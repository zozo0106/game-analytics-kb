---
title: 新增与买量分析：归因、成本与 ROAS 入门
tags: [新增, 买量, 渠道归因, CPI, ROAS, 增量实验, 多触点归因]
game_type: [F2P]
scene: 买量与增长
difficulty: 进阶
updated: 2026-09-16
---

# 新增与买量分析：归因、成本与 ROAS 入门

> 一句话摘要：买量分析的入门错觉是"看归因报表排名"。真正的分水岭在于一个认知——**归因收入（attributed）不等于增量收入（incremental）**。这篇文章讲清渠道归因、成本口径、ROAS 回收，以及为什么要用增量实验来验证。

> ✅ 核对状态：归因与增量方法学已对照 ACM KDD/ADKDD 与 Journal of Marketing Research 文献核对；成本与 ROAS 基准为**行业经验参考区间**。

## 背景

增长团队每天面对的灵魂拷问：**"这条渠道值不值得继续投？"**

最直觉的答案是看投放后台的归因报表：花了多少钱、带回多少收入、ROAS 多少。但这套逻辑有个致命漏洞——**归因报表会把"本来就会来的用户"也算成广告的功劳**。

一个用户可能刷到了广告，但他本来就会通过应用商店搜索安装。归因模型（尤其 last-click）会把这笔功劳记给广告，于是**广告的"账面回报"被系统性高估**。

## 框架：获客漏斗 + 三种口径 + 一个验证

**1. 获客漏斗（找流失环节）**

`曝光 → 点击 → 安装 → 注册 → 激活（次留/首充）→ 付费`

各环节转化率（CVR）是买量优化的抓手；**别只看 CPI，要看"哪个环节掉了"**。

**2. 三种成本口径（别混用）**

| 口径 | 公式 | 适用 |
|:---|:---|:---|
| CPI | 花费 ÷ 安装数 | 粗筛渠道质量 |
| CPA | 花费 ÷ 完成目标行为人数 | 目标可设为注册/次留/首充，更接近业务 |
| CPM/CPC | 千次曝光 / 单次点击 | 投放侧定价与竞价诊断 |

**3. 归因模型（口径决定结论）**

- **Last-click**：把功劳全给最后一次点击。简单，但**高估转化前触点**，且极易把自然量算成付费渠道的业绩
- **First-click**：给首次触点，利于评估"拉新曝光"
- **多触点（数据驱动）**：用 **Shapley 值 / 马尔可夫链**把功劳分摊到各触点（Shao & Li 2011）；更公平但需要数据积累

> 归因窗口（1 天 / 7 天）与去重逻辑会直接改变渠道排名——**报表口径不写清，渠道对比就没有意义**。

**4. 一个验证：增量实验（关键认知）**

归因只能回答"谁被记功"，不能回答"没有这广告会怎样"。要测**增量（incrementality）**，需要真正的对照组：

- **Ghost Ads / PSA（公益广告对照）**：给对照组展示无关广告，制造"未被投放"的反事实（Johnson, Lewis & Nubbemeyer 2017）
- **Geo 实验**：按地区随机开/关投放，比较地区级增量
- **因果归因**：不是"分摊功劳"，而是估计"某触点是否**导致了**转化"（Dalessandro et al. 2012）

**实践铁律**：**归因值 ≥ 增量值**。归因收入通常高于真实增量，差额就是"自然量劫持"（organic cannibalization）。

## 方法（落地要点）

- **ROAS 看回收节奏**：D1 / D7 / D30 ROAS 曲线决定你能承受多贵的 CPI。快回收品类可激进，慢热品类必须先算 LTV/CAC。
- **LTV/CAC 是终局判据**：经验区间常以 **> 3** 为健康线（<1 即越买越亏）；⚠️ 这是经验阈值，非学术标准，且必须用**分渠道的 LTV**而非全局 LTV。
- **新渠道先"小额增量实验"再放量**：直接放量后你会无法区分"渠道有效"和"渠道抢了自然量"。
- **警惕归因口径切换的假信号**：换归因模型/窗口后渠道排名大变，往往不是业务变了，是口径变了。
- **看结构而不是只看总量**：渠道新增留存/付费结构差 → 会长期拖累大盘（详见 [留存体系](retention.md)）。

## 案例（脱敏，数值为合成示意）

某手游两个买量渠道，投放后台数据：

| 渠道 | CPI | 归因 D7 ROAS | 归因 D30 ROAS |
|:---|:---:|:---:|:---:|
| A（信息流） | 8.5 元 | 0.42 | 0.95 |
| B（垂直社区） | 11.0 元 | 0.55 | 1.30 |

初判：B 更优（D30 ROAS 更高），尽管更贵。

数据侧复核：
1. **增量实验（Ghost Ads）**：A 的真实增量约为归因的 **60%**，B 约为 **85%** → B 的"账面"更接近真实
2. **自然量校验**：B 的主投地区在投放开启前后，**自然量同步上涨** → 说明 B 有一部分"劫持自然量"的成分（但比例小于 A）
3. **口径校验**：把归因窗口从 1 天改到 7 天，A 的 ROAS 从 0.30 跳到 0.42——**波动主要来自口径，不是业务改善**

结论：**B 仍更优，但优势没有后台数字显示的那么大**；更重要的是，A 的高归因值被证明有相当比例是自然量劫持 → 建议 A 缩量、B 谨慎放量并继续用增量实验监控。

## 要点速记

- [ ] **归因 ≠ 增量**：归因收入通常高于真实增量，差额 = 自然量劫持
- [ ] 口径必须写死：**归因模型 + 归因窗口 + 去重逻辑**，否则渠道排名不可比
- [ ] 多触点归因用 **Shapley / 马尔可夫链**，比 last-click 更公平（但需数据积累）
- [ ] 验证增量靠实验：**Ghost Ads / PSA / Geo 实验**，不是看后台报表
- [ ] **ROAS 分 D1/D7/D30 看回收节奏**；LTV/CAC 健康线为经验区间（常 >3）
- [ ] 用**分渠道 LTV** 而非全局 LTV 做决策
- [ ] 新渠道先小额增量实验，再放量

## 延伸阅读
- [商业化指标体系：ARPU/ARPPU/付费率/LTV/ROAS](monetization.md)
- [留存体系：D1/D7/D30 与留存曲线](retention.md)
- [A/B 测试设计：从假设到决策的完整流程](../04-experimentation/ab-test-design.md)
- [活动效果评估：无法做 A/B 时怎么算清"增量"](../03-analysis-frameworks/event-campaign.md)

## 参考来源
- 数据驱动多触点归因：Shao & Li (2011), *Data-driven Multi-touch Attribution Models*, Proceedings of the 17th ACM SIGKDD International Conference on Knowledge Discovery and Data Mining. DOI:10.1145/2020408.2020453
- 因果归因（不止分摊功劳，而是估计因果效应）：Dalessandro, Perlich, Stitelman & Provost (2012), *Causally Motivated Attribution for Online Advertising*, Proceedings of the Sixth International Workshop on Data Mining for Online Advertising and Internet Economy (ADKDD), ACM. DOI:10.1145/2351356.2351363
- 广告增量测量（Ghost Ads / PSA 对照设计）：Johnson, Lewis & Nubbemeyer (2017), *Ghost Ads: Improving the Economics of Measuring Online Ad Effectiveness*, Journal of Marketing Research 54(6):867–884. DOI:10.1509/jmr.15.0297
- 实验与增量思维：Kohavi, Tang & Xu (2020), *Trustworthy Online Controlled Experiments*, Cambridge University Press. DOI:10.1017/9781108653985
- 渠道成本与 ROAS 基准：GameAnalytics 行业 Benchmark 报告 — https://gameanalytics.com/reports （⚠️ 基准随品类、年份、地区浮动）
- 注：案例数值为合成示意，**非真实业务数据**；LTV/CAC > 3 为经验区间，非学术标准
