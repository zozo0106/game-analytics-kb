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
MIN_COVERAGE = 0.08        # 覆盖率闸门的历史阈值（实测无区分度，已不参与拒判，仅保留诊断）
MAX_UNKNOWN_RATIO = 0.36   # query 中"语料里从没见过"的 token 占比上限，超了判为域外问题
UNKNOWN_TOKEN_WEIGHT = 6.0 # 未登录词的覆盖率权重（略高于小语料最大 IDF≈5）
MIN_SCORE_FRAC = 0.55      # 入选句子至少要达到最佳句得分的这个比例，避免混入填充句

# 虚词/功能词：它们在任何语料里都常见，会把覆盖率"注水"。
# 例："Python 的 GIL 是什么？" 里的 的/是/什么 让覆盖率虚高到 0.58 —— 只看实词才露馅。
STOPWORDS = {
    "的", "是", "了", "在", "和", "与", "及", "或", "把", "被", "从", "到", "对", "为", "以",
    "之", "其", "很", "更", "最", "也", "都", "就", "而", "但", "不", "有", "无", "能", "会",
    "要", "可", "请", "问", "我", "你", "他", "她", "它", "这", "那", "些", "个", "上", "下",
    "什么", "为什么", "怎么", "怎样", "如何", "哪里", "哪个", "哪些", "多少", "哪个",
    "是不是", "有没有", "应该", "可以", "需要", "以及", "还有", "比如", "例如",
    "我们", "你们", "他们", "一下", "一个", "比较", "到底", "究竟", "呢", "吗", "吧", "啊",
}

# 关于这两个阈值：在 47 题标注集上按**实词**重新标定 —— 域内问题的实词未登录占比 ≤0.33、
# 域外 ≥0.40（"Python 的 GIL 是什么" 这类"词面都认识、主题却域外"的问题，只有量实词才分得开），
# 故取 0.36 作分界；覆盖率闸门（0.08）只兜极端情况（词都认识但一句话都对不上），
# 因为域内最差的覆盖率也有 0.10 —— 阈值设高了会误拒真问题。
# 阈值是经验值，且 0.33 / 0.40 的间隔只有 0.07，属于**窄间隔**，换语料必须重新标定
# （eval_retrieval.py 会直接打印误拒/漏拒）。


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


def content_tokens(query: str) -> list[str]:
    """只保留实词：去掉虚词/功能词与单字标点。停用词表很小且可解释（见 STOPWORDS）。"""
    return [t for t in tokenize(query)
            if t not in STOPWORDS and re.search(r"[0-9a-z\u4e00-\u9fff]", t)]


def unknown_ratio(query: str, idx: RagIndex) -> float:
    """query 的**实词**里有多少是语料词表中从未出现过的（域外问题的强信号）。"""
    toks = content_tokens(query)
    if not toks:
        return 1.0
    return sum(1 for t in toks if idx.bm25.idf_of(t) == 0) / len(toks)


def best_coverage(query: str, hits: list[dict], idx: RagIndex) -> float:
    """top-k 分块里，最好的一个句子覆盖了多少 query 实词权重（0~1）。

    ⚠️ 未登录词（IDF=0）必须**照样计入分母**，否则会被"熟悉但无关"的词掩盖：
    问"某运行时机制"时，仅因句中有"Python"命中语料，覆盖率就能被拉到 1.00。
    这里给未登录词一个略高于语料内最大 IDF 的权重 —— 完全陌生的词最有信息量。
    """
    tokens = list(dict.fromkeys(content_tokens(query)))
    weights = {t: (idx.bm25.idf_of(t) or UNKNOWN_TOKEN_WEIGHT) for t in tokens}
    q_weight = sum(weights.values())
    if q_weight <= 0:
        return 0.0
    best = 0.0
    for h in hits[:3]:
        for sent in split_sentences(h["text"]):
            toks = set(tokenize(sent))
            best = max(best, sum(w for t, w in weights.items() if t in toks) / q_weight)
    return best


def abstain_reason(query: str, hits: list[dict], idx: RagIndex) -> str | None:
    """返回拒答原因；None 表示可以作答。

    只用一道闸门：**实词未登录占比**。这是实测唯一有效的信号 ——
    - 覆盖率闸门：把未登录词计入分母后，域内最低 0.06 / 域外最低 0.05，**完全没有区分度**；
    - 语义距离闸门（稠密余弦）：域外问题 0.713 反而高于域内最低 0.46（小语料 + LSA 的
      语义空间被"Python"这类通用词主导）→ 同样失效。
    两个被否掉的方案写在 README「拒答的减法」一节，此处保留 best_coverage 仅作诊断输出。
    """
    ur = unknown_ratio(query, idx)
    if ur > MAX_UNKNOWN_RATIO:
        return f"问题超出知识库范围（实词未登录占比 {ur:.0%} > {MAX_UNKNOWN_RATIO:.0%}）"
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
