# 01 · 游戏用户流失预测

> 一句话：用用户行为数据，提前 7 天识别高流失风险用户，输出可执行的召回名单。
> 技术栈：SQL（特征提取）+ Python（建模评估）｜数据：合成（可一键复现）

---

## 业务问题

游戏运营最贵的成本之一是**获客**。如果能在用户流失前识别出来并干预，等于把买量成本省下来。
本项目的目标：**在 T 时刻，基于历史行为，预测用户在接下来 7 天是否会流失**，并按风险排序输出名单。

## 方法（三步）

```
原始日志(user_daily/profile/purchases)
   │  sql/churn_features.sql   ← 窗口函数把"逐日明细"压成"一人一行"特征
   ▼
特征宽表(features.csv, 25 个特征)
   │  python/02_churn_model.py  ← 逻辑回归 + 梯度提升树
   ▼
流失概率 + 风险分层 → 召回优先级名单
```

**标签口径（关键，先定口径再建模）**
- 特征窗口：2026-01-01 ~ 2026-02-22（用这段时间的行为做特征）
- 标签窗口：2026-02-23 ~ 2026-03-01（这 7 天内**零登录** → churn=1）
- 严禁让模型看到标签窗口的任何信息（防数据泄露）

## 结果（合成数据，seed=42 可复现）

| 指标 | 逻辑回归 | 梯度提升树 |
|:---|:---:|:---:|
| AUC | 0.933 | **0.933** |
| PR-AUC | 0.837 | **0.839** |
| KS | **0.705** | 0.704 |

> 业务真正看的是 **Lift**：取出**风险最高的 10% 用户**，覆盖了全部流失用户的 **41%**，提升度 **4.11x**
> （即：随机捞 10% 只能命中 10%，模型捞 10% 命中率是它的 4 倍）

## 怎么跑

```bash
pip install -r requirements.txt
python data/generate_data.py      # 1. 生成合成数据（~3 秒）
python python/build_features.py   # 2. SQL 提特征
python python/01_eda.py           # 3. 探索性分析
python python/02_churn_model.py   # 4. 建模评估 → data/churn_scores.csv
```

## 目录

| 路径 | 内容 |
|:---|:---|
| `data/generate_data.py` | 合成数据生成器（模拟真实游戏日志结构） |
| `sql/churn_features.sql` | 特征提取（CASE 聚合 + 窗口口径，可移植 Hive/MySQL） |
| `python/build_features.py` | 原始 CSV → SQLite → 跑 SQL → 特征宽表 |
| `python/01_eda.py` | 单变量区分度、流失曲线、渠道对比 |
| `python/02_churn_model.py` | 建模、评估、打分名单 |
| `report.md` | **完整分析报告（含结论与业务建议）** |

## 设计说明（面试常被问）

- **为什么用合成数据？** 公司数据不能带出来；合成数据可复现、无隐私风险，且能演示完整链路。
- **为什么既有 SQL 又有 Python？** 特征工程用 SQL（贴近生产数仓），建模评估用 Python —— 两段各司其职。
- **为什么选这两个模型？** 逻辑回归可解释、可做打分卡上生产；GBDT 探性能上限。二者 AUC 接近，故以可解释性更高的**逻辑回归**也能打平。
- **下一步可做**：时间切分验证、PSI 稳定性监控、SHAP 归因、召回 ROI 闭环。

## 参考来源
- 流失/分群分析方法论：GameAnalytics 官方博客 —— Player segmentation（https://www.gameanalytics.com/blog/player-segmentation-segmentiq）
- 评估指标定义：scikit-learn 官方文档 —— Model evaluation（ROC-AUC / Average Precision：https://scikit-learn.org/stable/modules/model_evaluation.html）
- 本项目中所有数值均由 `seed=42` 的合成数据产生，**非真实业务数据**，仅用于演示方法
