"""
NL2SQL 基线引擎（规则 + Schema Linking，零依赖、可离线跑）

三段式流水线（和真实产品一致，只是后两段用规则替代 LLM）：
    1. Schema Linking  —— 把自然语言里的词映射到 表 / 列 / 枚举值
    2. Query Planning  —— 识别 指标 / 维度 / 时间窗 / TopN
    3. SQL Rendering   —— 按模板生成 SQL

设计取舍：
    - 之所以先做规则基线，是为了拿到一个**可解释的下界**。
      后面接 LLM 时（llm_adapter.py），所有提升都能量化，而不是"感觉变好了"。
"""
from __future__ import annotations

import os
import re
import sqlite3
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "..", "data", "game.db")
REF_DATE = date(2026, 6, 30)

# ---------------------------------------------------------------- Schema Card
# 真实 NL2SQL 里，这一步是把 DDL 喂给模型；规则版里它是硬编码的映射表。
SCHEMA_CARD = {
    "users": {
        "desc": "用户维度，一人一行",
        "columns": ["user_id", "register_date", "channel", "country", "level", "vip_level"],
    },
    "daily_active": {
        "desc": "日活明细，玩家 x 天，一行=某玩家某天在线",
        "columns": ["user_id", "log_date", "sessions", "play_minutes", "level_end"],
    },
    "purchases": {
        "desc": "付费订单，一行=一笔订单",
        "columns": ["order_id", "user_id", "order_date", "product_id", "amount", "currency"],
    },
    "products": {
        "desc": "商品维度",
        "columns": ["product_id", "product_name", "product_type", "price"],
    },
}

# ---------------------------------------------------------------- 指标字典
# 顺序敏感：越具体的口径越靠前（ARPPU 必须在 ARPU 前，付费用户 必须在 用户 前）
METRICS = [
    {
        "name": "arppu",
        "keys": ["arppu", "每付费用户平均收入"],
        "table": "purchases", "alias": "p",
        "expr": "ROUND(SUM(p.amount) / COUNT(DISTINCT p.user_id), 2)",
        "time_col": "p.order_date",
        "support_dim": True,
    },
    {
        "name": "arpu",
        "keys": ["arpu", "每活跃用户平均收入"],
        "table": "purchases", "alias": "p",
        "expr": "ROUND((SELECT SUM(amount) FROM purchases WHERE {tf}) * 1.0 / "
                "(SELECT COUNT(DISTINCT user_id) FROM daily_active WHERE {tf_da}), 2)",
        "time_col": "p.order_date",
        "support_dim": False,       # 分子分母不同表，规则版先不支持下钻
    },
    {
        "name": "paying_users",
        "keys": ["付费用户数", "付费用户", "付费人数"],
        "table": "purchases", "alias": "p",
        "expr": "COUNT(DISTINCT p.user_id)",
        "time_col": "p.order_date",
        "support_dim": True,
    },
    {
        "name": "dau",
        "keys": ["活跃用户数", "活跃用户", "dau", "日活"],
        "table": "daily_active", "alias": "da",
        "expr": "COUNT(DISTINCT da.user_id)",
        "time_col": "da.log_date",
        "support_dim": True,
    },
    {
        "name": "new_users",
        "keys": ["注册用户数", "注册用户", "新增用户数", "新增用户", "新增", "注册"],
        "table": "users", "alias": "u",
        "expr": "COUNT(*)",
        "time_col": "u.register_date",
        "support_dim": True,
    },
    {
        "name": "revenue",
        "keys": ["收入", "gmv", "流水", "营收", "付费金额", "销售额"],
        "table": "purchases", "alias": "p",
        "expr": "ROUND(SUM(p.amount), 2)",
        "time_col": "p.order_date",
        "support_dim": True,
    },
    {
        "name": "orders",
        "keys": ["订单数", "订单量", "订单"],
        "table": "purchases", "alias": "p",
        "expr": "COUNT(*)",
        "time_col": "p.order_date",
        "support_dim": True,
    },
    {
        "name": "avg_duration",
        "keys": ["平均时长", "平均游戏时长", "人均时长", "平均在线时长"],
        "table": "daily_active", "alias": "da",
        "expr": "ROUND(AVG(da.play_minutes), 2)",
        "time_col": "da.log_date",
        "support_dim": True,
    },
    {
        "name": "sessions",
        "keys": ["会话数", "会话", "启动次数"],
        "table": "daily_active", "alias": "da",
        "expr": "SUM(da.sessions)",
        "time_col": "da.log_date",
        "support_dim": True,
    },
    {
        "name": "users_total",
        "keys": ["用户数", "用户", "人数"],
        "table": "users", "alias": "u",
        "expr": "COUNT(*)",
        "time_col": "u.register_date",
        "support_dim": True,
    },
]

# ---------------------------------------------------------------- 维度字典
# need_user_join：base 表不是 users 时，要不要 join 用户维表
DIMENSIONS = [
    {"name": "product_name", "keys": ["商品名称", "各商品", "商品"], "expr": "pr.product_name", "need_product_join": True, "need_user_join": False},
    {"name": "product_type", "keys": ["商品类型", "品类"], "expr": "pr.product_type", "need_product_join": True, "need_user_join": False},
    {"name": "channel", "keys": ["渠道"], "expr": "u.channel", "need_product_join": False, "need_user_join": True},
    {"name": "country", "keys": ["国家", "地区", "区域"], "expr": "u.country", "need_product_join": False, "need_user_join": True},
    {"name": "vip_level", "keys": ["vip等级", "vip", "贵族等级"], "expr": "u.vip_level", "need_product_join": False, "need_user_join": True},
    {"name": "level", "keys": ["等级", "玩家等级"], "expr": "u.level", "need_product_join": False, "need_user_join": True},
    {"name": "month", "keys": ["每月", "按月", "每个月"], "expr": "strftime('%Y-%m', {time_col})", "need_product_join": False, "need_user_join": False},
    {"name": "date", "keys": ["每天", "按天", "每日", "日期"], "expr": "{time_col}", "need_product_join": False, "need_user_join": False},
]

CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6,
          "七": 7, "八": 8, "九": 9, "十": 10}

# ---------------------------------------------------------------- 同义词归一化
# 实测结论：保留集上的失败 8/8 都是「同一个意思换了说法」，
# 不是 SQL 逻辑不会写。所以最便宜的一次提升不是上大模型，而是先把词表补齐。
PHRASE_RULES = [
    # 整句同义（必须放最前，否则会被词级规则拆碎）
    ("平均每个付费用户花多少钱", "arppu"),
    ("平均每个付费用户", "arppu"),
]

SYNONYMS = [
    ("最近两周", "最近14天"), ("最近一周", "最近7天"), ("最近半个月", "最近15天"),
    ("两周", "14天"), ("半个月", "15天"), ("一周", "7天"),
    ("卖得最好", "收入最高"), ("卖得最多", "收入最高"), ("卖得最火", "收入最高"),
    ("收了多少钱", "收入"), ("赚了多少钱", "收入"), ("花了多少钱", "收入"),
    ("每一天", "每天"),
    ("玩家", "用户"),
    ("多少人", "用户数"),
    ("一共", ""), ("总共", ""), ("是多少", ""), ("分别为", ""),
]


def normalize(q: str) -> str:
    s = q.lower().replace(" ", "").replace("，", ",")
    for a, b in PHRASE_RULES:
        s = s.replace(a, b)
    for a, b in SYNONYMS:
        s = s.replace(a, b)
    return s


def _norm(q: str) -> str:
    return normalize(q).strip()


def _cn2int(s: str) -> int | None:
    if s.isdigit():
        return int(s)
    if s in CN_NUM:
        return CN_NUM[s]
    return None


# ---------------------------------------------------------------- 1. Schema Linking
def _best_match(q: str, items: list[dict]) -> dict | None:
    """最长关键词优先。

    踩过的坑：「各商品类型收入」里同时命中 '商品'（商品名称）和 '商品类型'（品类）。
    靠列表顺序来保证优先级，加一个新词就可能翻车；
    改成按命中关键词长度排序，语义越具体越优先，稳定性好得多。
    """
    best, best_len = None, 0
    for it in items:
        for k in it["keys"]:
            if k in q and len(k) > best_len:
                best, best_len = it, len(k)
    return best


def link_metric(q: str) -> dict | None:
    return _best_match(q, METRICS)


def link_dimension(q: str) -> dict | None:
    return _best_match(q, DIMENSIONS)


def link_time(q: str) -> tuple[str, str] | tuple[None, None]:
    """返回 (where 子句模板, 说明)。模板里 {c} 会被替换成指标的 time_col。"""
    # 最近 N 天 / 近 N 天
    m = re.search(r"(?:最近|近)\s*(\d+|[一二两三四五六七八九十]+)\s*(?:天|日)", q)
    if m:
        n = _cn2int(m.group(1))
        if n:
            start = REF_DATE - timedelta(days=n - 1)
            return (f"{{c}} >= '{start.isoformat()}' AND {{c}} <= '{REF_DATE.isoformat()}'", f"最近{n}天")

    if "本月" in q or "这个月" in q:
        return (f"{{c}} >= '2026-06-01' AND {{c}} <= '2026-06-30'", "本月")
    if "上月" in q or "上个月" in q:
        return (f"{{c}} >= '2026-05-01' AND {{c}} <= '2026-05-31'", "上月")

    m = re.search(r"(\d{4})年(\d{1,2})月", q)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        start = date(y, mo, 1)
        nxt = date(y + (mo == 12), 1 if mo == 12 else mo + 1, 1)
        end = nxt - timedelta(days=1)
        return (f"{{c}} >= '{start.isoformat()}' AND {{c}} <= '{end.isoformat()}'", f"{y}年{mo}月")

    # 省略年份的「6月」：默认按 REF_DATE 所在年补全
    m = re.search(r"(?<!\d)(\d{1,2})月", q)
    if m:
        mo = int(m.group(1))
        start = date(REF_DATE.year, mo, 1)
        nxt = date(REF_DATE.year + (mo == 12), 1 if mo == 12 else mo + 1, 1)
        end = nxt - timedelta(days=1)
        return (f"{{c}} >= '{start.isoformat()}' AND {{c}} <= '{end.isoformat()}'", f"{mo}月")

    return (None, None)


def link_topn(q: str) -> int | None:
    # 允许「最高的3个」「前 5 名」「Top3」等写法，中间的"的/排"是可选的
    m = re.search(r"(?:前|top|最高|排名前|最多的)\s*(?:的|排)?\s*(\d+|[一二两三四五六七八九十]+)\s*(?:个|名|位)?", q)
    if m:
        return _cn2int(m.group(1))
    return None


# ---------------------------------------------------------------- 2/3. Plan + Render
def parse(q: str) -> dict:
    qn = _norm(q)
    metric = link_metric(qn)
    if metric is None:
        raise ValueError(f"未识别指标：{q}")

    dim = link_dimension(qn)
    where_tpl, time_desc = link_time(qn)
    topn = link_topn(qn)
    if topn is None and ("哪个" in qn or "哪些" in qn) and ("最多" in qn or "最高" in qn):
        topn = 1

    # 维度不支持时降级：不下钻，只给总量
    degraded = []
    if dim and not metric["support_dim"]:
        degraded.append(f"指标 {metric['name']} 暂不支持按 {dim['name']} 下钻，已降级为总量")
        dim = None

    return {"question": q, "metric": metric, "dim": dim,
            "where_tpl": where_tpl, "time_desc": time_desc,
            "topn": topn, "degraded": degraded}


def to_sql(plan: dict) -> str:
    m, dim = plan["metric"], plan["dim"]
    table, alias = m["table"], m["alias"]

    where_expr = ""
    if plan["where_tpl"]:
        where_expr = plan["where_tpl"].replace("{c}", m["time_col"])
        if m["name"] == "arpu":
            where_expr_da = plan["where_tpl"].replace("{c}", "log_date")
            where_expr = plan["where_tpl"].replace("{c}", "order_date")  # 分子表内层
            m_expr = m["expr"].format(tf=where_expr, tf_da=where_expr_da)
        else:
            m_expr = m["expr"]
    else:
        m_expr = m["expr"].format(tf="1=1", tf_da="1=1") if m["name"] == "arpu" else m["expr"]

    # FROM
    from_sql = f"{table} {alias}"
    if dim:
        if dim["need_user_join"] and table != "users":
            from_sql += f" JOIN users u ON {alias}.user_id = u.user_id"
        if dim["need_product_join"] and table == "purchases":
            from_sql += " JOIN products pr ON p.product_id = pr.product_id"
        if dim["need_product_join"] and table != "purchases":
            raise ValueError("商品维度只支持付费类指标")

    # ARPU 是全量标量查询，不走 FROM
    if m["name"] == "arpu":
        return f"SELECT {m_expr} AS metric"

    dim_expr = None
    if dim:
        dim_expr = dim["expr"].replace("{time_col}", m["time_col"]), dim["name"]

    if dim_expr:
        select = f"SELECT {dim_expr[0]} AS dim, {m_expr} AS metric"
        sql = f"{select} FROM {from_sql}"
        if where_expr:
            sql += f" WHERE {where_expr}"
        sql += f" GROUP BY {dim_expr[0]}"
        if plan["topn"]:
            sql += f" ORDER BY metric DESC LIMIT {plan['topn']}"
        return sql

    sql = f"SELECT {m_expr} AS metric FROM {from_sql}"
    if where_expr:
        sql += f" WHERE {where_expr}"
    return sql


def answer(q: str, con: sqlite3.Connection | None = None) -> dict:
    plan = parse(q)
    sql = to_sql(plan)
    close = False
    if con is None:
        con = sqlite3.connect(DB_PATH)
        close = True
    try:
        cur = con.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    finally:
        if close:
            con.close()
    return {"question": q, "sql": sql, "columns": cols, "rows": rows,
            "plan": plan, "degraded": plan["degraded"]}


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "最近7天各渠道活跃用户数"
    r = answer(q)
    print("Q:", q)
    print("SQL:", r["sql"])
    for row in r["rows"][:20]:
        print("   ", row)
    if r["degraded"]:
        print("⚠️", *r["degraded"])
