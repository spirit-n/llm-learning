from __future__ import annotations

import re
from html import escape

from .models import CitationCheck, ContextBundle, RAGAnswer, SearchHit
from .text import tokenize


INSTRUCTION_PATTERN = re.compile(
    r"(?i)(ignore (all|previous)|system prompt|developer message|忽略.{0,8}(指令|规则)|系统提示词)"
)
CITATION_PATTERN = re.compile(r"\[([A-Za-z0-9_.:-]+#[A-Za-z0-9_.:-]+)\]")
# 单字分词会把“如何使用”之类套话误当作证据。门控只统计有区分度的词。
QUERY_STOP_TOKENS = set("是什么的了呢吗吧啊请问如何怎么为何为什么一下相关关于和与或使用介绍讲解")


def evidence_relevance(query: str, hits: list[SearchHit]) -> float:
    """返回 0..1 的可解释词项覆盖率，用作生成前的最后一道证据门控。

    排序分数只能表示“候选中谁更靠前”，不能证明候选真的相关；尤其 RRF 在两路
    都很差时仍会产生正分。因此这里重新检查问题与首条证据是否存在有意义的交集。
    """

    if not hits:
        return 0.0
    query_terms = set(tokenize(query)) - QUERY_STOP_TOKENS
    evidence_terms = set(
        tokenize(
            f"{hits[0].chunk.title} {hits[0].chunk.section} {hits[0].chunk.text}"
        )
    ) - QUERY_STOP_TOKENS
    if not query_terms:
        return 0.0
    overlap = query_terms & evidence_terms
    # ASCII 术语/错误码一次精确命中已很强；中文单字至少命中两个，降低“的/用”等碰撞。
    strong_ascii_match = any(re.search(r"[a-z0-9]", term, re.I) for term in overlap)
    if not strong_ascii_match and len(overlap) < 2:
        return 0.0
    return min(1.0, len(overlap) / len(query_terms))


def build_context_bundle(
    hits: list[SearchHit], *, token_budget: int = 160
) -> ContextBundle:
    if token_budget <= 0:
        raise ValueError("token_budget 必须大于 0")
    blocks: list[str] = []
    citations: list[str] = []
    dropped: list[str] = []
    used_tokens = 0
    seen_chunks: set[str] = set()
    contains_untrusted_instructions = False
    for hit in hits:
        chunk = hit.chunk
        if chunk.chunk_id in seen_chunks:
            continue
        contains_instruction = bool(INSTRUCTION_PATTERN.search(chunk.text))
        contains_untrusted_instructions |= contains_instruction
        # 检索内容始终作为“数据”包裹；标记疑似注入是为了审计，不是让模型自行判断权限。
        block = (
            f'<evidence id="{escape(chunk.chunk_id, quote=True)}" '
            f'source="{escape(chunk.source, quote=True)}" '
            f'untrusted_instruction="{str(contains_instruction).lower()}">\n'
            f"{escape(chunk.title)}/{escape(chunk.section)}\n"
            f"{escape(chunk.text)}\n</evidence>"
        )
        block_tokens = len(tokenize(block))
        if used_tokens + block_tokens > token_budget:
            dropped.append(chunk.chunk_id)
            continue
        blocks.append(block)
        citations.append(chunk.chunk_id)
        seen_chunks.add(chunk.chunk_id)
        used_tokens += block_tokens
    return ContextBundle(
        text="\n\n".join(blocks),
        citation_ids=citations,
        used_tokens=used_tokens,
        dropped_chunk_ids=dropped,
        contains_untrusted_instructions=contains_untrusted_instructions,
    )


def build_context(
    hits: list[SearchHit], *, token_budget: int = 160
) -> tuple[str, list[str]]:
    """保留教程早期的 tuple 接口；工程代码优先使用 build_context_bundle。"""
    bundle = build_context_bundle(hits, token_budget=token_budget)
    return bundle.text, bundle.citation_ids


def validate_citations(answer: str, allowed_ids: list[str]) -> CitationCheck:
    cited = list(dict.fromkeys(CITATION_PATTERN.findall(answer)))
    allowed = set(allowed_ids)
    unknown = [citation for citation in cited if citation not in allowed]
    return CitationCheck(
        valid=bool(cited) and not unknown,
        cited_ids=cited,
        unknown_ids=unknown,
    )


def answer_from_context(
    hits: list[SearchHit],
    *,
    token_budget: int = 160,
    query: str | None = None,
    min_relevance: float = 0.2,
) -> RAGAnswer:
    if not 0 <= min_relevance <= 1:
        raise ValueError("min_relevance 必须在 0..1")
    relevance = evidence_relevance(query, hits) if query is not None else 1.0
    bundle = build_context_bundle(hits, token_budget=token_budget)
    usable_hits = [hit for hit in hits if hit.chunk.chunk_id in bundle.citation_ids]
    if not usable_hits or relevance < min_relevance:
        reason = "NO_CONTEXT_WITHIN_BUDGET" if not usable_hits else "LOW_RELEVANCE"
        answer = "证据不足，无法回答。"
        return RAGAnswer(
            answer=answer,
            citations=[],
            context=bundle.text,
            insufficient_evidence=True,
            citation_check=CitationCheck(
                valid=True, cited_ids=[], unknown_ids=[]
            ),
            evidence_reason=reason,
            relevance_score=relevance,
        )
    top = usable_hits[0].chunk
    answer = f"{top.text} [{top.chunk_id}]"
    check = validate_citations(answer, bundle.citation_ids)
    return RAGAnswer(
        answer=answer,
        citations=[top.chunk_id],
        context=bundle.text,
        insufficient_evidence=False,
        citation_check=check,
        relevance_score=relevance,
    )
