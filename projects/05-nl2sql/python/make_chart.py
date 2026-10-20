"""生成报告配图：三套评测集的 EX 对比 + 保留集按难度的错误构成。"""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "..", "assets", "eval_summary.png")
os.makedirs(os.path.dirname(OUT), exist_ok=True)


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


dev = load("eval_results.json")
para = load("eval_paraphrase_results.json")
hold = load("eval_holdout_results.json")

fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))

# --- 左：三套集对比
names = ["Dev set\n(handbuilt, tuned)", "Paraphrase set\n(tuned, leaked)", "Held-out set\n(untouched)"]
vals = [dev["execution_accuracy"] * 100, para["execution_accuracy"] * 100, hold["execution_accuracy"] * 100]
colors = ["#6b8e9f", "#9aa5b1", "#c0504d"]
bars = axes[0].bar(names, vals, color=colors, width=0.55)
for b, v in zip(bars, vals):
    axes[0].text(b.get_x() + b.get_width() / 2, v + 2, f"{v:.0f}%", ha="center", fontsize=12, fontweight="bold")
axes[0].set_ylim(0, 112)
axes[0].set_ylabel("Execution Accuracy (%)")
axes[0].set_title("Rule baseline: in-distribution vs held-out", fontsize=12)
axes[0].grid(axis="y", alpha=0.25)
axes[0].axhline(100, color="#c0504d", ls=":", lw=1)

# --- 右：保留集按难度
diffs = ["easy", "medium", "hard"]
ex = [hold["by_difficulty"][d]["ex"] * 100 for d in diffs]
ns = [hold["by_difficulty"][d]["n"] for d in diffs]
bars2 = axes[1].bar([f"{d}\n(n={n})" for d, n in zip(diffs, ns)], ex,
                    color=["#4f81bd", "#9bbb59", "#c0504d"], width=0.55)
for b, v, n in zip(bars2, ex, ns):
    axes[1].text(b.get_x() + b.get_width() / 2, v + 2, f"{v:.0f}%", ha="center", fontsize=12, fontweight="bold")
axes[1].set_ylim(0, 112)
axes[1].set_ylabel("Execution Accuracy (%)")
axes[1].set_title("Held-out set by difficulty (n=20)", fontsize=12)
axes[1].grid(axis="y", alpha=0.25)

plt.tight_layout()
plt.savefig(OUT, dpi=150)
print("saved:", OUT)
