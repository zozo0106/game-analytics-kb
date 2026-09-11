#!/usr/bin/env python3
"""
探索性分析（EDA）：先看清楚"流失长什么样"，再谈建模
================================================

产出：
  - 控制台：流失率、关键特征对比、单变量区分度
  - assets/eda_*.png：特征分布对比图

运行：python python/01_eda.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)
plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

NUM_FEATURES = [
    "recency_days", "logins_7d", "login_trend", "logins_30d", "active_days",
    "avg_minutes_7d", "matches_7d", "social_7d", "social_per_login",
    "level_max", "level_gain_14d", "days_since_pay", "revenue_30d",
]


def main() -> None:
    df = pd.read_csv(ROOT / "data" / "features.csv")
    print(f"样本 {len(df):,} | 流失率 {df['churn'].mean():.1%}\n")

    # ---- 1. 关键特征：流失 vs 留存 均值对比 + 标准化差异 ----
    rows = []
    for c in NUM_FEATURES:
        g0, g1 = df.loc[df.churn == 0, c], df.loc[df.churn == 1, c]
        pooled = df[c].std(ddof=0) or 1
        rows.append({
            "feature": c,
            "留存均值": round(g0.mean(), 2),
            "流失均值": round(g1.mean(), 2),
            "标准化差异": round((g1.mean() - g0.mean()) / pooled, 3),
        })
    cmp = pd.DataFrame(rows).sort_values("标准化差异", key=abs, ascending=False)
    print("== 单变量区分度（|标准化差异| 越大越能区分流失）==")
    print(cmp.to_string(index=False))

    # ---- 2. 流失率曲线：按 recency / login_trend 分箱 ----
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    r = df.groupby(pd.cut(df.recency_days, bins=[-1, 0, 2, 4, 7, 14, 30, 60]),
                   observed=True)["churn"].mean()
    axes[0].bar(range(len(r)), r.values, color="#4C78A8")
    axes[0].set_xticks(range(len(r)))
    axes[0].set_xticklabels([str(i) for i in r.index], rotation=45, ha="right", fontsize=8)
    axes[0].set_title("Churn rate by recency (days since last login)")
    axes[0].set_ylabel("churn rate")

    t = df.groupby(pd.cut(df.login_trend, bins=[-100, -10, -5, -2, 0, 2, 100]),
                   observed=True)["churn"].mean()
    axes[1].bar(range(len(t)), t.values, color="#F58518")
    axes[1].set_xticks(range(len(t)))
    axes[1].set_xticklabels([str(i) for i in t.index], rotation=45, ha="right", fontsize=8)
    axes[1].set_title("Churn rate by login trend (last7 - prev7)")
    axes[1].set_ylabel("churn rate")

    s = df.groupby(pd.cut(df.social_7d, bins=[-1, 0, 5, 20, 50, 200, 10000]),
                   observed=True)["churn"].mean()
    axes[2].bar(range(len(s)), s.values, color="#54A24B")
    axes[2].set_xticks(range(len(s)))
    axes[2].set_xticklabels([str(i) for i in s.index], rotation=45, ha="right", fontsize=8)
    axes[2].set_title("Churn rate by social actions (last 7d)")
    axes[2].set_ylabel("churn rate")

    fig.tight_layout()
    fig.savefig(ASSETS / "eda_churn_curves.png", dpi=120)
    print(f"\n· 图已保存：{ASSETS / 'eda_churn_curves.png'}")

    # ---- 3. 渠道流失率 ----
    print("\n== 各渠道流失率 ==")
    print(df.groupby("channel")["churn"].agg(["mean", "count"])
            .sort_values("mean", ascending=False).round(3).to_string())


if __name__ == "__main__":
    main()
