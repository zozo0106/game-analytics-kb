"""
生成 PRJ-5 NL2SQL 用的游戏分析样例库（SQLite）。

数据区间：2026-01-01 ~ 2026-06-30
口径约定：REF_DATE = 2026-06-30（"今天"），所有"最近N天"均以此为基准。

用法：
    python3 generate_game_db.py
产出：
    game.db (同目录)
"""
import os
import random
import sqlite3
from datetime import date, timedelta

REF_DATE = date(2026, 6, 30)
DATA_START = date(2026, 1, 1)
HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "game.db")
SCHEMA_PATH = os.path.join(HERE, "..", "sql", "schema.sql")

CHANNELS = ["自然量", "买量-抖音", "买量-腾讯", "应用商店"]
CHANNEL_W = [0.35, 0.30, 0.20, 0.15]
COUNTRIES = ["CN", "US", "JP", "KR", "SEA"]
COUNTRY_W = [0.60, 0.14, 0.10, 0.07, 0.09]
PRODUCTS = [
    # (product_id, name, type, price)
    (1, "新手礼包", "礼包", 6.0),
    (2, "成长基金", "礼包", 68.0),
    (3, "至尊月卡", "月卡", 30.0),
    (4, "普通月卡", "月卡", 12.0),
    (5, "限定时装-星海", "皮肤", 128.0),
    (6, "限定时装-暗夜", "皮肤", 98.0),
    (7, "复活币x10", "道具", 6.0),
    (8, "体力药水x5", "道具", 12.0),
    (9, "赛季通行证", "礼包", 88.0),
    (10, "周年庆礼包", "礼包", 198.0),
    (11, "改名卡", "道具", 20.0),
    (12, "限定坐骑-赤焰", "皮肤", 328.0),
]


def d(s):
    return date.fromisoformat(s)


def main():
    random.seed(20260630)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        cur.executescript(f.read())

    n_users = 6000
    users, active, orders = [], [], []

    for uid in range(1, n_users + 1):
        # 注册日期：整体偏近期（增长盘）
        span_days = (REF_DATE - DATA_START).days
        offset = int(random.triangular(0, span_days, span_days * 0.7))
        reg = DATA_START + timedelta(days=offset)
        channel = random.choices(CHANNELS, CHANNEL_W)[0]
        country = random.choices(COUNTRIES, COUNTRY_W)[0]
        level = min(60, max(1, int(random.gauss(28, 12))))
        vip = random.choices([0, 1, 2, 3, 4, 5], [0.70, 0.13, 0.08, 0.05, 0.03, 0.01])[0]
        users.append((uid, reg.isoformat(), channel, country, level, vip))

        # 活跃行为：从注册日到 REF_DATE，按活跃强度抽样
        act_rate = random.betavariate(2, 5)          # 大部分玩家偏冷
        if vip >= 3:
            act_rate = min(0.95, act_rate + 0.35)
        cur_day = reg
        while cur_day <= REF_DATE:
            if random.random() < act_rate:
                sessions = random.choice([1, 1, 2, 2, 3, 4, 6])
                minutes = round(sessions * random.uniform(8, 45), 1)
                lv = max(1, min(60, level - random.randint(0, 8)))
                active.append((uid, cur_day.isoformat(), sessions, minutes, lv))
            cur_day += timedelta(days=1)

        # 付费行为：VIP 越高越可能付费
        pay_p = 0.06 + vip * 0.05
        if random.random() < pay_p:
            n_orders = random.randint(1, 20)
            dur = max(1, (REF_DATE - reg).days)
            for _ in range(n_orders):
                od = reg + timedelta(days=random.randint(0, dur))
                pid, _, _, price = random.choice(PRODUCTS)
                amt = round(price * random.choice([1, 1, 1, 1.2, 0.8]), 2)
                orders.append((None, uid, od.isoformat(), pid, amt, "CNY"))

    cur.executemany("INSERT INTO users VALUES (?,?,?,?,?,?)", users)
    cur.executemany("INSERT INTO daily_active VALUES (?,?,?,?,?)", active)
    cur.executemany("INSERT INTO products VALUES (?,?,?,?)", PRODUCTS)
    cur.executemany(
        "INSERT INTO purchases VALUES (?,?,?,?,?,?)",
        [(i + 1, o[1], o[2], o[3], o[4], o[5]) for i, o in enumerate(orders)],
    )
    con.commit()

    print(f"users        : {cur.execute('SELECT COUNT(*) FROM users').fetchone()[0]:>8,}")
    print(f"daily_active : {cur.execute('SELECT COUNT(*) FROM daily_active').fetchone()[0]:>8,}")
    print(f"purchases    : {cur.execute('SELECT COUNT(*) FROM purchases').fetchone()[0]:>8,}")
    print(f"products     : {cur.execute('SELECT COUNT(*) FROM products').fetchone()[0]:>8,}")
    print(f"GMV          : {cur.execute('SELECT ROUND(SUM(amount),2) FROM purchases').fetchone()[0]:>12,.2f}")
    print(f"-> {DB_PATH}")
    con.close()


if __name__ == "__main__":
    main()
