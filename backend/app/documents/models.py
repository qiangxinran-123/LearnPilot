from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ParseStatus(StrEnum):
    SUCCESS = "SUCCESS"
    EMPTY_CONTENT = "EMPTY_CONTENT"
    DECODE_ERROR = "DECODE_ERROR"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    PARSE_FAILED = "PARSE_FAILED"


@dataclass(frozen=True)
class ParsedSegment:
    text: str
    source_reference: str

    def to_dict(self) -> dict[str, str]:
        return {"text": self.text, "source_reference": self.source_reference}


@dataclass(frozen=True)
class ParsedDocument:
    status: ParseStatus
    text: str
    segments: list[ParsedSegment]
    page_count: int
    parser_name: str
    parser_version: str
    error_code: str | None = None
    error_message: str | None = None

    @property
    def successful(self) -> bool:
        return self.status == ParseStatus.SUCCESS
