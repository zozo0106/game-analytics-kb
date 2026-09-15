# 04 · 知识库 RAG 问答（把知识库变成可检索的 AI 问答）

> 一句话：给这套游戏数据分析知识库接上一个**可评测、可拒答**的检索问答层 —— **零 API key、离线可复现**。
> 技术栈：BM25（稀疏）+ LSA（稠密）+ RRF 融合 + 抽取式作答｜评测：42 题标注 + 5 题域外

---

## 业务问题

知识库写多了，新的问题就来了：**"这些文档我自己都记不住，别人更不会翻。"**

直接上 LLM 行不行？不行——**LLM 不知道你库里的口径**（"我们的 ARPU 分母是 DAU 还是付费用户？"），硬答就是编。所以需要 RAG（检索增强生成）：**先从知识库检索证据，再基于证据作答**。

而做 RAG 的人最容易忽略的一点：**瓶颈几乎总在检索层，不在生成层**。检索没把对的段落捞出来，再强的模型也只能胡说。所以这个项目**把评测做在检索上**。

## 架构

```
docs/**.md（10 篇知识库）
   │  分块：按 Markdown 二级标题切（文档 › 章节），标题路径一并入索引
   ▼
72 个 chunk
   ├─ 稀疏：BM25（中文用「单字 + 双字 bigram」，不依赖分词器）
   └─ 稠密：TF-IDF → TruncatedSVD(LSA) → 余弦
   ▼  RRF 倒数排名融合
Top-K 证据
   ▼  抽取式作答（挑最相关句子）+ 引用来源
答案 + 可点开的出处
```

**为什么用 LSA 而不是 sentence-transformers？** 为了让整个项目**离线可复现、零依赖、可评测**。LSA 可以理解为"离线版 embedding"——想换成真向量模型，改 `LsaEncoder` 一个类就行，其余代码不动（见下方「升级路径」）。

## 怎么跑

```bash
pip install -r requirements.txt

python python/build_index.py      # 1. 建索引（分块 + BM25 + LSA）→ data/index.pkl
python python/ask.py "N-day 留存和不固定日留存有什么区别？"
python python/ask.py --interactive          # 交互问答
python python/ask.py "归因和增量差在哪" --show-prompt   # 打印可投喂任意 LLM 的 prompt
python python/eval_retrieval.py   # 2. 检索评测 → 指标表 + assets/retrieval_metrics.png
python python/ablation_heading.py # 3. 消融实验：标题路径要不要进索引
```

## 评测结果（42 题标注 · 10 篇 / 72 块）

| 检索模式 | Recall@1 | Recall@3 | Recall@5 | MRR |
|:---|:---:|:---:|:---:|:---:|
| BM25（稀疏） | 0.738 | 0.929 | 0.976 | 0.836 |
| LSA（稠密） | 0.691 | 0.976 | 0.976 | 0.818 |
| **混合（RRF）** | **0.786** | 0.905 | 0.976 | **0.855** |

**拒答能力**：域外问题拦截 **5/5（100%）**；域内可答题作答率 **42/42（100%）**。

### 三个值得说的发现

**① 标题路径入索引，是性价比最高的一行改动**

同一语料、同一评测集，只改这一件事（`ablation_heading.py`）：

| 索引文本 | 混合 R@1 | 混合 MRR | LSA R@1 |
|:---|:---:|:---:|:---:|
| 只有正文 | 0.691 | 0.788 | 0.500 |
| **正文 + 标题路径** | **0.786** | **0.855** | **0.691** |
| 增量 | **+9.5pp** | **+6.7pp** | **+19.1pp** |

中文知识库的标题往往是**信息密度最高的地方**（"留存体系：D1/D7/D30、Cohort"），把它加进检索文本几乎零成本。稠密检索受益最大（+19.1pp）——它缺的正是"精确词面锚点"。

**② 小语料上，稠密检索不一定赢**

72 块的规模下，BM25 的 R@1 就有 0.738，**稠密（LSA）反而更低（0.691）**；不过稠密的 R@3 更高（0.976 vs 0.929）——它更擅长"把对的捞进候选"，只是排序头部不如 BM25 精准。
→ 结论：**小语料先上 BM25，别一上来就堆向量库**；稠密的价值在语义泛化（同义改写、跨语言），语料小的时候体现不出来。

**③ 混合不是"处处最优"（如实说）**

RRF 融合在 R@1 / MRR 上最好（0.786 / 0.855），但 **R@3 反而低于单路**（0.905 vs BM25 0.929）：融合偶尔把某题的 gold 从 top-3 挤到第 4 位。
→ 融合是**整体最优**,不是"每一项都赢"；选择要看你的下游用 top-1 还是 top-5。

### 诚实的失败案例

- **"LTV 应该按什么口径计算"**：gold 文档确实在 **top-5 内（rank 3）**，但 **top-1 是错的**（"口径"这个泛化词命中了另一篇的标题"定义流失（口径先行）"）。检索勉强够用，抽取式答案却因此答错 → 说明**"进了 top-5" 不等于 "答得对"**，还需要答案级评测（本项目只评检索，见 report 局限）。
- **"SRM 是什么"**：唯一没进 top-5 的题（gold 在 `pitfalls.md`，但 `ab-test-design.md` 里也讲了 SRM）→ **多篇文档讲同一概念时，单文档标注会"冤枉"检索**，这是评测集本身的口径问题。
- **加文档会挤动邻居**：本项目进行中新增了一篇文档（语料 9 篇 66 块 → 10 篇 72 块），几道题的 top-1 因此换人。**语料是活的，文档一多就要重跑评测**。

## 拒答怎么做的（RAG 的诚实性）

宁可拒答，也不硬凑。两道闸门（阈值经标注集标定）：

1. **未登录词占比 > 33%** → 判为域外问题（"今天晚饭吃什么" 的 token 大多从没在语料里出现过）
2. **top-3 分块最高覆盖率 < 15%** → 判为知识库没覆盖

标注集上：域内未登录词占比 ≤ 0.29、域外 ≥ 0.38，分得很干净。阈值是经验值，换语料要重新标定（评测脚本会打印误拒/漏拒）。

## 目录

| 路径 | 内容 |
|:---|:---|
| `python/rag_lib.py` | 核心库：分块 / 中文 n-gram 分词 / BM25 / LSA / RRF / 索引持久化 |
| `python/build_index.py` | 建索引 |
| `python/ask.py` | 问答 CLI（检索 + 抽取式作答 + 拒答 + `--show-prompt`） |
| `python/eval_retrieval.py` | 检索评测（三模式对比 + 拒答评测 + 出图） |
| `python/ablation_heading.py` | 消融实验（标题路径入索引的净增益） |
| `data/eval_questions.json` | **人工标注评测集**（42 域内 + 5 域外，源文件、入库） |
| `report.md` | **完整报告（方法 / 消融 / 失败分析 / 参考来源）** |

## 设计说明（面试常被问）

- **为什么自己实现 BM25 而不装 `rank_bm25`？** 一是零依赖更好复现，二是 BM25 只有 20 行，能改（这里就改了标题加权）；评测口径也更透明。
- **中文为什么不用 jieba？** 单字 + bigram 在检索场景已经很能打，且免去词典依赖；分词器只是"如何把中文切好"的一种方案，不是必需品。
- **RRF 为什么比加权求和好？** BM25 分数和余弦相似度**量纲不同**，直接加权要反复调参；RRF 只看排名（`Σ 1/(k+rank)`），天然免标定，且对异质检索器鲁棒。
- **为什么答案是"抽取式"？** 为了**离线可复现 + 可溯源 + 不编造**。生成式回答靠 `build_prompt()` 接任意 LLM 即可，但**评测要分开**：检索质量可以自动评，生成质量需要 LLM-as-judge 或人工（这里如实标为局限）。

## 升级路径（保持接口不变）

- **换真向量**：把 `LsaEncoder` 换成 sentence-transformers 或在线 embedding API，`RagIndex.search()` 不用动
- **换生成式**：`build_prompt()` 产出的 prompt 直接扔给任意 LLM
- **换评测**：`eval_questions.json` 换成你的业务问题集，指标自动重算
- **上生产**：语料变大后换 FAISS/Milvus 做向量索引，BM25 换 Elasticsearch；**但先把检索评测这套建起来**——否则上什么库都是盲调

## 参考来源

- RAG（检索增强生成）：Lewis et al. (2020), *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*, NeurIPS 33. arXiv:2005.11401 — https://arxiv.org/abs/2005.11401
- BM25 / 概率检索框架：Robertson & Zaragoza (2009), *The Probabilistic Relevance Framework: BM25 and Beyond*, Foundations and Trends in Information Retrieval 3(4):333–389. DOI:10.1561/1500000019
- RRF（倒数排名融合）：Cormack, Clarke & Buettcher (2009), *Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods*, SIGIR'09. DOI:10.1145/1571941.1572114
- 稠密检索基线（DPR）：Karpukhin et al. (2020), *Dense Passage Retrieval for Open-Domain Question Answering*, EMNLP. DOI:10.18653/v1/2020.emnlp-main.550
- LSA（潜在语义分析，本项目稠密向量基础）：Deerwester et al. (1990), *Indexing by Latent Semantic Analysis*, JASIS 41(6):391–407. DOI:10.1002/(SICI)1097-4571(199009)41:6<391::AID-ASI1>3.0.CO;2-9
- 注：本项目知识库与评测集均为**本仓库自有内容**，不含任何真实业务数据
