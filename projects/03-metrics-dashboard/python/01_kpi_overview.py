#!/usr/bin/env python3
"""
01_kpi_overview.py —— KPI 体检：周期对比 + 异常检测
================================================================
读 data/metrics_daily.csv（由 build_metrics.py 产出），做两件事：
  1. 周期对比：最近 7 天 vs 前 7 天（看指标在变好还是变差）
  2. 异常检测：基于"滚动中位数 + MAD"的稳健 z 分数（Iglewicz & Hoaglin 1993）
     —— 比均值±σ 更抗离群点，适合日级看板的自动告警

输出：data/summary.json   周期对比结果
      data/alerts.json    命中的异常点
      assets/kpi_trend.png
      assets/kpi_rates.png

运行：python python/01_kpi_overview.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]   # 图内不出现中文，避免豆腐块
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

Z_THRESHOLD = 3.5      # 改进 z 分数常用阈值（Iglewicz & Hoaglin）
WINDOW = 28            # 滚动窗口（约 4 周）
ALERT_METRICS = ["dau", "revenue", "pay_rate_pct"]


def robust_zscores(s: pd.Series, window: int) -> pd.Series:
    """改进 z 分数：0.6745 * (x - rolling_median) / rolling_MAD"""
    med = s.rolling(window, min_periods=window // 2).median()
    mad = (s - med).abs().rolling(window, min_periods=window // 2).median()
    mad = mad.replace(0, np.nan)
    return 0.6745 * (s - med) / mad


def deseasonalize(df: pd.DataFrame, col: str, weeks: int = 8) -> pd.Series:
    """去掉星期效应：每个值 ÷ 同星期几的滚动中位数。
    游戏流量有明显周内节律（周末高），不做这一步，周末会被误判成异常。"""
    wd = pd.to_datetime(df["date"]).dt.weekday
    factor = df.groupby(wd)[col].transform(
        lambda g: g.rolling(weeks, min_periods=weeks // 2).median())
    return df[col] / factor


def period_compare(df: pd.DataFrame) -> dict:
    last7, prev7 = df.tail(7), df.tail(14).head(7)
    metrics = ["dau", "revenue", "arpu", "pay_rate_pct", "minutes_per_dau",
               "d1_ret_pct", "d7_ret_pct"]
    out = {}
    for m in metrics:
        a, b = float(last7[m].mean()), float(prev7[m].mean())
        out[m] = {"last7": round(a, 3), "prev7": round(b, 3),
                  "wow_pct": round(100 * (a - b) / b, 2) if b else None}
    return out


def detect_alerts(df: pd.DataFrame) -> list[dict]:
    alerts = []
    for m in ALERT_METRICS:
        adj = deseasonalize(df, m)          # 先去星期季节性
        z = robust_zscores(adj, WINDOW)     # 再算稳健 z 分数
        hit = df[z.abs() > Z_THRESHOLD]
        for _, r in hit.iterrows():
            zz = float(z.loc[r.name])
            alerts.append({
                "date": r["date"], "metric": m,
                "value": round(float(r[m]), 3), "z": round(zz, 2),
                "direction": "高于常态" if zz > 0 else "低于常态",
            })
    return sorted(alerts, key=lambda a: a["date"])


def plot_trend(df: pd.DataFrame, alerts: list[dict]) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    x = pd.to_datetime(df["date"])
    for ax, col, ma, title in [(axes[0], "dau", "dau_ma7", "DAU & 7-day MA"),
                               (axes[1], "revenue", "revenue_ma7", "Revenue & 7-day MA")]:
        ax.plot(x, df[col], color="#4C72B0", lw=1.2, label=col)
        ax.plot(x, df[ma], color="#DD8452", lw=2, label=ma)
        for a in [a for a in alerts if a["metric"] == col]:
            color = "#C44E52" if a["direction"] == "低于常态" else "#55A868"
            ax.axvspan(pd.to_datetime(a["date"]), pd.to_datetime(a["date"]),
                       color=color, alpha=0.35)
        ax.set_title(title, loc="left", fontsize=11)
        ax.legend(loc="upper left", fontsize=8, frameon=False)
        ax.grid(alpha=0.25)
    fig.suptitle("Daily KPI trend with robust-z anomalies (red=dip, green=spike)", fontsize=12)
    fig.tight_layout()
    fig.savefig(ASSETS / "kpi_trend.png", dpi=130)
    plt.close(fig)


def plot_rates(df: pd.DataFrame) -> None:
    x = pd.to_datetime(df["date"])
    fig, axes = plt.subplots(2, 2, figsize=(12, 6))
    specs = [("pay_rate_pct", "Pay rate (%)"), ("arpu", "ARPU (CNY)"),
             ("minutes_per_dau", "Minutes / DAU"), ("d1_ret_pct", "D1 retention (%)")]
    for ax, (col, title) in zip(axes.ravel(), specs):
        ax.plot(x, df[col], color="#4C72B0", lw=1.1)
        ax.set_title(title, loc="left", fontsize=10)
        ax.grid(alpha=0.25)
    fig.suptitle("Engagement & monetization KPIs", fontsize=12)
    fig.tight_layout()
    fig.savefig(ASSETS / "kpi_rates.png", dpi=130)
    plt.close(fig)


def main() -> None:
    df = pd.read_csv(DATA / "metrics_daily.csv")

    summary = period_compare(df)
    with open(DATA / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    alerts = detect_alerts(df)
    with open(DATA / "alerts.json", "w", encoding="utf-8") as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)

    plot_trend(df, alerts)
    plot_rates(df)

    print("📅 最近 7 天 vs 前 7 天（环比）")
    for m, v in summary.items():
        print(f"   {m:16s} {v['prev7']:>12,.2f} → {v['last7']:>12,.2f}  ({v['wow_pct']:+.2f}%)")
    print(f"\n🚨 异常检测命中 {len(alerts)} 点（改进 z 分数，阈值 |z|>{Z_THRESHOLD}）")
    for a in alerts:
        print(f"   {a['date']}  {a['metric']:14s} {a['value']:>12,.2f}  z={a['z']:+.2f}  {a['direction']}")
    print("\n✅ 已输出 assets/kpi_trend.png, assets/kpi_rates.png, data/summary.json, data/alerts.json")


if __name__ == "__main__":
    main()
