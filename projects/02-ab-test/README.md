# 02 · A/B 测试分析框架

> 一句话：从**实验设计**到**决策建议**的完整 A/B 测试流水线 —— 不只算 p 值，更能识别"看起来赢了其实输了"的坑。
> 技术栈：SQL（指标提取）+ Python（统计检验）｜数据：合成（可一键复现）

---

## 业务问题

游戏做了个**新版每日任务系统**，想验证它到底有没有用。但"看数据涨了"和"证明是这次改动带来的"是两回事：
涨了可能是大盘自然波动、可能是新奇效应、可能是分流不均、也可能是你测了 10 个指标挑的那个恰好显著。

本项目的目标：**给定一次 A/B 实验，输出可信的因果结论 + 上线/不上的决策建议**，并能识别数据里的四类陷阱。

## 方法（四步）

```
实验日志(users/daily)
   │  sql/experiment_metrics.sql   ← 累加/条件聚合，把"每日明细"压成"一人一行"指标
   ▼
指标宽表(ab_features.csv, 12 列)
   │  python/01_design_and_srm.py  ← 先体检：功效 / 分流 / 分层均衡
   ▼
   │  python/02_abtest.py          ← 再检验：主指标 + CUPED + 多重比较校正
   ▼
   │  python/03_pitfalls.py        ← 后验坑：新奇效应 / 辛普森悖论 / 假阳性
   ▼
决策建议（上线 / 不上线）+ 效应量置信区间
```

**口径（先定口径，再谈显著性）**
- 分流单元：用户（user_id），对照组 / 实验组各约 10,000 人，比例 1:1
- 主指标：`retained_d7` = 第 7 天是否活跃（0/1）
- 次指标：`payer_7d`（付费率）、`matches_7d`（人均对局）、`revenue_7d`（人均付费）
- 观测窗口：实验前 7 天（指标口径）；实验前 14 天（CUPED 协变量）

## 结果（合成数据，seed=42 可复现）

**前置体检（全绿才敢读结论）**

| 检查项 | 结果 | 判断 |
|:---|:---|:---:|
| 功效分析 | 基线 61.22%，检出 2pp 需每组 9,222 人，实有 ~10,000 | ✅ 足够 |
| SRM 分流 | 9,938 vs 10,062，实际占比 0.4969，χ²=0.77，p=0.38 | ✅ 正常 |
| 分层均衡 | 渠道 p=0.16 / 设备 p=0.66 | ✅ 均衡 |
| 实验前 AA | 三个前置指标 p 均 > 0.20 | ✅ 无差异 |

**主指标：D7 活跃率**

> 对照组 61.22% → 实验组 63.29%，**绝对提升 +2.07pp（相对 +3.38%）**
> 95% CI [+0.72pp, +3.41pp]，z=3.02，**p=0.0026 → 显著**

**CUPED 方差缩减**（协变量 = 实验前 14 天对局数）

> ρ(前, 后) = 0.761 → **方差缩减 58.1%**，标准误降低 35.3%
> 置信区间宽度从 0.584 收窄到 0.378（同样数据、更确定的结论）

**次指标 + 多重比较校正（Holm）**

| 指标 | 对照 → 实验 | 提升 | 校正后仍显著 |
|:---|:---:|:---:|:---:|
| 人均对局数 | 10.867 → 12.203 | **+12.29%** | ✅ |
| 人均付费 | 4.067 → 4.309 | +5.96% | ❌（重尾、样本不足） |
| 付费率 | 17.59% → 18.19% | +3.40% | ❌ |

**决策建议：上线**（主指标显著为正；对局数大幅提升；需继续观察付费类指标）

## 三个坑（数据实测，非纸上谈兵）

| 坑 | 实测证据 | 教训 |
|:---|:---|:---|
| **新奇效应** | 提升第 1 天 +5.60pp → 第 7 天 +2.07pp → 第 14 天 **+0.23pp**（衰减到 4%） | 只看首日会严重高估；至少要跑满一个周期 |
| **多重比较** | 2,000 次 AA 测试假阳性率 5.3%；一次看 10 个指标，族错误率高达 **40.1%** | 先定主指标；次指标必须做 Holm/Bonferroni 校正 |
| **辛普森悖论** | 整体 +7.20pp（p<0.001 显著），但拆开看：自然量 **−1.67pp**、买量 **−2.31pp**（都显著为负） | 分流与人群相关时整体均值毫无意义；结论前必做分层 |

> 辛普森悖论的成因：坏实验里实验组的自然量用户占比 80%（对照组仅 20%）—— **随机化被破坏**。

## 怎么跑

```bash
pip install -r requirements.txt
python data/generate_data.py       # 1. 生成合成实验数据（20,000 用户 × 14 天）
python python/build_features.py    # 2. SQL 提指标
python python/01_design_and_srm.py # 3. 前置体检：功效 / SRM / 分层均衡
python python/02_abtest.py         # 4. 显著性检验 + CUPED + 多重比较
python python/03_pitfalls.py       # 5. 三个坑的实测演示
```

## 目录

| 路径 | 内容 |
|:---|:---|
| `data/generate_data.py` | 合成数据生成器（含新奇效应、真实效应"上帝视角"） |
| `sql/experiment_metrics.sql` | 用户级指标宽表（可移植 Hive/MySQL） |
| `sql/daily_trend.sql` | 分日趋势（看新奇效应） |
| `python/ab_lib.py` | 统计工具箱（z 检验 / 样本量 / CUPED / Bootstrap / Holm / SRM） |
| `python/01_design_and_srm.py` | 实验可信度前置检查 |
| `python/02_abtest.py` | 主分析：检验 + CUPED + 校正 + 决策 |
| `python/03_pitfalls.py` | 三类陷阱实测 |
| `report.md` | **完整实验报告（含分层结论与上线建议）** |

## 设计说明（面试常被问）

- **为什么先做 SRM 再看好坏？** 分流比例失衡意味着数据链路有 bug（埋点、缓存、分流不一致），此时任何显著性都不可信。SRM 是"一票否决"检查。
- **为什么主指标只有 1 个？** 实验的核心问题只能有 1 个答案；次指标是辅助观察，必须做多重比较校正，否则"测得多"必然"显著多"。
- **连续指标怎么选检验？** 对局数近似正态 → Welch t 检验；付费金额重尾（少数大 R 拉偏均值）→ 正态假设崩了，改用 Bootstrap 重抽样。
- **CUPED 为什么有效？** 用实验前行为做协变量，把用户固有差异"扣掉"，等价于凭空多出样本量。本项目 ρ=0.76 → 方差砍掉一半以上。
- **下一步可做**：序贯检验（Early Stopping 防偷看）、Delta Method 处理比值指标（如 ARPU/DAU）、多层实验（层/域正交）、异质性处理效应（HTE/因果森林）。

## 参考来源

- 两比例 z 检验：NIST/SEMATECH e-Handbook of Statistical Methods, §7.3.3（https://www.itl.nist.gov/div898/handbook/prc/section3/prc33.htm）
- 样本量推导：NIST e-Handbook §7.2.4.2（https://www.itl.nist.gov/div898/handbook/prc/section2/prc242.htm）；Evan Miller A/B Sample Size Calculator（https://www.evanmiller.org/ab-testing/sample-size.html）
- CUPED：Deng, Xu, Kohavi & Walker (2013), *Improving the Sensitivity of Online Controlled Experiments by Utilizing Pre-Experiment Data*, WSDM. DOI:10.1145/2433396.2433413
- SRM 检查：Fabijan et al. (2019), *Diagnosing Sample Ratio Mismatch in Online Controlled Experiments*, KDD. DOI:10.1145/3292500.3330722
- Wilson 置信区间：Wilson (1927), *Probable Inference, the Law of Succession, and Statistical Inference*, JASA. DOI:10.1080/01621459.1927.10502953
- Holm 校正：Holm (1979), *A Simple Sequentially Rejective Multiple Test Procedure*, Scandinavian Journal of Statistics 6(2):65–70
- Bootstrap：Efron & Tibshirani (1993), *An Introduction to the Bootstrap*, Chapman & Hall
- 新奇效应与陷阱综述：Kohavi, Tang & Xu (2020), *Trustworthy Online Controlled Experiments*, Cambridge University Press
- ⚠️ 本项目中所有数值均由 `seed=42` 的合成数据产生，**非真实业务数据**，仅用于演示方法（真实效应已在 `data/ground_truth.json` 中保存用于框架自检）
