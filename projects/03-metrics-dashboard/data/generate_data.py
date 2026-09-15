#!/usr/bin/env python3
"""
generate_data.py —— 合成一款 F2P 手游 180 天的日级经营数据
================================================================
目的：给"指标体系看板"提供一份**可复现**的明细底表。
全部为合成数据（非真实业务数据），seed 固定，结果可复现。

产出：
  data/daily_fact.csv        明细事实表（日期 × 渠道 × 机型 × 地域）
  data/cohort_retention.csv  新增批次留存表（按安装日）
  data/calendar.csv          活动/事件日历（供异常检测自检用）

埋入的真实"剧情"（让看板的异常检测有真东西可抓）：
  - 第 58~63 天：版本 2.1 上线后崩溃率飙升 → 活跃/时长下挫（负异常）
  - 第 118~120 天：限时活动（充值返利 + 登录奖） → 活跃/收入脉冲（正异常）
  - 全程：周末季节性抬升 + 缓慢自然增长 + 随机噪声

运行：python data/generate_data.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
DAYS = 180
START = "2026-03-01"

CHANNELS = ["自然量", "应用商店", "买量-信息流", "买量-KOL"]
DEVICES = ["iOS", "Android"]
REGIONS = ["华东", "华北", "华南", "西部"]

# 渠道结构（占比）与渠道特征（获客成本口径的差异体现在新增/付费结构上）
CHANNEL_W = {"自然量": 0.34, "应用商店": 0.26, "买量-信息流": 0.26, "买量-KOL": 0.14}
CHANNEL_INSTALL = {"自然量": 0.012, "应用商店": 0.02, "买量-信息流": 0.045, "买量-KOL": 0.05}
CHANNEL_PAYRATE = {"自然量": 0.021, "应用商店": 0.028, "买量-信息流": 0.034, "买量-KOL": 0.038}
DEVICE_W = {"iOS": 0.42, "Android": 0.58}
DEVICE_ARPPU = {"iOS": 1.22, "Android": 0.84}   # iOS 付费深度偏高
REGION_W = {"华东": 0.34, "华北": 0.24, "华南": 0.26, "西部": 0.16}

BASE_DAU = 120_000.0
TREND = 0.18          # 全程自然增长 18%
WEEKEND_LIFT = 0.08   # 周末抬升
NOISE = 0.018

# 事件：{起, 止, daily活跃系数, 收入系数}
EVENTS = [
    {"name": "版本2.1崩溃", "start": 58, "end": 63, "active": 0.88, "revenue": 0.80},
    {"name": "限时充值活动", "start": 118, "end": 120, "active": 1.35, "revenue": 1.60},
]


def event_multiplier(day_idx: int, key: str) -> float:
    m = 1.0
    for e in EVENTS:
        if e["start"] <= day_idx <= e["end"]:
            m *= e[key]
    return m


def main() -> None:
    rng = np.random.default_rng(SEED)
    dates = pd.date_range(START, periods=DAYS, freq="D")

    # ---------- 大盘曲线（日级） ----------
    rows = []
    for i, d in enumerate(dates):
        weekend = 1.0 + (WEEKEND_LIFT if d.weekday() >= 5 else 0.0)
        trend = 1.0 + TREND * i / (DAYS - 1)
        noise = 1.0 + rng.normal(0, NOISE)
        dau_total = BASE_DAU * trend * weekend * noise * event_multiplier(i, "active")

        # ---------- 拆到"渠道 × 机型 × 地域"明细 ----------
        for ch in CHANNELS:
            for dev in DEVICES:
                for rg in REGIONS:
                    w = CHANNEL_W[ch] * DEVICE_W[dev] * REGION_W[rg]
                    cell_noise = 1.0 + rng.normal(0, 0.03)
                    active = dau_total * w * cell_noise
                    # 新增：渠道安装率不同，且随大盘趋势走
                    new_u = active * CHANNEL_INSTALL[ch] * (1.0 + 0.5 * TREND * i / (DAYS - 1))
                    # 付费：渠道付费率 × 机型付费深度
                    pay_rate = CHANNEL_PAYRATE[ch] * DEVICE_ARPPU[dev] * 0.9
                    payers = active * pay_rate * (1.0 + rng.normal(0, 0.05)) * event_multiplier(i, "revenue")
                    # 收入：付费人数 × 人均付费（机型差异）
                    arppu = 62.0 * DEVICE_ARPPU[dev] * (1.0 + rng.normal(0, 0.06))
                    revenue = payers * arppu * event_multiplier(i, "revenue")
                    # 参与：会话与时长（周末更高）
                    sessions = active * (3.3 + rng.normal(0, 0.06)) * weekend
                    minutes = active * (44.0 + rng.normal(0, 0.8)) * weekend * event_multiplier(i, "active")

                    rows.append((d.strftime("%Y-%m-%d"), ch, dev, rg,
                                 int(round(new_u)), int(round(active)), int(round(sessions)),
                                 round(float(minutes), 1), int(round(payers)), round(float(revenue), 2)))
    fact = pd.DataFrame(rows, columns=["date", "channel", "device", "region",
                                       "new_users", "active_users", "sessions",
                                       "play_minutes", "payers", "revenue"])
    fact.to_csv(Path(__file__).parent / "daily_fact.csv", index=False)

    # ---------- 新增批次留存表（按安装日） ----------
    daily_new = fact.groupby("date", as_index=False)["new_users"].sum()
    cov = []
    for i, r in daily_new.iterrows():
        base_d1 = 0.40 + 0.06 * i / (DAYS - 1)      # D1 留存从 40% 缓慢改善到 46%
        base_d7 = 0.19 + 0.05 * i / (DAYS - 1)
        base_d30 = 0.085 + 0.03 * i / (DAYS - 1)
        # 版本 bug 期间新增用户质量更差
        if 58 <= i <= 63:
            base_d1 *= 0.85
            base_d7 *= 0.80
            base_d30 *= 0.78
        n = int(r["new_users"])
        cov.append({
            "install_date": r["date"],
            "new_users": n,
            "retained_d1": int(round(n * np.clip(base_d1 + rng.normal(0, 0.008), 0, 1))),
            "retained_d7": int(round(n * np.clip(base_d7 + rng.normal(0, 0.006), 0, 1))),
            "retained_d30": int(round(n * np.clip(base_d30 + rng.normal(0, 0.004), 0, 1))),
        })
    pd.DataFrame(cov).to_csv(Path(__file__).parent / "cohort_retention.csv", index=False)

    # ---------- 事件日历（仅用于异常检测自检，正常流程不读） ----------
    cal = [{"name": e["name"],
            "date_start": dates[e["start"]].strftime("%Y-%m-%d"),
            "date_end": dates[e["end"]].strftime("%Y-%m-%d"),
            "type": "负异常" if e["active"] < 1 else "正异常"} for e in EVENTS]
    with open(Path(__file__).parent / "calendar.csv", "w", encoding="utf-8") as f:
        pd.DataFrame(cal).to_csv(f, index=False)

    print("✅ 合成数据已生成")
    print(f"   daily_fact.csv        {fact.shape[0]:,} 行 × {fact.shape[1]} 列"
          f"（{DAYS} 天 × {len(CHANNELS)} 渠道 × {len(DEVICES)} 机型 × {len(REGIONS)} 地域）")
    print(f"   cohort_retention.csv  {len(cov):,} 行（{DAYS} 个安装批次）")
    print(f"   calendar.csv          {len(cal)} 个埋入事件（仅供异常检测自检）")


if __name__ == "__main__":
    main()
