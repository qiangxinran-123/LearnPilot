from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import BinaryIO

from backend.app.documents import ParseStatus, parse_document


class ExtractionStatus(StrEnum):
    EXTRACTED = "EXTRACTED"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    DECODE_ERROR = "DECODE_ERROR"
    EMPTY_CONTENT = "EMPTY_CONTENT"
    PARSE_FAILED = "PARSE_FAILED"


@dataclass(frozen=True)
class ExtractionResult:
    status: ExtractionStatus
    text: str
    error_code: str | None = None
    error_message: str | None = None

    @property
    def extracted(self) -> bool:
        return self.status == ExtractionStatus.EXTRACTED


def extract_text(source: BinaryIO, extension: str) -> ExtractionResult:
    parsed = parse_document(source, extension)
    status_map = {
        ParseStatus.SUCCESS: ExtractionStatus.EXTRACTED,
        ParseStatus.UNSUPPORTED_FORMAT: ExtractionStatus.UNSUPPORTED_FORMAT,
        ParseStatus.DECODE_ERROR: ExtractionStatus.DECODE_ERROR,
        ParseStatus.EMPTY_CONTENT: ExtractionStatus.EMPTY_CONTENT,
        ParseStatus.PARSE_FAILED: ExtractionStatus.PARSE_FAILED,
    }
    return ExtractionResult(
        status=status_map[parsed.status],
        text=parsed.text,
        error_code=parsed.error_code,
        error_message=parsed.error_message,
    )
