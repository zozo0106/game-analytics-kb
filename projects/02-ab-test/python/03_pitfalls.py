#!/usr/bin/env python3
"""
03_pitfalls.py —— 三个最常见的坑（也是面试最爱问的）
================================================================
A/B 测试真正的难点不在"会不会算 p 值"，而在**别被数据骗了**。这里用数据演示三坑：

  坑 1 · 新奇效应：实验组第 1 天涨得很猛，第 14 天没了 —— 只看首日结论会崩
  坑 2 · 多重比较：测 10 个指标，至少一个 p<0.05 的概率高达 40%（AA 测试实测）
  坑 3 · 辛普森悖论：整体看实验组更好，拆开每个渠道看，实验组都更差

输出：data/pitfalls.json, assets/novelty_effect.png, assets/simpson_paradox.png
运行：python python/03_pitfalls.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from ab_lib import holm_correction, two_prop_test  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA, ASSETS = ROOT / "data", ROOT / "assets"
ASSETS.mkdir(exist_ok=True)
ALPHA, SEED = 0.05, 42

plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

out: dict = {}


# ================================================================ 坑 1
def novelty_effect() -> None:
    trend = pd.read_csv(DATA / "daily_trend.csv")
    piv = trend.pivot(index="day", columns="group_name", values="active_rate")
    lift_pp = (piv["treatment"] - piv["control"]) * 100

    day1, day7, day14 = lift_pp.iloc[0], lift_pp.iloc[6], lift_pp.iloc[-1]
    out["novelty"] = {"lift_day1_pp": float(day1), "lift_day7_pp": float(day7),
                      "lift_day14_pp": float(day14),
                      "decay_ratio": float(day14 / day1) if day1 else None}

    print("═" * 66)
    print("【坑 1 · 新奇效应】分日活跃率提升（实验组 − 对照组）")
    print(f"  第 1 天  {day1:+.3f} pp   ← 若只看首日，会得出“效果炸裂”的结论")
    print(f"  第 7 天  {day7:+.3f} pp")
    print(f"  第 14 天 {day14:+.3f} pp（衰减到首日的 {day14/day1:.0%}）")
    print("  → 教训：读实验至少看一个完整周期，警惕“新玩具效应”")

    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.plot(piv.index, lift_pp.values, marker="o", color="#e76f51", label="daily lift (pp)")
    ax.axhline(0, color="gray", linewidth=1)
    ax.plot([1, 7], [day1, day7], linestyle="--", color="#264653", alpha=0.5)
    ax.annotate(f"day1 = {day1:+.2f}pp", (1, day1), textcoords="offset points", xytext=(8, 4), fontsize=9)
    ax.annotate(f"day7 = {day7:+.2f}pp", (7, day7), textcoords="offset points", xytext=(4, -14), fontsize=9)
    ax.annotate(f"day14 = {day14:+.2f}pp", (14, day14), textcoords="offset points", xytext=(-42, 8), fontsize=9)
    ax.set_xlabel("experiment day"); ax.set_ylabel("active-rate lift (pp)")
    ax.set_title("Pitfall 1 · Novelty effect: lift decays over time")
    ax.legend(); fig.tight_layout()
    fig.savefig(ASSETS / "novelty_effect.png", dpi=140); plt.close(fig)


# ================================================================ 坑 2
def multiple_comparisons() -> None:
    """AA 测试仿真：两组完全无差异，连测 N 次，看"至少一次假阳性"的概率。"""
    rng = np.random.default_rng(SEED)
    n_each, n_sim, p0 = 10_000, 2_000, 0.62
    x_c = rng.binomial(n_each, p0, n_sim)
    x_t = rng.binomial(n_each, p0, n_sim)          # 同一分布 → 真效应为 0
    pvals = np.array([two_prop_test(a, n_each, b, n_each)["p_value"] for a, b in zip(x_c, x_t)])
    fpr = float((pvals < ALPHA).mean())

    # 测 10 个指标时的族错误率（假设独立，理论值）
    fwer10 = 1 - (1 - ALPHA) ** 10

    # 实例：10 个次指标（真效应为 0）经 Holm 校正
    fake = {f"metric_{i:02d}": float(p) for i, p in enumerate(rng.uniform(0, 1, 10), 1)}
    holm = holm_correction(fake, ALPHA)
    raw_sig = sum(1 for p in fake.values() if p < ALPHA)
    holm_sig = sum(1 for h in holm if h["significant"])

    out["multiple_comparisons"] = {"aa_false_positive_rate": fpr, "n_simulations": n_sim,
                                   "theoretical_fwer_with_10_metrics": fwer10,
                                   "example_raw_significant": raw_sig, "example_holm_significant": holm_sig}
    print("\n" + "═" * 66)
    print("【坑 2 · 多重比较】")
    print(f"  AA 仿真：{n_sim:,} 次“完全无差异”的测试，假阳性率 = {fpr:.2%}（理论 α=5%）")
    print(f"  若一次看 10 个指标，至少出现 1 个假阳性的概率 ≈ {fwer10:.1%}（族错误率）")
    print(f"  示例：10 个“无效应”指标中，原始 p<0.05 的有 {raw_sig} 个，Holm 校正后剩 {holm_sig} 个")
    print("  → 教训：先定主指标；次指标必须校正，否则“总有一个显著”")


# ================================================================ 坑 3
def simpson_paradox() -> None:
    """坏实验：分流与渠道相关（例：埋点 bug 让自然量用户更容易进实验组）。
    结果：整体实验组更好，但每个渠道内部实验组都更差。"""
    rng = np.random.default_rng(SEED + 1)
    n = 40_000
    base = {"自然量": 0.70, "买量": 0.55}
    treat_effect = -0.02                     # 每个渠道内部：实验组都差 2pp

    seg = rng.choice(["自然量", "买量"], n, p=[0.5, 0.5])
    # ⚠️ 关键：分组概率依赖渠道（这就是 bug —— 随机化被破坏）
    p_treat = np.where(seg == "自然量", 0.80, 0.20)
    is_t = rng.random(n) < p_treat
    p_ret = np.array([base[s] for s in seg]) + np.where(is_t, treat_effect, 0.0)
    retained = rng.random(n) < p_ret

    df = pd.DataFrame({"segment": seg, "is_treatment": is_t, "retained": retained.astype(int)})
    c, t = df[~df.is_treatment], df[df.is_treatment]

    overall = two_prop_test(int(c.retained.sum()), len(c), int(t.retained.sum()), len(t))
    per_seg = {}
    for s in ["自然量", "买量"]:
        cs, ts = c[c.segment == s], t[t.segment == s]
        r = two_prop_test(int(cs.retained.sum()), len(cs), int(ts.retained.sum()), len(ts))
        per_seg[s] = {"control_n": int(len(cs)), "treatment_n": int(len(ts)), **r}

    out["simpson_paradox"] = {"overall": overall, "per_segment": per_seg,
                              "treatment_share_自然量": float((t.segment == "自然量").mean()),
                              "control_share_自然量": float((c.segment == "自然量").mean())}
    print("\n" + "═" * 66)
    print("【坑 3 · 辛普森悖论】（分流被渠道污染：实验组里自然量用户占比异常高）")
    print(f"  自然量占比：对照组 {out['simpson_paradox']['control_share_自然量']:.1%}"
          f"  vs  实验组 {out['simpson_paradox']['treatment_share_自然量']:.1%}  ← 明显失衡")
    print(f"  整体： {overall['p_control']:.2%} → {overall['p_treatment']:.2%}"
          f"  ({overall['abs_lift']*100:+.2f}pp, p={overall['p_value']:.4f})  ← 看起来赢了")
    for s, r in per_seg.items():
        print(f"  {s}内部：{r['p_control']:.2%} → {r['p_treatment']:.2%}"
              f"  ({r['abs_lift']*100:+.2f}pp, p={r['p_value']:.4f})  ← 其实输了")
    print("  → 教训：结论前必做分层检验；分流与人群相关时，整体均值毫无意义")

    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    groups = ["Overall", "Natural", "Paid"]
    cvals = [overall["p_control"] * 100, per_seg["自然量"]["p_control"] * 100, per_seg["买量"]["p_control"] * 100]
    tvals = [overall["p_treatment"] * 100, per_seg["自然量"]["p_treatment"] * 100, per_seg["买量"]["p_treatment"] * 100]
    x = np.arange(3); w = 0.35
    b1 = ax.bar(x - w / 2, cvals, w, label="control", color="#8d99ae")
    b2 = ax.bar(x + w / 2, tvals, w, label="treatment", color="#e76f51")
    for xi, (cv, tv) in enumerate(zip(cvals, tvals)):
        ax.text(xi, max(cv, tv) + 0.8, f"{tv-cv:+.2f}pp", ha="center", fontsize=9,
                color="#2a9d8f" if tv - cv > 0 else "#c1121f")
    ax.set_xticks(x); ax.set_xticklabels(groups); ax.set_ylabel("retention (%)")
    ax.set_title("Pitfall 3 · Simpson's paradox: overall up, every segment down")
    ax.legend(); fig.tight_layout()
    fig.savefig(ASSETS / "simpson_paradox.png", dpi=140); plt.close(fig)


def main() -> None:
    novelty_effect()
    multiple_comparisons()
    simpson_paradox()
    (DATA / "pitfalls.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n✅ 图表 → assets/novelty_effect.png, assets/simpson_paradox.png")
    print("✅ 结果 → data/pitfalls.json")


if __name__ == "__main__":
    main()
