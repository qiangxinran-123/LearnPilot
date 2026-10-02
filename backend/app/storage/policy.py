from __future__ import annotations

from pathlib import Path

from backend.app.storage.base import UploadRejected

ALLOWED_MEDIA_TYPES: dict[str, set[str]] = {
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
    ".pdf": {"application/pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
}


def validate_filename_and_media_type(filename: str, media_type: str | None) -> str:
    if not filename:
        raise UploadRejected("INVALID_FILENAME", "Uploaded file must have a filename.")
    if "/" in filename or chr(92) in filename or Path(filename).name != filename:
        raise UploadRejected(
            "INVALID_FILENAME",
            "Uploaded filename contains a path component.",
        )
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_MEDIA_TYPES:
        raise UploadRejected("UNSUPPORTED_FILE_TYPE", "Unsupported file type.")
    if media_type not in ALLOWED_MEDIA_TYPES[extension]:
        raise UploadRejected(
            "INVALID_MEDIA_TYPE",
            "Declared media type is not allowed for this file.",
        )
    return extension


def validate_content_signature(extension: str, prefix: bytes) -> None:
    if extension == ".pdf" and not prefix.startswith(b"%PDF-"):
        raise UploadRejected("INVALID_FILE_SIGNATURE", "PDF signature validation failed.")
    if extension == ".docx" and not prefix.startswith(b"PK"):
        raise UploadRejected(
            "INVALID_FILE_SIGNATURE",
            "Office file signature validation failed.",
        )
