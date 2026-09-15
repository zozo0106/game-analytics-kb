#!/usr/bin/env python3
"""
01_design_and_srm.py —— 实验可信度前置检查
================================================================
看实验结论之前，先回答三个"体检"问题：

  1. 样本量够不够？   → 功效分析：给定基线，检出 X pp 需要多少人
  2. 分流对不对？     → SRM 卡方检验（比例失衡 = 数据链路出 bug，结论直接作废）
  3. 分层均不均衡？   → 渠道/设备分布检验 + 实验前指标 AA 对比

这三步不过，后面的显著性检验都是"在错误的地基上盖楼"。

输出：data/design.json
运行：python python/01_design_and_srm.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from scipy import stats

from ab_lib import achieved_power, required_sample_size, srm_test

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ALPHA, POWER = 0.05, 0.80


def main() -> None:
    df = pd.read_csv(DATA / "ab_features.csv")
    ctrl = df[df.group_name == "control"]
    trt = df[df.group_name == "treatment"]
    result: dict = {}

    # ---------------- 1. 功效分析 ----------------
    p1 = ctrl.retained_d7.mean()
    plan = []
    for mde_pp in [0.5, 1.0, 1.5, 2.0, 3.0]:
        mde = mde_pp / 100
        n_req = required_sample_size(p1, mde, ALPHA, POWER)
        plan.append({
            "mde_pp": mde_pp,
            "n_per_group": n_req,
            "achieved_power_at_actual_n": round(achieved_power(p1, mde, min(len(ctrl), len(trt)), ALPHA), 3),
            "feasible_now": bool(min(len(ctrl), len(trt)) >= n_req),
        })
    result["power_analysis"] = {"baseline_p": round(float(p1), 4), "alpha": ALPHA, "power": POWER, "plan": plan}

    print("─" * 64)
    print(f"【1】功效分析  (对照组基线活跃率 {p1:.2%}, α={ALPHA}, power={POWER})")
    print(f"{'MDE(绝对)':>10} {'每组所需N':>12} {'当前功效':>10} {'现有样本是否够':>14}")
    for r in plan:
        print(f"{r['mde_pp']:>9.1f}pp {r['n_per_group']:>12,} {r['achieved_power_at_actual_n']:>10.1%}"
              f" {'✅ 够' if r['feasible_now'] else '❌ 不够':>12}")

    # ---------------- 2. SRM 分流比例检验 ----------------
    srm = srm_test(len(ctrl), len(trt), expected_ratio=0.5)
    result["srm"] = srm
    print("\n" + "─" * 64)
    print(f"【2】SRM 分流校验  control={srm['n_control']:,} / treatment={srm['n_treatment']:,}"
          f"  实际占比={srm['observed_ratio']:.4f}")
    print(f"     χ²={srm['chi2']:.4f}, p={srm['p_value']:.4f} → "
          f"{'🚨 检出失衡，实验不可信！' if srm['srm_detected'] else '✅ 分流正常'}")

    # ---------------- 3. 分层与 AA 均衡性 ----------------
    balance = {}
    for dim in ["channel", "device"]:
        tab = pd.crosstab(df[dim], df.group_name)
        chi2, p, _, _ = stats.chi2_contingency(tab)
        balance[dim] = {"chi2": round(float(chi2), 4), "p_value": round(float(p), 4),
                        "balanced": bool(p > 0.05)}
        print(f"\n【3】分层校验 · {dim}:  χ²={chi2:.4f}, p={p:.4f} → "
              f"{'✅ 均衡' if p > 0.05 else '❌ 不均衡'}")

    aa = {}
    for col in ["pre_matches_14d", "pre_revenue_14d", "pre_active_days_14d"]:
        t, p = stats.ttest_ind(ctrl[col], trt[col], equal_var=False)
        aa[col] = {"t": round(float(t), 4), "p_value": round(float(p), 4), "balanced": bool(p > 0.05)}
        print(f"     实验前指标 AA · {col:20s} p={p:.4f} → {'✅ 均衡' if p > 0.05 else '❌ 不均衡'}")
    result["balance"] = balance
    result["aa_pre_metrics"] = aa
    result["n"] = {"control": int(len(ctrl)), "treatment": int(len(trt))}

    (DATA / "design.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n✅ 前置检查完成 → data/design.json")


if __name__ == "__main__":
    main()
