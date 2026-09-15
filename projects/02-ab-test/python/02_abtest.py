#!/usr/bin/env python3
"""
02_abtest.py —— 核心：显著性检验 + CUPED 方差缩减 + 多重比较校正
================================================================
前置检查（01）通过后，这里回答业务最关心的一句话：
    **新版每日任务系统到底有没有用？能不能上线？**

流程：
  1. 主指标：D7 活跃率 —— 两比例 z 检验 + 95% 置信区间
  2. 次指标：付费率 / 对局数 / 人均付费 —— 分类型选检验（t / Bootstrap）
  3. CUPED：用实验前对局数做协变量，演示方差缩减（同样的数据，更窄的区间）
  4. 多重比较：Holm 校正，避免"测 10 个指标总有一个显著"的假阳性
  5. 决策：主指标显著 & 方向为正 & 护栏指标不恶化 → 建议上线

输出：data/metrics.json, assets/*.png
运行：python python/02_abtest.py
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

from ab_lib import bootstrap_diff_means, cuped_adjust, holm_correction, two_prop_test  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA, ASSETS = ROOT / "data", ROOT / "assets"
ASSETS.mkdir(exist_ok=True)
ALPHA = 0.05

plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def boot_relative_ci(a: np.ndarray, b: np.ndarray, n_boot: int = 10_000, seed: int = 42) -> tuple[float, float, float]:
    """相对提升 (mean_b/mean_a - 1) 的 Bootstrap 95% CI。"""
    rng = np.random.default_rng(seed)
    a, b = np.asarray(a, float), np.asarray(b, float)
    obs = b.mean() / a.mean() - 1
    draws = np.empty(n_boot)
    for i in range(n_boot):
        draws[i] = rng.choice(b, b.size, True).mean() / rng.choice(a, a.size, True).mean() - 1
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return float(obs), float(lo), float(hi)


def main() -> None:
    df = pd.read_csv(DATA / "ab_features.csv")
    c = df[df.group_name == "control"]
    t = df[df.group_name == "treatment"]
    out: dict = {}

    # ================= 1. 主指标：D7 活跃率（两比例 z 检验）=================
    r = two_prop_test(int(c.retained_d7.sum()), len(c), int(t.retained_d7.sum()), len(t), ALPHA)
    out["primary_retained_d7"] = r
    print("═" * 66)
    print("【主指标】D7 活跃率（实验第 7 天是否活跃）")
    print(f"  对照组 {r['p_control']:.4%}  vs  实验组 {r['p_treatment']:.4%}")
    print(f"  绝对提升 {r['abs_lift']*100:+.3f} pp   相对提升 {r['rel_lift']*100:+.2f}%")
    print(f"  95% CI [{r['ci_low']*100:+.3f}, {r['ci_high']*100:+.3f}] pp   z={r['z']:.3f}   p={r['p_value']:.4f}"
          f"   → {'✅ 显著' if r['significant'] else '❌ 不显著'}")

    # ================= 2. 次指标 =================
    sec, sec_p = {}, {}

    payer = two_prop_test(int(c.payer_7d.sum()), len(c), int(t.payer_7d.sum()), len(t), ALPHA)
    sec["payer_7d"] = {"type": "binary", **payer,
                       "display": f"付费率 {payer['p_control']:.2%} → {payer['p_treatment']:.2%}"}
    sec_p["payer_7d"] = payer["p_value"]

    # 对局数：连续、近似正态 → Welch t 检验 + Bootstrap 交叉验证
    tw, pw = stats.ttest_ind(t.matches_7d, c.matches_7d, equal_var=False)
    bs = bootstrap_diff_means(c.matches_7d.values, t.matches_7d.values)
    rel, rlo, rhi = boot_relative_ci(c.matches_7d.values, t.matches_7d.values)
    sec["matches_7d"] = {"type": "continuous", "test": "welch_t", "t": float(tw), "p_value": float(pw),
                         "mean_control": float(c.matches_7d.mean()), "mean_treatment": float(t.matches_7d.mean()),
                         "abs_lift": bs["diff"], "ci_low": bs["ci_low"], "ci_high": bs["ci_high"],
                         "rel_lift": rel, "rel_ci_low": rlo, "rel_ci_high": rhi,
                         "display": f"人均对局 {c.matches_7d.mean():.3f} → {t.matches_7d.mean():.3f}"}
    sec_p["matches_7d"] = float(pw)

    # 付费金额：重尾 → 只用 Bootstrap
    bs_rev = bootstrap_diff_means(c.revenue_7d.values, t.revenue_7d.values)
    rel_r, rlo_r, rhi_r = boot_relative_ci(c.revenue_7d.values, t.revenue_7d.values)
    sec["revenue_7d"] = {"type": "heavy_tailed", "test": "bootstrap", **bs_rev,
                         "mean_control": float(c.revenue_7d.mean()), "mean_treatment": float(t.revenue_7d.mean()),
                         "rel_lift": rel_r, "rel_ci_low": rlo_r, "rel_ci_high": rhi_r,
                         "display": f"人均付费 {c.revenue_7d.mean():.3f} → {t.revenue_7d.mean():.3f}"}
    sec_p["revenue_7d"] = bs_rev["p_two_sided"]

    print("\n" + "═" * 66)
    print("【次指标】")
    for name, s in sec.items():
        pv = s.get("p_value", s.get("p_two_sided"))
        sig = "✅" if (pv < ALPHA) else "❌"
        print(f"  {name:14s} {s['display']:>34s}   p={pv:.4f} {sig}")

    # ================= 3. CUPED 方差缩减 =================
    pre = df.pre_matches_14d.values
    y = df.matches_7d.values
    y_adj, theta, rho = cuped_adjust(y, pre)
    g_adj = df.group_name.values
    raw_diff = t.matches_7d.mean() - c.matches_7d.mean()
    adj_diff = y_adj[g_adj == "treatment"].mean() - y_adj[g_adj == "control"].mean()
    raw_se = np.sqrt(c.matches_7d.var(ddof=1) / len(c) + t.matches_7d.var(ddof=1) / len(t))
    adj_se = np.sqrt(y_adj[g_adj == "treatment"].var(ddof=1) / len(t) + y_adj[g_adj == "control"].var(ddof=1) / len(c))
    var_reduction = 1 - (adj_se / raw_se) ** 2
    out["cuped"] = {"theta": theta, "corr_pre_post": rho, "var_reduction": float(var_reduction),
                    "se_reduction": float(1 - adj_se / raw_se),
                    "raw_diff": float(raw_diff), "raw_ci": [float(raw_diff - 1.96 * raw_se), float(raw_diff + 1.96 * raw_se)],
                    "adj_diff": float(adj_diff), "adj_ci": [float(adj_diff - 1.96 * adj_se), float(adj_diff + 1.96 * adj_se)]}
    print("\n" + "═" * 66)
    print("【CUPED 方差缩减】（协变量 = 实验前 14 天对局数）")
    print(f"  ρ(pre, post) = {rho:.3f}   θ = {theta:.3f}   → 方差缩减 {var_reduction:.1%}，标准误降低 {(1-adj_se/raw_se):.1%}")
    print(f"  普通均值差 = {raw_diff:+.4f}  CI [{raw_diff-1.96*raw_se:+.4f}, {raw_diff+1.96*raw_se:+.4f}]（宽 {2*1.96*raw_se:.4f}）")
    print(f"  CUPED 修正 = {adj_diff:+.4f}  CI [{adj_diff-1.96*adj_se:+.4f}, {adj_diff+1.96*adj_se:+.4f}]（宽 {2*1.96*adj_se:.4f}）")

    # ================= 4. 多重比较校正 =================
    holm = holm_correction(sec_p, ALPHA)
    out["holm"] = holm
    print("\n" + "═" * 66)
    print("【多重比较校正】Holm–Bonferroni（共测 %d 个次指标）" % len(sec_p))
    for h in holm:
        print(f"  {h['metric']:14s} p={h['p_value']:.4f}  阈值={h['threshold']:.4f}  "
              f"{'✅ 仍显著' if h['significant'] else '❌ 校正后不显著'}")
    raw_sig = sum(1 for p in sec_p.values() if p < ALPHA)
    holm_sig = sum(1 for h in holm if h["significant"])
    print(f"  校正前显著 {raw_sig}/{len(sec_p)} 个 → 校正后 {holm_sig}/{len(sec_p)} 个")

    # ================= 5. 决策 =================
    decision = "上线" if (r["significant"] and r["abs_lift"] > 0) else "暂不上线"
    out["decision"] = {"recommendation": decision, "primary_significant": r["significant"],
                       "primary_lift_pp": r["abs_lift"] * 100}
    print("\n" + "═" * 66)
    print(f"【决策建议】{decision}（主指标显著且为正 → 若护栏指标无恶化即可灰度放量）")

    # ================= 6. 自检（仅合成数据可做）=================
    truth_path = DATA / "ground_truth.json"
    if truth_path.exists():
        truth = json.loads(truth_path.read_text(encoding="utf-8"))["true_effects"]
        print("\n" + "═" * 66)
        print("【框架自检】合成数据的真实效应 vs 模型检出（真实数据无法做此步）")
        det = [("D7活跃率 lift(pp)", r["abs_lift"] * 100, truth["retention_lift_abs"] * 100, "pp"),
               ("人均对局 lift(%)", rel * 100, truth["matches_lift_rel"] * 100, "%"),
               ("人均付费 lift(%)", rel_r * 100, truth["revenue_lift_rel"] * 100, "%")]
        for name, got, exp, unit in det:
            print(f"  {name:18s} 检出 {got:+.2f}{unit}  真实 {exp:+.2f}{unit}  偏差 {got-exp:+.2f}{unit}")
        out["self_check"] = [{"metric": n, "detected": g, "true": e} for n, g, e, _ in det]

    # ================= 7. 出图 =================
    fig, ax = plt.subplots(figsize=(6, 4.5))
    vals = [r["p_control"] * 100, r["p_treatment"] * 100]
    errs = [1.96 * np.sqrt(r["p_control"] * (1 - r["p_control"]) / len(c)) * 100,
            1.96 * np.sqrt(r["p_treatment"] * (1 - r["p_treatment"]) / len(t)) * 100]
    bars = ax.bar(["Control", "Treatment"], vals, yerr=errs, capsize=6, color=["#8d99ae", "#2a9d8f"], width=0.5)
    ax.set_ylabel("D7 active rate (%)")
    ax.set_title(f"Primary metric: D7 retention\nlift = {r['abs_lift']*100:+.2f}pp (p={r['p_value']:.4f})")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.6, f"{v:.2f}%", ha="center", fontsize=9)
    ax.set_ylim(min(vals) - 3, max(vals) + 3)
    fig.tight_layout()
    fig.savefig(ASSETS / "primary_metric.png", dpi=140)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    ctrl_mask = g_adj == "control"
    axes[0].hist(y[ctrl_mask] - y[ctrl_mask].mean(), bins=40, alpha=0.6, label="raw (centered)", color="#8d99ae")
    axes[0].hist(y_adj[ctrl_mask] - y_adj[ctrl_mask].mean(), bins=40, alpha=0.6,
                 label="CUPED-adjusted (centered)", color="#2a9d8f")
    axes[0].set_title(f"CUPED variance reduction = {var_reduction:.1%}\ncorr(pre, post) = {rho:.3f}")
    axes[0].set_xlabel("matches_7d"); axes[0].legend(fontsize=8)

    labels = ["D7 retention", "payer rate", "matches/user", "revenue/user"]
    rels = [r["rel_lift"] * 100, (payer["p_treatment"] / payer["p_control"] - 1) * 100, rel * 100, rel_r * 100]
    los = [(r["ci_low"] / r["p_control"]) * 100, ((payer["ci_low"]) / payer["p_control"]) * 100, rlo * 100, rlo_r * 100]
    his = [(r["ci_high"] / r["p_control"]) * 100, ((payer["ci_high"]) / payer["p_control"]) * 100, rhi * 100, rhi_r * 100]
    yy = np.arange(len(labels))[::-1]
    axes[1].errorbar(rels, yy, xerr=[np.array(rels) - np.array(los), np.array(his) - np.array(rels)],
                     fmt="o", color="#264653", capsize=5)
    axes[1].axvline(0, color="red", linestyle="--", linewidth=1)
    axes[1].set_yticks(yy); axes[1].set_yticklabels(labels)
    axes[1].set_xlabel("relative lift (%) with 95% CI")
    axes[1].set_title("Effect size by metric")
    fig.tight_layout()
    fig.savefig(ASSETS / "effect_summary.png", dpi=140)
    plt.close(fig)
    print(f"\n✅ 图表 → assets/primary_metric.png, assets/effect_summary.png")

    out["secondary"] = sec
    (DATA / "metrics.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("✅ 结果 → data/metrics.json")


if __name__ == "__main__":
    main()
