---
title: A/B 测试设计：从假设到决策的完整流程
tags: [AB测试, 实验设计, 因果推断, 指标体系, 分流]
game_type: [全品类]
scene: 实验设计与效果评估
difficulty: 入门
updated: 2026-09-15
---

# A/B 测试设计：从假设到决策的完整流程

> 一句话摘要：A/B 测试（随机对照实验）是游戏里唯一能回答"这次改动到底有没有用"的方法。本文给出一套可落地的六步设计流程，并说明游戏行业做实验的特殊约束。

## 背景

游戏运营里最常见的争论是"这个改动到底有没有用"：新版任务系统上线后 D7 留存涨了——是改动有效，还是版本节点、买量结构变化、大盘季节性造成的？**观测到的相关不等于因果**。A/B 测试通过**随机分组**把"是否受到改动影响"变成唯一变量，从而给出因果结论：这是它不可替代的价值。

但游戏行业做实验有自己的约束：DAU 有限、社交关系会互相影响、客户端版本不像 Web 能秒级灰度。所以"照搬互联网那套"经常翻车，需要专门设计。

## 框架：A/B 测试设计六步

**第一步 · 定假设与决策规则（实验前锁定）**
- 写成可证伪的命题："新版任务系统能提升 D7 活跃率"
- 明确判据："主指标显著且方向为正 → 上线；否则不上线"
- ⚠️ 规则必须在**看数据之前**定下来，否则会退化成"挑一个显著的指标来支持已定的结论"

**第二步 · 定指标：一个主指标 + 若干护栏指标**
- **主指标（OEC, Overall Evaluation Criterion）**：只能有一个，直接对应假设（如 D7 活跃率）
- **次指标**：辅助观察（如人均对局数），但必须做多重比较校正（见 [常见坑](pitfalls.md)）
- **护栏指标（Guardrail）**：只允许不劣化，如崩溃率、客服工单、退款率、核心付费指标

**第三步 · 定分流单元与随机化**
- **单元（unit）**：按用户（`user_id`）优于按设备，避免同人跨设备污染；有社交依赖时甚至要按**地域/公会**成组随机
- **比例**：通常 1:1；极端场景（怕伤体验）可用小流量实验组
- **校验**：上线后先跑 **SRM 检查**（Sample Ratio Mismatch，样本比例失配）——实测比例与设计比例显著偏离，说明分流链路有 bug，此时任何结论都不可信

**第四步 · 算样本量与时长**
- 输入：基线转化率、想检出的最小效应（**MDE, Minimum Detectable Effect**）、显著性水平 α（常取 0.05）、功效 power（常取 0.80）
- 输出：每组所需样本量 → 换算成实验天数
- ⚠️ **时长至少要覆盖一个完整行为周期**（如每日任务看 7 天、赛季看整赛季），否则读到的是短期脉冲而非稳态效应

**第五步 · 跑实验并监控**
- 观察 SRM、护栏指标、数据管道健康度；**不因为"看到显著"就提前停**（会抬高假阳性，见 pitfalls）
- 需要边跑边看，就用**序贯检验 / always-valid 推断**

**第六步 · 分析与决策**
- 算效应量 + 置信区间（而不只是 p 值）；做**分层检验**防辛普森悖论；必要时用**方差缩减**（如 CUPED）
- 输出一句话决策：上线 / 不上线 / 再迭代

## 游戏行业的特殊约束（实战重点）

| 约束 | 问题 | 应对 |
|:---|:---|:---|
| **网络效应 / 溢出** | 实验组和对照组在同一匹配池、公会里互相影响，违反"个体处理独立性"假设 | 按地域/公会/服务器成组随机（cluster randomization），或隔离匹配池 |
| **版本不可拆** | 客户端大版本无法对半灰度 | 用整包灰度 + 版本前后对比（quasi-experiment），或只对服务端可控项做 A/B |
| **DAU 太小** | 分不出有统计意义的流量 | 拉长周期、用 CUPED 降方差、或用**配对设计**；必要时改用准实验 |
| **新奇效应** | 新东西刚上线用户图新鲜，效果虚高 | 看满完整周期；设长期 holdout 组观察稳态 |

**方差缩减（CUPED）**：用实验前的用户行为做协变量，扣掉用户固有差异，能在不增加流量的前提下显著收窄置信区间。以本知识库 PRJ-2 示例数据为例：ρ(实验前, 实验期)=0.76 时，方差缩减约 58%，等效于把样本量摊大 2 倍以上（原理见参考来源 Deng et al.）。

## 案例（脱敏，数值为合成演示）

某项目新版每日任务系统做 A/B：分流单元为用户，1:1，主指标 D7 活跃率，周期 14 天。前置检查全绿（SRM p=0.38、分层/AA 均衡），主指标 **61.2% → 63.3%（+2.07pp，p=0.0026）**，判据满足 → 决策上线；但分日看出来提升从第 1 天 +5.6pp 衰减到第 14 天 +0.23pp（新奇效应），因此同步建议设长期 holdout 组复验。

## 要点速记

- [ ] A/B 的价值是**因果**：随机化让"是否受改动影响"成为唯一变量
- [ ] 决策规则、主指标必须**在实验前锁定**，否则就是事后挑数据
- [ ] 一个主指标（OEC）+ 若干护栏指标；次指标要看，但必须多重比较校正
- [ ] 先查 SRM 再读结论——分流比例失衡意味着数据链路有 bug，一票否决
- [ ] 样本量由"基线 + MDE + α + power"决定；实验时长至少覆盖一个完整行为周期
- [ ] 游戏做实验要处理网络效应（成组随机）和版本不可拆（灰度/准实验）两大特殊问题

## 延伸阅读
- [A/B 测试常见坑](pitfalls.md)
- [指标字典：留存/活跃口径](../02-metrics/metric-dictionary.md)
- [实战项目：A/B 测试分析框架（含完整代码与报告）](../../projects/02-ab-test/)

## 参考来源
- 样本量与两比例检验：NIST/SEMATECH e-Handbook of Statistical Methods §7.2.4.2、§7.3.3 — https://www.itl.nist.gov/div898/handbook/prc/section2/prc242.htm ｜ Evan Miller, A/B Sample Size Calculator — https://www.evanmiller.org/ab-testing/sample-size.html
- 实验方法学总纲（OEC、护栏指标、网络效应、novelty effect）：Kohavi, Tang & Xu (2020), *Trustworthy Online Controlled Experiments*, Cambridge University Press. DOI:10.1017/9781108653985
- 大规模在线实验实践：Kohavi, Deng, Frasca, Walker, Xu & Pohlmann (2013), *Online Controlled Experiments at Large Scale*, KDD. DOI:10.1145/2487575.2488217
- CUPED 方差缩减：Deng, Xu, Kohavi & Walker (2013), *Improving the Sensitivity of Online Controlled Experiments by Utilizing Pre-Experiment Data*, WSDM. DOI:10.1145/2433396.2433413
- SRM 检查：Fabijan et al. (2019), *Diagnosing Sample Ratio Mismatch in Online Controlled Experiments*, KDD. DOI:10.1145/3292500.3330722
- 连续监控 / 序贯推断：Johari, Koomen, Pekelis & Walsh (2022), *Always Valid Inference: Continuous Monitoring of A/B Tests*, Operations Research. DOI:10.1287/opre.2021.2135
- 案例数值来自本知识库合成数据项目 `projects/02-ab-test`（seed=42 可复现），**非真实业务数据**
