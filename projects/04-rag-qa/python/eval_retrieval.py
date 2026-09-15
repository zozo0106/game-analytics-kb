#!/usr/bin/env python3
"""
eval_retrieval.py —— 检索层评测：BM25 vs 稠密(LSA) vs 混合(RRF)
================================================================
用人工标注的 38 题评测集（data/eval_questions.json），比较三种检索模式的
Recall@1/3/5 与 MRR，回答一个很实际的问题：**小语料上到底要不要上向量检索？**

输出：data/eval_results.json
      assets/retrieval_metrics.png

运行：python python/eval_retrieval.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag_lib import RagIndex          # noqa: E402
from ask import extract_answer        # noqa: E402

plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

PROJ = Path(__file__).resolve().parent.parent
INDEX = PROJ / "data" / "index.pkl"
QS = PROJ / "data" / "eval_questions.json"
MODES = ["bm25", "dense", "hybrid"]
LABELS = {"bm25": "BM25 (sparse)", "dense": "LSA (dense)", "hybrid": "Hybrid (RRF)"}


def evaluate(idx: RagIndex, questions: list[dict], mode: str, ks=(1, 3, 5)) -> dict:
    hits_at = {k: 0 for k in ks}
    rr_sum, details = 0.0, []
    for item in questions:
        gold = set(item["gold_docs"])
        if not gold:                                  # 域外问题：不计入检索指标
            continue
        hits = idx.search(item["q"], k=max(ks), mode=mode)
        got = [h["doc"] for h in hits]
        rank = next((i for i, d in enumerate(got, 1) if d in gold), None)
        for k in ks:
            if rank is not None and rank <= k:
                hits_at[k] += 1
        rr_sum += 1.0 / rank if rank else 0.0
        details.append({"q": item["q"], "rank": rank, "top1": got[0],
                        "gold": sorted(gold)})
    n = len(details)
    return {
        "mode": mode,
        "n": n,
        **{f"recall@{k}": round(hits_at[k] / n, 4) for k in ks},
        "mrr": round(rr_sum / n, 4),
        "details": details,
    }


def eval_abstain(idx: RagIndex, questions: list[dict]) -> dict:
    """域外问题检测：知识库里没有答案时，系统应当"拒答"而不是硬凑。"""
    ood = [q for q in questions if not q["gold_docs"]]
    in_domain = [q for q in questions if q["gold_docs"]]
    ok_ood = sum(1 for q in ood if not extract_answer(q["q"], idx.search(q["q"], 5), idx))
    ok_in = sum(1 for q in in_domain if extract_answer(q["q"], idx.search(q["q"], 5), idx))
    return {
        "n_ood": len(ood), "abstain_correct": ok_ood,
        "abstain_rate": round(ok_ood / len(ood), 4) if ood else None,
        "n_in_domain": len(in_domain), "answered": ok_in,
        "answer_rate": round(ok_in / len(in_domain), 4) if in_domain else None,
    }


def plot(results: list[dict]) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    x = np.arange(len(results))
    labels = [LABELS[r["mode"]] for r in results]
    for ax, key, title in [(axes[0], "recall@1", "Recall@1"),
                           (axes[1], "recall@3", "Recall@3"),
                           (axes[2], "mrr", "MRR")]:
        vals = [r[key] for r in results]
        bars = ax.bar(x, vals, color=["#4C72B0", "#DD8452", "#55A868"])
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=12, fontsize=9)
        ax.set_ylim(0, 1.05)
        ax.set_title(title, loc="left", fontsize=11)
        ax.grid(alpha=0.25, axis="y")
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.2f}",
                    ha="center", fontsize=9)
    fig.suptitle("Retrieval quality on the 38-question labeled set", fontsize=12)
    fig.tight_layout()
    fig.savefig(PROJ / "assets" / "retrieval_metrics.png", dpi=130)
    plt.close(fig)


def main() -> None:
    idx = RagIndex.load(INDEX)
    questions = json.loads(QS.read_text(encoding="utf-8"))["questions"]

    results = [evaluate(idx, questions, m) for m in MODES]
    abstain = eval_abstain(idx, questions)
    (PROJ / "data" / "eval_results.json").write_text(
        json.dumps({"retrieval": {r["mode"]: {k: v for k, v in r.items() if k != "details"}
                                  for r in results},
                    "abstain": abstain}, ensure_ascii=False, indent=2), encoding="utf-8")
    plot(results)

    n = results[0]["n"]
    print(f"📊 检索评测（{n} 题标注 · 知识库 {len(idx.chunks)} 块 / "
          f"{len({c.doc for c in idx.chunks})} 篇）\n")
    print(f"   {'模式':<16}{'Recall@1':>10}{'Recall@3':>10}{'Recall@5':>10}{'MRR':>8}")
    for r in results:
        print(f"   {LABELS[r['mode']]:<16}{r['recall@1']:>10.3f}{r['recall@3']:>10.3f}"
              f"{r['recall@5']:>10.3f}{r['mrr']:>8.3f}")

    print(f"\n   拒答能力（域外问题拦截）：{abstain['abstain_correct']}/{abstain['n_ood']} "
          f"= {abstain['abstain_rate']:.0%}；域内可答题作答率："
          f"{abstain['answered']}/{abstain['n_in_domain']} = {abstain['answer_rate']:.0%}")

    # 混合模式下仍未进前 5 的失败案例
    fails = [d for d in results[-1]["details"] if d["rank"] is None]
    print(f"\n   混合模式漏检（前 5 未命中）：{len(fails)} 题")
    for d in fails:
        print(f"     ✗ {d['q']}\n        gold={d['gold']}  top1={d['top1']}")

    print("\n✅ 已输出 data/eval_results.json, assets/retrieval_metrics.png")


if __name__ == "__main__":
    main()
