#!/usr/bin/env python3
"""
合成数据生成器 —— A/B 测试分析框架（项目 02）
================================================================

场景：某游戏对"存量活跃用户"做了一次 **14 天实验**，测试新版每日任务系统
      是否提升活跃与付费。分流单元 = 用户，实验组/对照组各 10,000 人。

为什么要合成数据？
  - 真实实验数据是公司资产，带不出来
  - 合成数据的**真实效应我们自己知道**（"上帝视角"），
    所以能反过来验证分析框架检得准不准 —— 真实数据做不到这一步

生成三张表：
  1. experiment_users.csv  用户档案（组别 / 渠道 / 设备 / 实验前 14 天行为）
  2. experiment_daily.csv  实验期每日明细（day 1..14：活跃 / 对局 / 收入）
  3. ground_truth.json     真实效应（用大样本期望精确算出来，供第五章自检）

数据里埋的"真实现象"（看分析框架能不能发现）：
  · 新奇效应：实验组活跃率提升第 1 天最高，随后指数衰减
  · 三条因果链：活跃率↑ → 对局数↑（传导） + 玩法本身让对局 +5%
  · 强前置协变量：实验前对局数 ↔ 实验期对局数（给 CUPED 用）

运行：python data/generate_data.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------- 配置（改这里就能调规模 / 效应） ----------------
SEED = 42
N_PER_GROUP = 10_000          # 每组人数 → 总 20,000
DAYS = 14                     # 实验持续天数
SPLIT = 0.5                   # 分流比例（对照组占比）
OUT = Path(__file__).resolve().parent

# ---- 真实效应参数（上帝视角）----
TREAT_LIFT_DAY1 = 0.055       # 第 1 天活跃率的**绝对**提升（新奇效应峰值，5.5pp）
NOVELTY_TAU = 7.0             # 新奇效应衰减常数：效应(d) = 峰值·exp(−(d−1)/τ)
MATCH_LIFT_REL = 0.05         # 玩法本身带来的对局数相对提升（+5%）
REV_LIFT_REL = 0.04           # 商业化改动带来的付费相对提升（+4%）

# ---- 基线设定 ----
BASE_RETENTION = 0.62         # 对照组活跃率基线
P_NATURAL = 0.60              # 自然量用户占比
P_IOS = 0.45                  # iOS 用户占比
CHANNEL_EFF = {"自然量": 0.06, "买量": -0.06}   # 自然量用户更粘
DEVICE_EFF = {"iOS": 0.03, "Android": -0.03}
LOGN_SIGMA = 0.80             # 付费金额对数正态的 σ


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def logit(p: float) -> float:
    return float(np.log(p / (1 - p)))


def _segments(n: int, rng: np.random.Generator):
    """抽样用户的分层属性与潜在活跃度。"""
    u = rng.normal(0.0, 1.0, n)
    is_natural = rng.random(n) < P_NATURAL
    is_ios = rng.random(n) < P_IOS
    ch_eff = np.where(is_natural, CHANNEL_EFF["自然量"], CHANNEL_EFF["买量"])
    dv_eff = np.where(is_ios, DEVICE_EFF["iOS"], DEVICE_EFF["Android"])
    return u, is_natural, is_ios, ch_eff, dv_eff


def true_effects(n_mc: int = 500_000, seed: int = 7) -> dict:
    """用大样本**期望**精确计算真实效应（不靠单次抽样的噪音）。

    对每个组别，按生成模型把每日指标解析地求期望：
      E[活跃_d]  = p_active_d
      E[对局]    = Σ_d E[活跃_d] · E[Poisson 均值]
      E[付费]    = Σ_d E[活跃_d] · E[付费概率] · E[金额]
    再用同一批用户算两组（配对，方差更小）。
    """
    rng = np.random.default_rng(seed)
    u, is_natural, _, ch_eff, dv_eff = _segments(n_mc, rng)
    base = logit(BASE_RETENTION) + 0.55 * u + ch_eff + dv_eff
    lam0 = np.where(is_natural, 2.2, 1.6) * np.exp(0.55 * u)
    payer_p = sigmoid(-3.30 + 0.60 * u + ch_eff)
    rev_mean = np.exp(2.40 + 0.30 * u + LOGN_SIGMA**2 / 2)

    res = {}
    for is_t in (False, True):
        ret7, matches, revenue = 0.0, 0.0, 0.0
        for d in range(1, 8):                       # 前 7 天口径
            eff = TREAT_LIFT_DAY1 * np.exp(-(d - 1) / NOVELTY_TAU) if is_t else 0.0
            p_active = np.clip(sigmoid(base) + eff, 0.001, 0.999)   # 与生成模型一致（概率空间）
            if d == 7:
                ret7 = float(p_active.mean())
            matches += float((p_active * lam0 * (1 + MATCH_LIFT_REL * is_t)).mean())
            revenue += float((p_active * payer_p * rev_mean * (1 + REV_LIFT_REL * is_t)).mean())
        res[is_t] = {"retained_d7": ret7, "matches_7d": matches, "revenue_7d": revenue}

    c, t = res[False], res[True]
    return {
        "retention_lift_abs": round(t["retained_d7"] - c["retained_d7"], 5),
        "retention_control": round(c["retained_d7"], 5),
        "matches_lift_rel": round(t["matches_7d"] / c["matches_7d"] - 1, 5),
        "revenue_lift_rel": round(t["revenue_7d"] / c["revenue_7d"] - 1, 5),
        "matches_lift_rel_pure": MATCH_LIFT_REL,     # 剔除活跃传导后的"纯玩法"效应
        "revenue_lift_rel_pure": REV_LIFT_REL,
    }


def main() -> None:
    rng = np.random.default_rng(SEED)
    n = N_PER_GROUP * 2

    # ---------------- 1. 分流与分层（随机化 → 组别与渠道/设备独立）----------------
    group = np.where(rng.random(n) < SPLIT, "control", "treatment")
    is_treat = group == "treatment"
    uid = np.arange(100_000, 100_000 + n)
    u, is_natural, is_ios, ch_eff, dv_eff = _segments(n, rng)
    channel = np.where(is_natural, "自然量", "买量")
    device = np.where(is_ios, "iOS", "Android")

    # ---------------- 2. 实验前 14 天行为（前置协变量，CUPED 的原料）----------------
    pre_p = sigmoid(logit(0.62) + 0.55 * u + ch_eff + dv_eff)
    pre_active_days = rng.binomial(DAYS, pre_p)
    pre_base = np.where(is_natural, 6.0, 4.5) * np.where(is_ios, 1.10, 1.0)
    pre_matches = rng.poisson(np.clip(pre_base * np.exp(0.55 * u), 0.2, None))
    pre_payer = rng.random(n) < sigmoid(-2.60 + 0.55 * u + ch_eff)
    pre_revenue = np.where(pre_payer, rng.lognormal(mean=2.60 + 0.30 * u, sigma=0.90), 0.0)

    users = pd.DataFrame({
        "user_id": uid, "group": group, "channel": channel, "device": device,
        "pre_active_days_14d": pre_active_days,
        "pre_matches_14d": pre_matches,
        "pre_revenue_14d": np.round(pre_revenue, 2),
    })

    # ---------------- 3. 实验期每日明细（埋入新奇效应）----------------
    base = logit(BASE_RETENTION) + 0.55 * u + ch_eff + dv_eff
    lam0 = np.where(is_natural, 2.2, 1.6) * np.exp(0.55 * u)
    payer_p_d = sigmoid(-3.30 + 0.60 * u + ch_eff)

    frames = []
    for d in range(1, DAYS + 1):
        # 实验组效应随天数指数衰减：第 1 天最高，之后逐渐回落
        effect = np.where(is_treat, TREAT_LIFT_DAY1 * np.exp(-(d - 1) / NOVELTY_TAU), 0.0)
        p_active = np.clip(sigmoid(base) + effect, 0.001, 0.999)   # 绝对提升（概率空间）
        active = (rng.random(n) < p_active).astype(int)

        lam = np.clip(lam0 * (1 + MATCH_LIFT_REL * is_treat), 0.01, None)
        matches = (rng.poisson(lam) * active).astype(int)

        rev_payer = (rng.random(n) < payer_p_d) & (active == 1)
        revenue = np.where(
            rev_payer,
            rng.lognormal(mean=2.40 + 0.30 * u, sigma=LOGN_SIGMA) * (1 + REV_LIFT_REL * is_treat),
            0.0,
        )

        frames.append(pd.DataFrame({
            "user_id": uid, "day": d, "group": group,
            "active": active, "matches": matches, "revenue": np.round(revenue, 2),
        }))

    daily = pd.concat(frames, ignore_index=True)

    # ---------------- 4. 落盘 ----------------
    users.to_csv(OUT / "experiment_users.csv", index=False)
    daily.to_csv(OUT / "experiment_daily.csv", index=False)

    truth = {
        "seed": SEED, "n_per_group": N_PER_GROUP, "days": DAYS,
        "params": {"treat_lift_day1_abs": TREAT_LIFT_DAY1, "novelty_tau_days": NOVELTY_TAU,
                   "match_lift_rel": MATCH_LIFT_REL, "revenue_lift_rel": REV_LIFT_REL},
        "true_effects": true_effects(),
        "notes": "真实效应由大样本期望精确算出，仅供分析框架自检；分析脚本不读取本文件。",
    }
    (OUT / "ground_truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------------- 5. 打印体检信息 ----------------
    d7 = daily[daily["day"] == 7]
    t7 = truth["true_effects"]
    print("✅ 合成数据生成完成")
    print(f"   用户数：{len(users):,}（control={(group=='control').sum():,} / treatment={is_treat.sum():,}）")
    print(f"   日志行数：{len(daily):,}")
    print(f"   对照组 day7 活跃率：{d7.loc[d7.group=='control','active'].mean():.4f}（真实基线 {t7['retention_control']:.4f}）")
    print(f"   实验组 day7 活跃率：{d7.loc[d7.group=='treatment','active'].mean():.4f}"
          f"（真实效应 +{t7['retention_lift_abs']*100:.2f}pp）")
    print(f"   真实效应：对局 {t7['matches_lift_rel']:+.2%} / 付费 {t7['revenue_lift_rel']:+.2%}"
          f"（其中纯玩法 {t7['matches_lift_rel_pure']:+.0%}、纯商业化 {t7['revenue_lift_rel_pure']:+.0%}）")
    print(f"   输出：{OUT}/experiment_users.csv, experiment_daily.csv, ground_truth.json")


if __name__ == "__main__":
    main()
