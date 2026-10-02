from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    text: str
    source_reference: str


def chunk_segments(segments: list[dict[str, object]], *, max_chars: int, overlap_chars: int) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for raw_segment in segments:
        text = str(raw_segment.get("text", "")).strip()
        reference = str(raw_segment.get("source_reference", "资料内容"))
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            chunks.append(TextChunk(text=text[start:end], source_reference=reference))
            if end == len(text):
                break
            start = max(end - overlap_chars, start + 1)
    return chunks


def relevant_chunks(question: str, chunks: list[TextChunk], *, limit: int = 4) -> list[TextChunk]:
    tokens = set(re.findall(r"[a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]", question.casefold()))
    if not tokens:
        return []

    def score(chunk: TextChunk) -> int:
        haystack = chunk.text.casefold()
        return sum(token in haystack for token in tokens)

    ranked = sorted(((score(chunk), index, chunk) for index, chunk in enumerate(chunks)), reverse=True)
    return [chunk for score_value, _, chunk in ranked if score_value > 0][:limit]
