#!/usr/bin/env python3
"""
ab_lib.py —— A/B 测试统计工具箱（本项目的"发动机"）
================================================================
把常用检验封装成纯函数，脚本里只关心业务，公式都在这里。

覆盖：
  · 两比例 z 检验（含 CI）            two_prop_test
  · 样本量 / 功效分析                required_sample_size
  · CUPED 方差缩减                   cuped_adjust
  · 均值差的 Bootstrap 置信区间       bootstrap_diff_means
  · 多重比较校正（Bonferroni / Holm） holm_correction
  · 分流比例校验（SRM）              srm_test

方法出处见 ../report.md 文末「参考来源」。
"""
from __future__ import annotations

import numpy as np
from scipy import stats


# ---------------------------------------------------------------- 两比例 z 检验
def two_prop_test(x_c: int, n_c: int, x_t: int, n_t: int, alpha: float = 0.05) -> dict:
    """两比例 z 检验。

    - p 值用**合并比例**估 SE（原假设 p_c = p_t），这是教科书标准做法
    - 置信区间用**非合并** SE（现实里两组方差不必相等）
    """
    p_c, p_t = x_c / n_c, x_t / n_t
    diff = p_t - p_c

    # 合并比例（仅用于检验）
    p_pool = (x_c + x_t) / (n_c + n_t)
    se_pool = np.sqrt(p_pool * (1 - p_pool) * (1 / n_c + 1 / n_t))
    z = diff / se_pool if se_pool > 0 else 0.0
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))

    # 非合并 SE（用于 CI）
    se_diff = np.sqrt(p_c * (1 - p_c) / n_c + p_t * (1 - p_t) / n_t)
    z_crit = stats.norm.ppf(1 - alpha / 2)
    ci = (diff - z_crit * se_diff, diff + z_crit * se_diff)

    return {
        "p_control": p_c, "p_treatment": p_t,
        "abs_lift": diff, "rel_lift": diff / p_c if p_c > 0 else np.nan,
        "se": se_diff, "z": z, "p_value": p_value,
        "ci_low": ci[0], "ci_high": ci[1],
        "significant": p_value < alpha,
    }


def wilson_ci(x: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """单个比例的 Wilson 置信区间（小样本更稳，代码里对比用）。"""
    z = stats.norm.ppf(1 - alpha / 2)
    p = x / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return center - half, center + half


# ---------------------------------------------------------------- 样本量 / 功效
def required_sample_size(p1: float, mde_abs: float, alpha: float = 0.05, power: float = 0.80) -> int:
    """两比例检验的每组所需样本量（双侧）。

    n = (z_{1-α/2} + z_{1-β})² · [p1(1-p1) + p2(1-p2)] / (p2-p1)²

    文献出处：van Belle, Statistical Rules of Thumb（标准两比例样本量公式）。
    """
    p2 = p1 + mde_abs
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(power)
    num = (z_a + z_b) ** 2 * (p1 * (1 - p1) + p2 * (1 - p2))
    return int(np.ceil(num / mde_abs**2))


def achieved_power(p1: float, mde_abs: float, n: int, alpha: float = 0.05) -> float:
    """给定每组样本量 n，回算能检出一个 mde 的功效（用于"实验该跑多久"）。"""
    p2 = p1 + mde_abs
    se = np.sqrt(p1 * (1 - p1) / n + p2 * (1 - p2) / n)
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = (abs(mde_abs) / se) - z_a
    return float(stats.norm.cdf(z_b))


# ---------------------------------------------------------------- CUPED
def cuped_adjust(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, float, float]:
    """CUPED：用实验前协变量 x 对实验期指标 y 做方差缩减。

        θ = Cov(x, y) / Var(x)
        y_cuped = y - θ·(x - E[x])

    理论方差缩减比例 = ρ²(x, y)。
    出处：Deng, Xu, Kohavi & Walker (2013)，WSDM，《Improving the Sensitivity of
    Online Controlled Experiments by Utilizing Pre-Experiment Data》。
    """
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    theta = np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1)
    y_adj = y - theta * (x - x.mean())
    rho = float(np.corrcoef(x, y)[0, 1])
    return y_adj, float(theta), rho


# ---------------------------------------------------------------- Bootstrap
def bootstrap_diff_means(a: np.ndarray, b: np.ndarray, n_boot: int = 10_000,
                         alpha: float = 0.05, seed: int = 42) -> dict:
    """均值差 (b - a) 的 Bootstrap 百分位置信区间。

    重尾指标（如付费金额）不满足正态假设，t 检验会失真，改用重抽样。
    """
    rng = np.random.default_rng(seed)
    a, b = np.asarray(a, float), np.asarray(b, float)
    obs = b.mean() - a.mean()
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        diffs[i] = rng.choice(b, b.size, replace=True).mean() - rng.choice(a, a.size, replace=True).mean()
    lo, hi = np.percentile(diffs, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {
        "diff": obs, "ci_low": lo, "ci_high": hi,
        "boot_se": diffs.std(ddof=1),
        "p_two_sided": 2 * min((diffs <= 0).mean(), (diffs >= 0).mean()),
    }


# ---------------------------------------------------------------- 多重比较
def holm_correction(p_values: dict, alpha: float = 0.05) -> list[dict]:
    """Holm–Bonferroni 逐步校正（比 Bonferroni 更保守度更低、仍然控 FWER）。"""
    items = sorted(p_values.items(), key=lambda kv: kv[1])
    m = len(items)
    out, prev_reject = [], True
    for rank, (name, p) in enumerate(items, start=1):
        threshold = alpha / (m - rank + 1)
        reject = prev_reject and (p <= threshold)
        prev_reject = reject
        out.append({"metric": name, "p_value": p, "threshold": threshold, "significant": reject})
    return out


# ---------------------------------------------------------------- SRM
def srm_test(n_c: int, n_t: int, expected_ratio: float = 0.5, alpha: float = 0.001) -> dict:
    """Sample Ratio Mismatch：分流比例是否符合预期。

    用卡方拟合优度检验。阈值取 0.001（SRM 是"致命错误"，宁可敏感）。
    出处：Microsoft EX-P 平台 SRM 检查实践（Fabijan et al.）。
    """
    total = n_c + n_t
    expected = [total * expected_ratio, total * (1 - expected_ratio)]
    chi2, p = stats.chisquare([n_c, n_t], f_exp=expected)
    return {"chi2": float(chi2), "p_value": float(p), "n_control": n_c, "n_treatment": n_t,
            "observed_ratio": n_c / total, "srm_detected": bool(p < alpha)}
