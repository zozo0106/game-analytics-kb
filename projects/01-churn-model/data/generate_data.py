#!/usr/bin/env python3
"""
合成数据生成器 —— 游戏用户流失预测项目
================================================

为什么用合成数据？
  - 真实项目数据属于公司资产，不能带出来（脱敏也不行）
  - 合成数据可一键复现、可调参、无隐私风险，面试官 `git clone` 就能跑
  - 模拟了真实游戏日志的常见结构：日活明细 + 用户档案 + 付费流水

生成三张表：
  1. user_daily.csv    用户日活明细（登录/时长/对局/社交/等级）
  2. user_profile.csv  用户档案（注册信息/渠道/设备/是否付费）
  3. purchases.csv     付费流水

标签定义（见 ../README.md）：
  - 特征窗口：day 0 .. day 52  （53 天）
  - 标签窗口：day 53 .. day 59 （7 天）
  - churn = 标签窗口内一次都没登录

运行：python data/generate_data.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# ---------------- 配置（改这里就能调难度/规模） ----------------
SEED = 42
N_USERS = 8_000
OBS_DAYS = 60          # 总观察天数
LABEL_DAYS = 7         # 标签窗口长度（最后 7 天）
START = pd.Timestamp("2026-01-01")
OUT = Path(__file__).resolve().parent

# 用户原型：base 基础活跃度 / slope 每日衰减 / quit 主动流失概率
ARCHETYPES = {
    #  name      base    slope      quit_p   min_base  social_p  payer_p
    "loyal":   (0.88, -0.0005,    0.02,    70,       0.75,     0.28),
    "regular": (0.62, -0.0020,    0.07,    42,       0.45,     0.15),
    "fading":  (0.70, -0.0110,    0.42,    46,       0.35,     0.18),
    "light":   (0.34, -0.0030,    0.16,    24,       0.15,     0.05),
}
ARCH_NAMES = list(ARCHETYPES)
ARCH_PROBS = [0.26, 0.34, 0.24, 0.16]

CHANNELS = ["自然量", "买量-头条", "买量-腾讯", "买量-抖音", "老带新"]
CHANNEL_P = [0.20, 0.24, 0.18, 0.22, 0.16]
DEVICES = ["iOS", "Android"]
DEVICE_P = [0.42, 0.58]
COUNTRIES = ["CN", "CN", "CN", "SEA", "Other"]  # 以国内为主


def main() -> None:
    rng = np.random.default_rng(SEED)
    days = pd.date_range(START, periods=OBS_DAYS, freq="D")

    # ---------------- 1. 生成用户档案与隐性参数 ----------------
    arch = rng.choice(ARCH_NAMES, size=N_USERS, p=ARCH_PROBS)
    n = N_USERS
    base = np.array([ARCHETYPES[a][0] for a in arch])
    slope = np.array([ARCHETYPES[a][1] for a in arch])
    quit_p = np.array([ARCHETYPES[a][2] for a in arch])
    min_base = np.array([ARCHETYPES[a][3] for a in arch])
    social_p = np.array([ARCHETYPES[a][4] for a in arch])
    payer_p = np.array([ARCHETYPES[a][5] for a in arch])

    social = rng.random(n) < social_p

    # 主动流失日：一天起彻底不登录（版本冲击 / 换游戏）
    has_quit = rng.random(n) < quit_p
    quit_day = np.where(
        has_quit,
        rng.integers(5, OBS_DAYS, size=n),   # 5 ~ 59 天之间某天退出
        OBS_DAYS + 1,                         # 没退出
    )

    # 新用户：约 15% 在观察期内才注册（注册日靠后）
    late_register = rng.random(n) < 0.15
    reg_offset = np.where(late_register, rng.integers(0, 35, size=n), 0)
    reg_date = days[reg_offset]

    # ---------------- 2. 逐日模拟活跃 ----------------
    rows = []
    sessions_min = []
    t = np.arange(OBS_DAYS)

    # 每个用户每天的基础登录概率（含社交加成）
    social_bonus = np.where(social, 0.08, 0.0)[:, None]
    p_daily = base[:, None] + slope[:, None] * t[None, :] + social_bonus
    p_daily += rng.normal(0, 0.06, size=(n, OBS_DAYS))
    p_daily = np.clip(p_daily, 0.005, 0.98)

    # 未注册 / 已退出 → 概率置 0
    active_mask = t[None, :] >= reg_offset[:, None]
    for k in range(n):
        if quit_day[k] < OBS_DAYS:
            active_mask[k, quit_day[k]:] = False
    p_daily = p_daily * active_mask

    login = rng.random((n, OBS_DAYS)) < p_daily

    # 单次时长：活跃日按原型基准 * 参与度衰减
    engage = np.clip(1 + slope[:, None] * t[None, :] * 8, 0.25, 1.3)
    for k in range(n):
        mins = rng.gamma(shape=2.2, scale=min_base[k] / 2.2, size=OBS_DAYS) * engage[k]
        mins = np.round(mins * login[k]).astype(int)          # 非活跃日=0
        sessions_min.append(mins)

    # ---------------- 3. 组装日活明细 ----------------
    reg_ids = np.array([f"U{uid:05d}" for uid in range(n)])
    level_cum = np.zeros(n)      # 累计游玩分钟 → 等级
    is_payer = rng.random(n) < payer_p

    daily_user, daily_date = [], []
    daily_logins, daily_min, daily_match = [], [], []
    daily_social, daily_level = [], []

    for d_idx in range(OBS_DAYS):
        for k in range(n):
            m = sessions_min[k]
            if m is None:
                continue
            if m[d_idx] > 0:
                # 对局数 ~ 时长成正比
                matches = int(max(0, rng.poisson(m[d_idx] / 12)))
                soc = int(rng.poisson(3 * social[k])) if social[k] else int(rng.poisson(0.4))
            else:
                m[d_idx] = 0
                matches, soc = 0, 0
            if m[d_idx] > 0:
                level_cum[k] += m[d_idx]
            lvl = 1 + int(np.sqrt(level_cum[k] / 90))   # 等级：随累计时长递减边际
            daily_user.append(reg_ids[k])
            daily_date.append(days[d_idx])
            daily_logins.append(int(login[k, d_idx]))
            daily_min.append(int(m[d_idx]))
            daily_match.append(matches)
            daily_social.append(soc)
            daily_level.append(lvl)

    user_daily = pd.DataFrame({
        "user_id": daily_user,
        "date": daily_date,
        "logins": daily_logins,
        "session_minutes": daily_min,
        "matches": daily_match,
        "social_actions": daily_social,
        "level_end": daily_level,
    })

    # ---------------- 4. 付费流水 ----------------
    pur_rows = []
    for k in range(n):
        if not is_payer[k]:
            continue
        # 付费用户：观察期内 1~6 次小额 + 少量大额
        n_pay = rng.integers(1, 7)
        for _ in range(n_pay):
            d = rng.integers(reg_offset[k], OBS_DAYS)
            amount = float(np.round(rng.choice([6, 30, 98, 198, 328, 648],
                                               p=[.30, .28, .20, .12, .06, .04]), 2))
            pur_rows.append({"user_id": reg_ids[k], "date": days[d], "amount": amount})
    purchases = pd.DataFrame(pur_rows)

    # ---------------- 5. 用户档案 ----------------
    profile = pd.DataFrame({
        "user_id": reg_ids,
        "register_date": reg_date,
        "channel": rng.choice(CHANNELS, size=n, p=CHANNEL_P),
        "device": rng.choice(DEVICES, size=n, p=DEVICE_P),
        "country": rng.choice(COUNTRIES, size=n),
        "is_payer": is_payer.astype(int),
    })

    # ---------------- 6. 标签：标签窗口内是否零登录 ----------------
    cutoff = days[OBS_DAYS - LABEL_DAYS]
    label_window = user_daily[user_daily["date"] >= cutoff]
    logged = set(label_window.loc[label_window["logins"] > 0, "user_id"])
    labels = pd.DataFrame({
        "user_id": reg_ids,
        "churn": [0 if u in logged else 1 for u in reg_ids],
        # 仅供自检：真实"退出日"（模型严禁使用，属数据泄露）
        "_true_quit_day": quit_day,
    })

    # ---------------- 7. 落盘 ----------------
    user_daily.to_csv(OUT / "user_daily.csv", index=False)
    profile.to_csv(OUT / "user_profile.csv", index=False)
    purchases.to_csv(OUT / "purchases.csv", index=False)
    labels.to_csv(OUT / "labels.csv", index=False)

    churn_rate = labels["churn"].mean()
    print(f"✅ 生成完成 → {OUT}")
    print(f"   用户数        : {n:,}")
    print(f"   日活明细行数  : {len(user_daily):,}")
    print(f"   付费流水行数  : {len(purchases):,}")
    print(f"   流失率(churn) : {churn_rate:.1%}")
    print(f"   特征窗口      : {days[0].date()} ~ {days[OBS_DAYS-LABEL_DAYS-1].date()}")
    print(f"   标签窗口      : {cutoff.date()} ~ {days[-1].date()}")


if __name__ == "__main__":
    main()
