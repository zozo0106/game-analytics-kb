"""
LLM 适配层（可选）—— 把规则引擎换/补成大模型时的统一入口。

设计要点：
    1. 走 OpenAI 兼容协议，国内主流厂商（DeepSeek / 通义 / Kimi / 智谱）都能直接换 base_url
    2. 只给「Schema Card + 词典枚举值」，不给整库 DDL —— 上下文成本和准确率都更好
    3. 生成后**必须**过 sql_guard + 执行自检，再决定是否回退到规则引擎
    4. 没有 API key 时自动降级，保证整个仓库 clone 下来就能跑

用法：
    export LLM_API_KEY=sk-xxx
    export LLM_BASE_URL=https://api.deepseek.com/v1
    export LLM_MODEL=deepseek-chat
    python llm_adapter.py "最近一周各渠道活跃玩家数"
"""
from __future__ import annotations

import json
import os
import urllib.request

from nl2sql import DB_PATH, SCHEMA_CARD, answer as rule_answer
from sql_guard import validate

BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
API_KEY = os.environ.get("LLM_API_KEY", "")
MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")

SYSTEM_PROMPT = """你是游戏数据分析领域的 NL2SQL 专家。把中文问题翻译成 SQLite 查询。

只输出 JSON，不要解释：
{"sql": "...", "reasoning": "一句话说明口径"}

硬性规则：
- 只能生成单条 SELECT，禁止任何写操作
- 指标口径必须来自下面的指标字典，不要自创
- 时间窗以 REF_DATE={ref_date} 为基准；"最近N天"= [REF-(N-1), REF]
- 表名/列名必须来自 Schema Card
"""


def schema_prompt() -> str:
    lines = []
    for t, meta in SCHEMA_CARD.items():
        lines.append(f"- {t}({', '.join(meta['columns'])})  -- {meta['desc']}")
    return "\n".join(lines)


def ask_llm(question: str, ref_date: str = "2026-06-30") -> dict:
    if not API_KEY:
        raise RuntimeError("未设置 LLM_API_KEY，已自动降级到规则引擎")

    payload = {
        "model": MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.format(ref_date=ref_date) + "\n\nSchema Card:\n" + schema_prompt()},
            {"role": "user", "content": question},
        ],
    }
    req = urllib.request.Request(
        f"{BASE_URL.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    return json.loads(content)


def answer_hybrid(question: str) -> dict:
    """混合策略：LLM 优先，护栏不通过就回退规则引擎。"""
    try:
        out = ask_llm(question)
        sql = validate(out["sql"])
        return {"engine": "llm", "sql": sql, "reasoning": out.get("reasoning", "")}
    except Exception as e:
        r = rule_answer(question)
        r["engine"] = "rule_fallback"
        r["fallback_reason"] = str(e)
        return r


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "最近7天各渠道活跃用户数"
    result = answer_hybrid(q)
    print(json.dumps({k: v for k, v in result.items() if k != "plan"}, ensure_ascii=False, indent=2, default=str))
