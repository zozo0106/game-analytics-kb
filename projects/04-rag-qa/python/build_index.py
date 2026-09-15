#!/usr/bin/env python3
"""
build_index.py —— 把知识库（docs/**.md）构建成可检索索引
================================================================
流程：Markdown → 按章节分块 → 中文 n-gram 分词 → BM25 稀疏索引 + LSA 稠密索引
输出：data/index.pkl（含分块、BM25、SVD、向量矩阵；gitignored）

运行：python python/build_index.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag_lib import RagIndex          # noqa: E402

ROOT = Path(__file__).resolve().parents[3]      # 仓库根（…/game-analytics-kb）
DOCS = ROOT / "docs"
OUT = Path(__file__).resolve().parent.parent / "data" / "index.pkl"
N_COMPONENTS = 128


def main() -> None:
    md_files = sorted(DOCS.glob("**/*.md"))
    if not md_files:
        raise SystemExit(f"没找到任何 markdown：{DOCS}")

    idx = RagIndex.build(md_files, base=ROOT, n_components=N_COMPONENTS)
    idx.save(OUT)

    docs = sorted({c.doc for c in idx.chunks})
    print("📚 知识库索引构建完成")
    print(f"   源文档     {len(md_files)} 篇（{DOCS.relative_to(ROOT)}/）")
    print(f"   分块       {len(idx.chunks)} 块（按二级标题切）")
    print(f"   词表       {len(idx.bm25.idf):,} 个 token（中文单字+bigram）")
    print(f"   稠密维度   {idx.lsa.dim}（TF-IDF → TruncatedSVD/LSA）")
    print(f"   输出       {OUT.relative_to(ROOT.parent)}")
    print("\n   分块最多的文档：")
    cnt = {}
    for c in idx.chunks:
        cnt[c.doc] = cnt.get(c.doc, 0) + 1
    for d, n in sorted(cnt.items(), key=lambda kv: -kv[1])[:5]:
        print(f"     {n:>3} 块  {d}")


if __name__ == "__main__":
    main()
