# 🎮 游戏数据分析知识库 (Game Analytics KB)

> 定位：一个"大厂实战视角"的游戏数据分析知识库 —— 从指标体系到专项分析，从 A/B 实验到 AI 提效
> 作者：7 年数据经验（字节朝夕光年 3 年游戏数据分析 + 制造业 + 金融科技）
> 状态：🚧 建设中（2026-09 启动）

---

## 这个库回答什么问题

对标一线游戏大厂数据分析岗真实 JD（腾讯 IEG《王者荣耀世界》/《三角洲行动》等），覆盖五大能力域：

1. 运营数据分析体系怎么建？
2. 专项分析（流失/画像/版本/活动）怎么做才深入？
3. A/B 测试怎么设计与避坑？
4. 数据能力建设（埋点/数仓/报表）怎么落地？
5. AI 怎么给游戏数据分析提效？

## 目录导航

```
game-analytics-kb/
├── README.md                        # ← 你在这里：门户 + 导航
├── docs/
│   ├── 01-game-basics/              # 游戏业务基础（分析的地基）
│   ├── 02-metrics/                  # 指标体系（核心资产）
│   ├── 03-analysis-frameworks/      # 专项分析框架（JD 最高频）
│   ├── 04-experimentation/          # A/B 测试与因果推断
│   ├── 05-infrastructure/           # 数据基建与工具
│   ├── 06-ai-playbook/              # AI + 游戏数据分析（差异化）
│   └── 07-case-studies/             # 实战复盘（脱敏案例库）
├── projects/                        # 🛠️ 实战项目层（能跑能讲，面试弹药）
│   ├── README.md
│   ├── 01-churn-model/              # 流失预测（SQL + Python，已完成）
│   ├── 02-ab-test/                  # A/B 测试框架（规划中）
│   └── 03-metrics-dashboard/        # 指标体系看板（规划中）
├── templates/
│   └── article-template.md          # 文章模板（RAG 友好）
└── assets/                          # 图片 / 样例数据
```

> 💡 **两层结构**：`docs/` 是理论层（我懂什么），`projects/` 是实战层（我能做出什么）。
> 项目跑完反哺知识库，理论有出处、实践有代码。

## 📚 内容地图

### 01-game-basics 游戏业务基础
| 文档 | 内容 | 优先级 |
|:---|:---|:---|
| business-models.md | F2P / 买断制 / 订阅制，商业模式如何决定分析重点 | P1 |
| game-lifecycle.md | 预热→上线→成熟→衰退，各阶段核心命题 | P1 |
| economy-systems.md | 货币/资源/商城/经济系统，数值与分析的接口 | P2 |

### 02-metrics 指标体系（地基中的地基）
| 文档 | 内容 | 优先级 |
|:---|:---|:---|
| metric-dictionary.md | ⭐ 指标字典与口径统一（DAU/留存/付费/LTV 等一网打尽） | **P0 先写** |
| acquisition.md | 新增、渠道归因、买量成本、ROAS 入门 | P1 |
| retention.md | 留存体系：D1/D7/D30、Cohort、留存曲线形态解读 | P1 |
| monetization.md | ARPU/ARPPU/付费率/LTV/ROAS，商业化指标体系 | P1 |
| engagement.md | 活跃、时长、玩法参与度、社交指标 | P2 |

### 03-analysis-frameworks 专项分析框架（JD 最高频）
| 文档 | 内容 | 优先级 |
|:---|:---|:---|
| user-portrait.md | ⭐ 用户画像与分层（RFM / 生命周期分层 / 画像应用） | **P0** |
| churn-analysis.md | ⭐ 流失分析：预警信号→归因→召回策略闭环 | **P0** |
| version-evaluation.md | 版本/玩法效果评估：怎么证明新版本有没有用 | P1 |
| event-campaign.md | 活动效果评估：活动前后对比的正确姿势 | P1 |
| monetization-analysis.md | 商业化专题：礼包定价、促销、付费深度挖掘 | P2 |

### 04-experimentation A/B 测试与因果
| 文档 | 内容 | 优先级 |
|:---|:---|:---|
| ab-test-design.md | 游戏内 A/B 设计：分流、指标选择、样本量、显著性 | P1 |
| pitfalls.md | 常见坑：辛普森悖论、AA 测试、多重比较、新奇效应 | P1 |
| causal-inference.md | 因果推断入门：DID / 断点 / PS 匹配在游戏的应用 | P3 |

### 05-infrastructure 数据基建与工具
| 文档 | 内容 | 优先级 |
|:---|:---|:---|
| event-tracking.md | 埋点与日志规范（分析师的命根子） | P2 |
| dw-modeling.md | 数仓分层与主题建模（呼应数据治理功底） | P2 |
| reporting.md | 报表体系建设：从日报到自助看板 | P2 |
| sql-recipes.md | 高频 SQL 配方：留存计算/漏斗/窗口函数实战 | P1 |

### 06-ai-playbook AI + 游戏数据分析（差异化卖点）
| 文档 | 内容 | 优先级 |
|:---|:---|:---|
| llm-for-analysts.md | LLM 在游戏分析中的真实用法与边界 | P2 |
| rag-setup.md | 把本知识库做成 RAG 问答系统（项目化） | P2 |
| agent-workflows.md | AI Agent 自动化分析工作流实战 | P3 |

### 07-case-studies 实战复盘（脱敏 · 别人写不出的部分）
| 文档 | 内容 | 优先级 |
|:---|:---|:---|
| churn-recall-case.md | 流失用户召回案例复盘：分析→策略→效果 | P1 |
| version-push-case.md | 版本更新效果评估案例复盘 | P2 |
| …… | 持续补充，每个案例都是"故事" | 长期 |

---

## ✍️ 写作规范（RAG 化友好，每篇必守）

1. **一篇一主题**，500–1500 字，宁可拆篇不要大杂烩
2. **固定结构**：背景 → 框架 → 方法 → 案例 → 要点速记
3. **术语首次出现必须给定义**（RAG 检索时上下文自洽）
4. 每篇开头带元数据块（见 `templates/article-template.md`）
5. 案例一律脱敏：不出现项目名/真实数值，用"某 MOBA 项目"式表述
6. 有数据支撑的结论标注来源或计算方式
7. **✅ 发布前权威源核对（强制）**：事实性内容（定义/基准/框架）必须对照权威来源核对，文末附「参考来源」；无权威来源的数值一律标注为"经验区间/示意"，禁止无出处断言

## 🗺️ 写作路线图

- [x] P0-1：metric-dictionary.md（指标字典）✅ 已核对
- [x] P0-2：churn-analysis.md（流失分析）✅ 已核对
- [x] P0-3：user-portrait.md（用户分层）✅ 已核对
- [x] PRJ-1：projects/01-churn-model 流失预测（SQL+Python 全链路，AUC 0.93）✅ 已跑通
- [ ] P1-1：repo 上线 GitHub（README 门户完善 + git init + 推送）
- [ ] PRJ-2：projects/02-ab-test A/B 测试框架
- [ ] PRJ-3：projects/03-metrics-dashboard 指标体系看板
- [ ] P1-2：retention / monetization / acquisition
- [ ] P1-3：ab-test-design + event-campaign
- [ ] P2：RAG 化改造（向量化 + 问答 demo）
- [ ] 长期：case-studies 持续沉淀

## 📌 维护日志
- 2026-09-09：建立骨架与写作规范
- 2026-09-10：P0 三篇完成并通过权威源核对（GameAnalytics 官方博客等）；确立「发布前权威源核对」强制规范
- 2026-09-11：新增 **projects/ 实战项目层**；PRJ-1 流失预测跑通（合成数据 8,000 用户，AUC 0.93，Top10% 提升度 4.11x），含 SQL 特征提取 + 建模评估 + 分析报告
