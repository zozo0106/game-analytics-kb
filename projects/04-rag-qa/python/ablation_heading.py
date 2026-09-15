#!/usr/bin/env python3
"""
ablation_heading.py —— 消融实验：标题路径要不要进索引？
======================================================
同一份语料、同一套评测题，只改一件事：检索文本里**加不加章节标题路径**。
其余（分块、分词、BM25 参数、LSA 维度、RRF 常数）全部不变。

这样得到的就是「标题路径」这一项改动的净增益，而不是一堆参数混在一起的玄学。

输出：data/ablation_heading.json

运行：python python/ablation_heading.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag_lib import RagIndex                       # noqa: E402
from eval_retrieval import evaluate, LABELS, MODES  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"
PROJ = Path(__file__).resolve().parent.parent
QS = PROJ / "data" / "eval_questions.json"


def main() -> None:
    docs = sorted(DOCS.rglob("*.md"))
    questions = json.loads(QS.read_text(encoding="utf-8"))["questions"]

    variants = {"仅正文": False, "正文 + 标题路径": True}
    table: dict[str, dict[str, dict]] = {}
    for vname, use_heading in variants.items():
        idx = RagIndex.build(docs, base=ROOT, use_heading=use_heading)
        table[vname] = {m: {k: v for k, v in evaluate(idx, questions, m).items()
                            if k != "details"} for m in MODES}

    (PROJ / "data" / "ablation_heading.json").write_text(
        json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")

    n_in = sum(1 for q in questions if q["gold_docs"])
    print(f"🔬 消融实验：标题路径入索引（{n_in} 题标注）\n")
    print(f"   {'索引文本':<20}{'模式':<16}{'R@1':>7}{'R@3':>7}{'R@5':>7}{'MRR':>8}")
    for vname in variants:
        for m in MODES:
            r = table[vname][m]
            print(f"   {vname:<20}{LABELS[m]:<16}{r['recall@1']:>7.3f}{r['recall@3']:>7.3f}"
                  f"{r['recall@5']:>7.3f}{r['mrr']:>8.3f}")
        print()

    print("   增量（加标题 − 仅正文）：")
    for m in MODES:
        d1 = table["正文 + 标题路径"][m]["recall@1"] - table["仅正文"][m]["recall@1"]
        dm = table["正文 + 标题路径"][m]["mrr"] - table["仅正文"][m]["mrr"]
        print(f"     {LABELS[m]:<16} R@1 {d1:+.3f}   MRR {dm:+.3f}")

    print("\n✅ 已输出 data/ablation_heading.json")


if __name__ == "__main__":
    main()
