#!/usr/bin/env python3
"""
rag_lib.py —— RAG 检索层核心库（零外部依赖，只用 numpy + scikit-learn）
================================================================
包含四件事：
  1. 分块（chunking）：按 Markdown 二级标题切块，保留"文档 › 章节"路径
  2. 分词（tokenizer）：中文用「单字 + 双字 bigram」，英文/数字按词 —— 不依赖 jieba
  3. 稀疏检索（BM25）：经典概率检索模型（Robertson & Zaragoza 2009）
  4. 稠密检索（LSA）：TF-IDF → TruncatedSVD 降维 → 余弦相似（Deerwester et al. 1990）
  5. 融合（RRF）：倒数排名融合，把两路结果合并（Cormack et al. 2009）

> 说明：本项目**不需要任何 API key**，离线可复现。稠密向量用的是 LSA（可比作
> "离线版 embedding"）；把它换成 sentence-transformers 或在线 embedding API 即可升级，
> 检索接口保持不变（见 README「如何升级为在线向量」）。
"""
from __future__ import annotations

import math
import pickle
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")      # 把 markdown 链接压成纯文本
DROP_SECTIONS = ("延伸阅读", "参考来源")


# --------------------------------------------------------------------------
# 1. 分词
# --------------------------------------------------------------------------
def tokenize(text: str) -> list[str]:
    """中文按「单字 + 双字 bigram」切，英文/数字按词切。
    中文不用分词器也能有不错效果：bigram 天然覆盖了大部分词。"""
    tokens: list[str] = []
    run: list[str] = []

    def flush() -> None:
        if not run:
            return
        tokens.extend(run)                                   # 单字
        tokens.extend(a + b for a, b in zip(run, run[1:]))    # 双字 bigram
        run.clear()

    for t in TOKEN_RE.findall(text.lower()):
        if len(t) == 1 and CJK_RE.match(t):
            run.append(t)
        else:
            flush()
            tokens.append(t)
    flush()
    return tokens


# --------------------------------------------------------------------------
# 2. 分块
# --------------------------------------------------------------------------
@dataclass
class Chunk:
    cid: int
    doc: str            # 相对仓库根的文件路径
    doc_title: str
    heading: str
    heading_path: str   # 文档标题 › 章节标题
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


def chunk_markdown(raw: str, doc: str) -> list[Chunk]:
    """按 Markdown 二级标题（##）切块；H1 作为文档标题，全文存进每个块便于检索上下文。"""
    lines = raw.split("\n")
    if lines and lines[0].strip() == "---":                 # 去掉 frontmatter
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end is not None:
            lines = lines[end + 1:]

    title = Path(doc).stem
    sections: list[dict] = []
    cur = {"h": "概述", "lines": []}
    for ln in lines:
        h2 = re.match(r"^##\s+(.*)$", ln)
        if h2:
            sections.append(cur)
            cur = {"h": h2.group(1).strip(), "lines": []}
            continue
        h1 = re.match(r"^#\s+(.*)$", ln)
        if h1:
            if title == Path(doc).stem:
                title = h1.group(1).strip()
            continue
        cur["lines"].append(ln)
    sections.append(cur)

    out: list[Chunk] = []
    for s in sections:
        text = LINK_RE.sub(r"\1", "\n".join(s["lines"])).strip()
        if not text or any(s["h"].startswith(d) for d in DROP_SECTIONS):
            continue
        out.append(Chunk(cid=len(out), doc=doc, doc_title=title, heading=s["h"],
                         heading_path=f"{title} › {s['h']}", text=text))
    return out


# --------------------------------------------------------------------------
# 3. BM25（稀疏检索）
# --------------------------------------------------------------------------
class BM25:
    """标准 BM25（k1=1.5, b=0.75 为业界常用默认值；见 Robertson & Zaragoza 2009）。"""

    def __init__(self, docs_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.N = len(docs_tokens)
        self.tfs = [Counter(d) for d in docs_tokens]
        self.doc_len = np.array([len(d) for d in docs_tokens], dtype=float)
        self.avgdl = float(self.doc_len.mean()) if self.N else 0.0
        df = Counter()
        for tf in self.tfs:
            df.update(tf.keys())
        # BM25 常用 IDF 变体（带 +0.5 平滑，避免负值）
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def scores(self, q_tokens: list[str]) -> np.ndarray:
        s = np.zeros(self.N)
        for t in set(q_tokens):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i, tf in enumerate(self.tfs):
                f = tf.get(t, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * self.doc_len[i] / (self.avgdl or 1.0))
                s[i] += idf * f * (self.k1 + 1) / denom
        return s

    def idf_of(self, token: str) -> float:
        return self.idf.get(token, 0.0)


# --------------------------------------------------------------------------
# 4. LSA 稠密向量
# --------------------------------------------------------------------------
class LsaEncoder:
    def __init__(self, n_components: int = 128, seed: int = 42):
        self.n_components, self.seed = n_components, seed
        self.vec: TfidfVectorizer | None = None
        self.svd: TruncatedSVD | None = None

    def fit(self, texts: list[str]) -> np.ndarray:
        self.vec = TfidfVectorizer(tokenizer=tokenize, token_pattern=None,
                                   lowercase=False, min_df=1)
        X = self.vec.fit_transform(texts)
        n = max(2, min(self.n_components, min(X.shape) - 1))
        self.svd = TruncatedSVD(n_components=n, random_state=self.seed)
        return normalize(self.svd.fit_transform(X))

    def encode(self, text: str) -> np.ndarray:
        assert self.vec is not None and self.svd is not None, "先 fit()"
        return normalize(self.svd.transform(self.vec.transform([text])))[0]

    @property
    def dim(self) -> int:
        return int(self.svd.components_.shape[0]) if self.svd is not None else 0


# --------------------------------------------------------------------------
# 5. RRF 融合
# --------------------------------------------------------------------------
def rrf_fuse(rank_lists: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """倒数排名融合：score = Σ 1/(k + rank)，rank 从 1 开始（Cormack et al. 2009）。"""
    fused: dict[int, float] = {}
    for ranks in rank_lists:
        for pos, idx in enumerate(ranks, start=1):
            fused[int(idx)] = fused.get(int(idx), 0.0) + 1.0 / (k + pos)
    return sorted(fused.items(), key=lambda kv: -kv[1])


# --------------------------------------------------------------------------
# 6. 索引：构建 / 保存 / 加载 / 检索
# --------------------------------------------------------------------------
INDEX_FILES = ("index.pkl",)


class RagIndex:
    def __init__(self, chunks: list[Chunk], bm25: BM25, lsa: LsaEncoder, Z: np.ndarray):
        self.chunks, self.bm25, self.lsa, self.Z = chunks, bm25, lsa, Z

    # ---- 构建 ----
    @classmethod
    def build(cls, docs: list[Path], base: Path | None = None,
              n_components: int = 128) -> "RagIndex":
        """docs: markdown 文件路径；base: 若非空，则 doc 名存为相对 base 的路径（便于展示）。"""
        chunks: list[Chunk] = []
        for p in docs:
            p = Path(p)
            name = str(p.relative_to(base)).replace("\\", "/") if base else str(p)
            raw = p.read_text(encoding="utf-8")
            chunks.extend(chunk_markdown(raw, name))
        for i, c in enumerate(chunks):
            c.cid = i
        # 检索文本 = 标题路径 + 正文（标题里的关键词通常最有区分度）；
        # 展示/抽取仍用干净的 c.text，避免答案里混进标题
        index_texts = [f"{c.heading_path}\n{c.text}" for c in chunks]
        bm25 = BM25([tokenize(t) for t in index_texts])
        lsa = LsaEncoder(n_components=n_components)
        Z = lsa.fit(index_texts)
        return cls(chunks, bm25, lsa, Z)

    # ---- 持久化 ----
    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: str | Path) -> "RagIndex":
        with open(path, "rb") as f:
            return pickle.load(f)

    # ---- 检索 ----
    def search(self, query: str, k: int = 5, mode: str = "hybrid") -> list[dict]:
        bm = self.bm25.scores(tokenize(query))
        bm_rank = list(np.argsort(-bm))
        if mode == "bm25":
            order = bm_rank[:k]
        else:
            qv = self.lsa.encode(query)
            dense = self.Z @ qv
            dense_rank = list(np.argsort(-dense))
            if mode == "dense":
                order = dense_rank[:k]
            elif mode == "hybrid":
                order = [i for i, _ in rrf_fuse([bm_rank, dense_rank])[:k]]
            else:
                raise ValueError(f"未知 mode: {mode}")
        out = []
        for i in order:
            c = self.chunks[i]
            out.append({"cid": i, "doc": c.doc, "doc_title": c.doc_title,
                        "heading": c.heading, "heading_path": c.heading_path,
                        "text": c.text, "score_bm25": float(bm[i])})
        return out
