#!/usr/bin/env python3
"""
ask.py —— 知识库问答 CLI：检索 + 抽取式作答 + 引用
================================================================
零 API key 也能跑：默认用「检索 + 抽取式作答」——从命中的分块里挑出与问题
最相关的句子，并给出可点开的来源路径（文档 › 章节）。

想变成"生成式回答"，把 `build_prompt()` 产出的 prompt 丢给任意 LLM 即可
（README 有说明）。这一步是**有意留白的扩展点**，不是本项目的能力边界。

用法：
  python python/ask.py "N-day 留存和 unbounded 留存有什么区别？"
  python python/ask.py "归因和增量差在哪" --mode bm25 --topk 3
  python python/ask.py --interactive
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag_lib import RagIndex, tokenize          # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
INDEX = Path(__file__).resolve().parent.parent / "data" / "index.pkl"
SENT_SPLIT = re.compile(r"(?<=[。！？；])|\n+")
MAX_SENTS = 3
MIN_COVERAGE = 0.15        # top-3 分块里最好句子的 query 覆盖率下限，低于此判为"知识库答不了"
MAX_UNKNOWN_RATIO = 0.33   # query 中"语料里从没见过"的 token 占比上限，超了判为域外问题
MIN_SCORE_FRAC = 0.55      # 入选句子至少要达到最佳句得分的这个比例，避免混入填充句

# 关于这两个阈值：在 38+5 题标注集上，域内问题的未登录词占比 ≤0.29、域外 ≥0.38，
# 覆盖率域内 ≥0.17、域外无意义 —— 因此取 0.33 / 0.15 作为分隔。阈值是经验值，
# 换语料需重新标定（评测脚本会直接打印误拒/漏拒）。


def split_sentences(text: str) -> list[str]:
    out = []
    for raw in SENT_SPLIT.split(text):
        raw = (raw or "").strip()
        if raw.startswith("|"):                 # 跳过表格行（碎片不是句子）
            continue
        s = raw.replace("**", "").replace("`", "")
        s = re.sub(r"^[\s\-*>•\[\]]+", "", s)
        s = re.sub(r"^(第[一二三四五六七八九十]+步|坑\s*\d+)\s*[·、:：]?\s*", r"\1 ", s)
        if len(s) >= 10:
            out.append(s)
    return out


def unknown_ratio(query: str, idx: RagIndex) -> float:
    """query 里有多少 token 是语料词表中从未出现过的（域外问题的强信号）。"""
    toks = tokenize(query)
    if not toks:
        return 1.0
    return sum(1 for t in toks if idx.bm25.idf_of(t) == 0) / len(toks)


def best_coverage(query: str, hits: list[dict], idx: RagIndex) -> float:
    """top-k 分块里，最好的一个句子覆盖了多少 query 权重（0~1）。"""
    q_tokens = set(tokenize(query))
    q_weight = sum(idx.bm25.idf_of(t) for t in q_tokens)
    if q_weight <= 0:
        return 0.0
    best = 0.0
    for h in hits[:3]:
        for sent in split_sentences(h["text"]):
            toks = set(tokenize(sent))
            best = max(best, sum(idx.bm25.idf_of(t) for t in q_tokens if t in toks) / q_weight)
    return best


def abstain_reason(query: str, hits: list[dict], idx: RagIndex) -> str | None:
    """返回拒答原因；None 表示可以作答。"""
    ur = unknown_ratio(query, idx)
    if ur > MAX_UNKNOWN_RATIO:
        return f"问题超出知识库范围（未登录词占比 {ur:.0%} > {MAX_UNKNOWN_RATIO:.0%}）"
    bc = best_coverage(query, hits, idx)
    if bc < MIN_COVERAGE:
        return f"知识库没有覆盖这个问题（最高覆盖率仅 {bc:.0%}）"
    return None


def extract_answer(query: str, hits: list[dict], idx: RagIndex) -> list[str]:
    """从 top 分块里挑最相关的句子：句子得分 = 命中 token 的 IDF 之和 ÷ √句子长度。
    作答前先过拒答闸门（域外/无覆盖 → 返回空列表，由调用方提示"知识库中没有相关内容"）。"""
    if abstain_reason(query, hits, idx) is not None:
        return []
    q_tokens = set(tokenize(query))
    q_weight = sum(idx.bm25.idf_of(t) for t in q_tokens)
    cands: list[tuple[float, int, int, str]] = []
    for rank, h in enumerate(hits[:3]):
        for si, sent in enumerate(split_sentences(h["text"])):
            toks = set(tokenize(sent))
            covered = sum(idx.bm25.idf_of(t) for t in q_tokens if t in toks)
            if q_weight <= 0 or covered / q_weight < MIN_COVERAGE:
                continue
            cands.append((covered / math.sqrt(max(len(toks), 1)), rank, si, sent))
    cands.sort(key=lambda c: (-c[0], c[1], c[2]))
    if not cands:
        return []
    # 只保留接近最佳分的句子（否则会混进"沾边但无关"的填充句）
    floor = MIN_SCORE_FRAC * cands[0][0]
    picked = [c for c in cands if c[0] >= floor][:MAX_SENTS]
    picked.sort(key=lambda c: (c[1], c[2]))          # 按原文顺序输出
    seen, out = set(), []
    for _, _, _, s in picked:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def build_prompt(query: str, hits: list[dict]) -> str:
    """标准 RAG prompt 模板：接任意 LLM 即可得到生成式回答（本项目默认不用）。"""
    ctx = "\n\n".join(f"[{i}]（来源：{h['heading_path']}）\n{h['text']}"
                      for i, h in enumerate(hits, 1))
    return (
        "你是游戏数据分析知识库助手。请只依据下面提供的资料回答问题；"
        "资料中没有的内容不要编造，直接说明「知识库中没有相关内容」。\n"
        "回答后用 [编号] 标注引用的资料。\n\n"
        f"### 资料\n{ctx}\n\n### 问题\n{query}\n\n### 回答\n"
    )


def answer_once(query: str, idx: RagIndex, mode: str, topk: int,
                show_context: bool = False) -> None:
    hits = idx.search(query, k=topk, mode=mode)
    sents = extract_answer(query, hits, idx)

    print(f"\n❓ {query}")
    print(f"   检索模式：{mode}   命中分块：{len(hits)}")
    if sents:
        print("\n💡 答案（抽取式，原句引用自知识库）")
        for s in sents:
            print(f"   • {s}")
    else:
        reason = abstain_reason(query, hits, idx) or "没有找到足够相关的句子"
        print(f"\n🙅 知识库中没有相关内容 —— {reason}")
        print("   （这是设计行为：宁可拒答，也不硬凑一段看似相关的答案）")
    print("\n📎 来源")
    docs = []
    for h in hits:
        if h["doc"] not in [d for d, _ in docs]:
            docs.append((h["doc"], h["heading_path"]))
    for i, (doc, hp) in enumerate(docs, 1):
        print(f"   [{i}] {doc}\n       └ {hp}")
    if show_context:
        print("\n🧩 命中分块原文（调试）")
        for i, h in enumerate(hits, 1):
            head = h["text"].replace("\n", " ")[:160]
            print(f"   [{i}] {h['heading_path']}  (bm25={h['score_bm25']:.2f})\n       {head}…")


def main() -> None:
    ap = argparse.ArgumentParser(description="游戏数据分析知识库问答")
    ap.add_argument("question", nargs="*", help="要问的问题（不加则进入交互模式）")
    ap.add_argument("--mode", default="hybrid", choices=["hybrid", "bm25", "dense"])
    ap.add_argument("--topk", type=int, default=5)
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--show-context", action="store_true")
    ap.add_argument("--show-prompt", action="store_true", help="打印可投喂给 LLM 的 RAG prompt")
    args = ap.parse_args()

    if not INDEX.exists():
        raise SystemExit(f"索引不存在：{INDEX}\n先跑 python python/build_index.py")
    idx = RagIndex.load(INDEX)

    if args.interactive or not args.question:
        print("🎮 游戏数据分析知识库 · 问答（Ctrl-C 退出）")
        try:
            while True:
                q = input("\n> ").strip()
                if q:
                    answer_once(q, idx, args.mode, args.topk, args.show_context)
        except (KeyboardInterrupt, EOFError):
            print("\n再见 👋")
        return

    query = " ".join(args.question)
    answer_once(query, idx, args.mode, args.topk, args.show_context)
    if args.show_prompt:
        print("\n" + "=" * 70 + "\n📤 可直接投喂给 LLM 的 RAG prompt：\n" + "=" * 70)
        print(build_prompt(query, idx.search(query, k=args.topk, mode=args.mode)))


if __name__ == "__main__":
    main()
