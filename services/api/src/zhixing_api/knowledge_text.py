from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TextChunk:
    heading: str
    content: str
    locator: str
    token_estimate: int


def content_hash(content: str) -> str:
    from hashlib import sha256

    return sha256(content.strip().encode("utf8")).hexdigest()


def chunk_document(content: str, *, max_chars: int = 520) -> list[TextChunk]:
    """Split heading-based Chinese business documents into stable, readable chunks."""
    sections: list[tuple[str, list[str]]] = []
    heading = "正文"
    paragraphs: list[str] = []
    for raw_line in content.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if paragraphs:
                sections.append((heading, paragraphs))
            heading = line.lstrip("#").strip() or "正文"
            paragraphs = []
        else:
            paragraphs.append(line)
    if paragraphs:
        sections.append((heading, paragraphs))

    chunks: list[TextChunk] = []
    for section_heading, section_paragraphs in sections:
        buffer: list[str] = []
        buffer_length = 0
        for paragraph in section_paragraphs:
            if buffer and buffer_length + len(paragraph) > max_chars:
                text = "\n".join(buffer)
                chunks.append(_text_chunk(section_heading, text, len(chunks) + 1))
                buffer = []
                buffer_length = 0
            buffer.append(paragraph)
            buffer_length += len(paragraph)
        if buffer:
            text = "\n".join(buffer)
            chunks.append(_text_chunk(section_heading, text, len(chunks) + 1))
    return chunks or [_text_chunk("正文", content.strip(), 1)]


def lexical_terms(text: str) -> set[str]:
    lowered = text.casefold()
    temporal_terms = {
        re.sub(r"\s+", "", item)
        for item in re.findall(r"\d+(?:\.\d+)?\s*(?:年|月|日|天|%|元|万)", lowered)
    }
    normalized = re.sub(r"\s+", "", lowered)
    terms = set(re.findall(r"[a-z0-9][a-z0-9_.-]{1,}", normalized))
    terms.update(temporal_terms)
    for sequence in re.findall(r"[\u3400-\u9fff]+", normalized):
        for width in (2, 3, 4):
            terms.update(
                sequence[index : index + width] for index in range(len(sequence) - width + 1)
            )
    return terms


def _text_chunk(heading: str, content: str, sequence: int) -> TextChunk:
    return TextChunk(
        heading=heading,
        content=content,
        locator=f"{heading} / 段落 {sequence}",
        token_estimate=max(1, round(len(content) / 1.7)),
    )
