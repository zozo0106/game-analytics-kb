"""
评测脚本：执行准确率 (Execution Accuracy, EX) + 错误归因

EX 定义（对齐 Spider / BIRD 的做法）：
    生成 SQL 与标准 SQL 在**同一数据库上执行结果一致** → 正确。
    比字符串匹配（Exact Match）更贴近业务真实需求。
"""
from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter

from nl2sql import DB_PATH, answer, parse, to_sql

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL_PATH = os.path.join(HERE, "..", "data", "eval_set.json")
OUT_PATH = os.path.join(HERE, "..", "data", "eval_results.json")

def run_sql(con, sql):
    cur = con.execute(sql)
    rows = cur.fetchall()
    return rows


def norm_rows(rows):
    """把结果规整成可比较的形式：浮点统一保留 4 位，行排序消除顺序影响。"""
    out = []
    for r in rows:
        rr = []
        for v in r:
            if isinstance(v, float):
                rr.append(round(v, 4))
            else:
                rr.append(v)
        out.append(tuple(rr))
    return sorted(out, key=lambda x: tuple(str(i) for i in x))


def classify_error(plan, gold_rows, gen_rows):
    """错误归因——比一个准确率数字更有用的东西。"""
    if not gen_rows and gold_rows:
        return "空结果/过滤条件错"
    if len(gen_rows) != len(gold_rows):
        if plan["dim"] and not plan["topn"] and len(gen_rows) < len(gold_rows):
            return "维度/过滤过严"
        if plan["topn"]:
            return "TopN 或排序错"
        return "聚合口径错"
    # 行数一致但值不同
    if plan["dim"]:
        return "维度取值或 Join 错"
    return "聚合口径错"


def main(eval_path: str = EVAL_PATH, out_path: str = OUT_PATH):
    with open(eval_path, encoding="utf-8") as f:
        spec = json.load(f)
    cases = spec["cases"]
    con = sqlite3.connect(DB_PATH)

    details, errors = [], []
    for c in cases:
        gold_rows = run_sql(con, c["gold"])
        try:
            plan = parse(c["q"])
            gen_sql = to_sql(plan)
            gen_rows = run_sql(con, gen_sql)
            ok = norm_rows(gold_rows) == norm_rows(gen_rows)
            err = None if ok else classify_error(plan, gold_rows, gen_rows)
        except Exception as e:  # 解析失败也算错，但要能看见原因
            plan, gen_sql, gen_rows, ok, err = None, None, None, False, f"解析/执行失败: {e}"

        details.append({
            "id": c["id"], "difficulty": c["difficulty"], "question": c["q"],
            "gold": c["gold"], "gen": gen_sql, "ok": ok, "error": err,
        })
        if not ok:
            errors.append({"id": c["id"], "q": c["q"], "type": err,
                           "gen": gen_sql, "gold_rows": gold_rows[:3],
                           "gen_rows": (gen_rows or [])[:3]})

    total = len(cases)
    correct = sum(1 for d in details if d["ok"])
    by_diff = {}
    for lvl in ["easy", "medium", "hard"]:
        sub = [d for d in details if d["difficulty"] == lvl]
        by_diff[lvl] = {
            "n": len(sub),
            "correct": sum(1 for d in sub if d["ok"]),
            "ex": round(sum(1 for d in sub if d["ok"]) / len(sub), 4) if sub else None,
        }

    err_counter = Counter(e["type"] for e in errors)
    result = {
        "engine": "rule_based_v1",
        "ref_date": spec["ref_date"],
        "total": total,
        "correct": correct,
        "execution_accuracy": round(correct / total, 4),
        "by_difficulty": by_diff,
        "error_breakdown": dict(err_counter),
        "errors": errors,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[{os.path.basename(eval_path)}] 执行准确率 EX = {correct}/{total} = {result['execution_accuracy']:.2%}")
    for lvl, v in by_diff.items():
        print(f"  {lvl:6s}: {v['correct']}/{v['n']}  EX={v['ex']:.2%}")
    print("错误分布:", dict(err_counter))
    for e in errors:
        print(f"  ✗ #{e['id']} {e['q']}  -> {e['type']}")
    print(f"\n明细已写入 {OUT_PATH}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        p = sys.argv[1]
        o = p.replace(".json", "_results.json")
        main(p, o)
    else:
        main()
