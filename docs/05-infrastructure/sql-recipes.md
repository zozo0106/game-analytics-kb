---
title: 高频 SQL 配方：留存、漏斗与窗口函数实战
tags: [SQL, 窗口函数, 留存计算, 漏斗, CTE, 口径统一]
game_type: [全品类]
scene: 数据提取 / 指标计算
difficulty: 入门
updated: 2026-09-16
---

# 高频 SQL 配方：留存、漏斗与窗口函数实战

> 一句话摘要：分析师 80% 的时间在写 SQL，但真正拉开差距的不是"会不会写"，而是**口径能不能统一、结果能不能复现**。这篇给出四组可直接抄的配方（留存 / 漏斗 / 连续活跃 / 窗口 frame 陷阱），以及一份反模式清单。

> ✅ 核对状态：窗口函数语法与 frame 默认值已对照 PostgreSQL 官方文档核对；基数估计（HyperLogLog）引原文；下方所有 SQL 均在本机 sqlite3（Python 标准库）**实际执行过**，数字为实测输出（合成数据，**非真实业务数据**）。窗口函数 / CTE 属 SQL 标准语法，PostgreSQL、MySQL 8+、Hive/Spark SQL 通用；各引擎差异见文末说明。

## 背景

同一个指标，两个人写出两个数——这是数据团队最贵的成本。**"D7 留存 23%" 和 "D7 留存 19%" 争一上午，最后发现是口径不同**：一个算"恰好第 7 天活跃"，一个算"第 7 天及之后活跃过"。

SQL 不只是取数工具，**它其实就是口径本身**：JOIN 的粒度、去重的位置、窗口 frame 的选择，每一处都在悄悄定义指标的含义。配方固定下来，口径才能固定下来。

## 框架：四组配方 + 一份反模式清单

| 配方 | 解决什么 | 核心技巧 |
|:---|:---|:---|
| ① 留存 | N-day 固定日 / 滚动留存 | 先建"用户×天"宽表，再按 `day_n` 条件聚合 |
| ② 窗口 frame | 累计值算错 | 显式写 frame，别依赖默认值 |
| ③ 连续活跃 | 粘性、连续登录奖励 | gaps & islands（日期 − ROW_NUMBER 差法） |
| ④ 有序漏斗 | 步骤转化率虚高 | 取"到当前行为止的最大步号"再过滤 |

## 方法

### ① 留存：先统一到"用户 × 天"宽表

```sql
-- day_n = 活跃日 − 注册日；一张宽表把两种口径的差异摊在明面上
WITH base AS (
  SELECT u.user_id, a.dt AS act_dt,
         CAST(julianday(a.dt) - julianday(u.reg_dt) AS INT) AS day_n
  FROM users u JOIN active_events a ON a.user_id = u.user_id
)
SELECT
  COUNT(DISTINCT CASE WHEN day_n = 7  THEN user_id END) AS d7_fixed,      -- 固定日
  COUNT(DISTINCT CASE WHEN day_n >= 7 THEN user_id END) AS d7_unbounded   -- 滚动
FROM base;
```

**关键点**：`COUNT(DISTINCT user_id)` 必须在聚合前去重——事件表里一个用户一天可能有多行，不去重就会算出"留存率 > 100%"这种经典事故。分母（当日新增用户数）要来自**用户表**，不是事件表。

### ② 窗口 frame：默认是"累计"，不是"全分区"

官方文档写得很清楚：**默认 frame 是 `RANGE UNBOUNDED PRECEDING`**，等价于 `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`——即"从分区第一行到当前行"。所以 `SUM(x) OVER (ORDER BY dt)` 得到的是**累计值**，不是全表总和。要全量必须显式指定：

```sql
SUM(dau) OVER (ORDER BY dt)                                                    -- 累计
SUM(dau) OVER (ORDER BY dt ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)  -- 全分区
```

同一份数据实测（`LIMIT 3`）：`55 / 181 / 236`（累计）对 `443 / 443 / 443`（全量）。**写 `ORDER BY` 却不写 frame，是分析师最常犯的隐性错误。**

### ③ 连续活跃天数：日期 − 行号 = 分组 ID

连续区间（gaps & islands）的标准解法：**在连续区间内，"日期序数 − 行号"是常数**。

```sql
WITH act AS (SELECT DISTINCT user_id, dt FROM active_events),
grp AS (SELECT user_id, dt,
        CAST(julianday(dt) AS INT) - ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY dt) AS island
        FROM act)
SELECT user_id, COUNT(*) AS streak FROM grp GROUP BY user_id, island ORDER BY streak DESC;
```

同一用户若中断一天，`island` 值就分叉成两段，`GROUP BY` 自然切出两个连续区间。**`DISTINCT` 是必须的**——去重保证一天一行，否则行号会错位。

### ④ 有序漏斗：别用"是否到过某步"

漏斗最常见的错误是**只判断"到过第 N 步"而不看顺序**——回退、乱序事件都会让转化率虚高。正确做法是先算"到当前行为止的最大步号"，再要求该行步号 == 最大步号：

```sql
WITH ordered AS (
  SELECT user_id, step, ts,
         MAX(step) OVER (PARTITION BY user_id ORDER BY ts
                         ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS max_step
  FROM funnel)
SELECT step, COUNT(DISTINCT user_id) FROM ordered WHERE step = max_step GROUP BY step;
```

### 反模式清单

- **`SELECT *`**：数仓里意味着全列扫描，还可能把 `cardinality` 大到爆的中间列带出来
- **先 JOIN 再过滤**：把过滤条件（分区/日期）下推到最内层子查询，能少扫几个数量级的行
- **用 `COUNT(DISTINCT)` 处理超大基数**：精确去重是内存杀手，亿级 UV 用 HyperLogLog 类近似（误差约 2%）
- **`GROUP BY` 后不看行数变化**：聚合前后行数、金额合计对不上，说明 JOIN 发生了放大

## 案例（本机实测 · 合成数据）

**背景**：某 SLG 的新手引导效果评估，两人用同一份日志算 D7 留存，结果差了近一倍——**26% vs 51.5%**。

**分析过程**：把两种口径写进同一条 SQL（配方 ①），跑出来：**D7 固定日 26.00%，D7 滚动 51.50%**（D1 为 63.00% / 88.50%）。差异来源不是数据错了，而是**口径不同**：固定日回答"第 7 天当天来没来"，滚动回答"第 7 天起还活着没"。

**结论**：**两个数都对，但不能混用**。评估"新手引导是否成功"看**固定日**（对节奏敏感）；看"整体活跃池子有多大"看**滚动**（对流失敏感）。

**实际效果**：把口径写进指标字典后，同类争论从"每次吵"变成"查文档"；报表里两个口径分列展示，并明确标注分母口径。

## 要点速记

- [ ] SQL 就是口径：JOIN 粒度、去重位置、窗口 frame 都在定义指标，**不是实现细节**
- [ ] 留存先统一到"用户×天"宽表，**`COUNT(DISTINCT user_id)` 必须在聚合前去重**，分母来自用户表
- [ ] **N-day 固定日 ≠ 滚动留存**：实测 26% vs 51.5%，两个都对但不能混用，必须写进指标字典
- [ ] 窗口函数**默认 frame 是"到当前行"（累计）**，要全分区必须显式写 `UNBOUNDED FOLLOWING`
- [ ] 连续区间用"日期 − 行号"差法；有序漏斗必须先取"到当前为止最大步号"再过滤
- [ ] 性能三件套：过滤下推、避开 `SELECT *`、超大基数用近似去重（HyperLogLog 误差约 2%）

## 延伸阅读

- [指标字典与口径统一](../02-metrics/metric-dictionary.md) —— 口径写下来的地方，SQL 配方的上游
- [留存体系：D1/D7/D30、Cohort 与留存曲线](../02-metrics/retention.md) —— N-day vs 滚动的业务解读
- [流失分析：预警信号 → 归因 → 召回闭环](../03-analysis-frameworks/churn-analysis.md) —— 连续活跃/流失判定的下游应用
- [PRJ-1 流失预测（SQL + Python 可运行代码）](../../projects/01-churn-model/) —— 这些配方的工程化落地

## 参考来源

- PostgreSQL Global Development Group, *PostgreSQL 18 Documentation*：Window Functions（`first_value`/`last_value`/peers）、SELECT 表达式一节 —— "The default framing option is `RANGE UNBOUNDED PRECEDING`, which is the same as `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`." — https://www.postgresql.org/docs/current/sql-expressions.html
- Flajolet, Fusy, Gandouet & Meunier (2007), *HyperLogLog: the analysis of a near-optimal cardinality estimation algorithm*, DMTCS Proceedings. DOI:10.46298/dmtcs.3545（近似去重与 ~2% 标准误差出处）
- Kellenberger & Groom (2015), *Expert T-SQL Window Functions in SQL Server*, Apress. DOI:10.1007/978-1-4842-1103-8（窗口函数工程实践）
- 引擎差异：本文 SQL 在 sqlite3 实跑验证；`julianday()` 为 sqlite 函数，PostgreSQL 用 `date1 - date2`，Hive/Spark 用 `datediff()`，其余（CTE、`ROW_NUMBER`、frame 语法）为标准语法
