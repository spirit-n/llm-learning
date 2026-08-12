from __future__ import annotations

import hashlib

from .models import Chunk, Document
from .text import tokenize


def _split_with_overlap(text: str, *, max_tokens: int, overlap_tokens: int) -> list[str]:
    """教学实现按字符近似回切；真实项目应替换成所用模型的 tokenizer。"""
    if max_tokens <= 0 or overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("max_tokens 必须大于 0，且 overlap_tokens 必须小于 max_tokens")
    if len(tokenize(text)) <= max_tokens:
        return [text]

    # 中文按字符、英文按空白切虽然不完美，但能稳定展示“长章节必须二次切分”。
    is_cjk = any("\u4e00" <= char <= "\u9fff" for char in text)
    units = list(text) if is_cjk else text.split()
    step = max_tokens - overlap_tokens
    parts = [units[start : start + max_tokens] for start in range(0, len(units), step)]
    joiner = "" if is_cjk else " "
    return [joiner.join(part).strip() for part in parts if part]


def heading_chunks(
    document: Document,
    *,
    max_tokens: int = 120,
    overlap_tokens: int = 20,
) -> list[Chunk]:
    sections: list[tuple[str, list[str]]] = []
    current_heading = document.title
    current_lines: list[str] = []

    for raw_line in document.text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if current_lines:
                sections.append((current_heading, current_lines))
            current_heading = line.lstrip("#").strip() or document.title
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_heading, current_lines))
    if not sections:
        sections.append((document.title, [document.text.strip()]))

    chunks: list[Chunk] = []
    chunk_position = 0
    for heading_position, (heading, lines) in enumerate(sections, start=1):
        parts = _split_with_overlap(
            "\n".join(lines), max_tokens=max_tokens, overlap_tokens=overlap_tokens
        )
        for part_position, part in enumerate(parts, start=1):
            # 单段保留简短 ID；被二次切分时加 pN，便于定位原章节中的片段。
            suffix = (
                f"#h{heading_position}"
                if len(parts) == 1
                else f"#h{heading_position}p{part_position}"
            )
            chunks.append(
                Chunk(
                    chunk_id=f"{document.doc_id}{suffix}",
                    doc_id=document.doc_id,
                    text=part,
                    source=document.source,
                    title=document.title,
                    section=heading,
                    version=document.version,
                    tenant=document.tenant,
                    is_latest=document.is_latest,
                    position=chunk_position,
                    token_count=len(tokenize(part)),
                    content_hash=hashlib.sha256(part.encode("utf-8")).hexdigest()[:16],
                )
            )
            chunk_position += 1
    return chunks


def chunk_documents(
    documents: list[Document], *, max_tokens: int = 120, overlap_tokens: int = 20
) -> list[Chunk]:
    seen_ids: set[str] = set()
    chunks: list[Chunk] = []
    for document in documents:
        if document.doc_id in seen_ids:
            raise ValueError(f"重复 doc_id: {document.doc_id}")
        seen_ids.add(document.doc_id)
        chunks.extend(
            heading_chunks(
                document, max_tokens=max_tokens, overlap_tokens=overlap_tokens
            )
        )
    return chunks
