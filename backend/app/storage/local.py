from __future__ import annotations

import logging
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from backend.app.storage.base import FileStorage, SavedFile, StorageError, UploadRejected
from backend.app.storage.policy import validate_content_signature

logger = logging.getLogger(__name__)


class LocalFileStorage(FileStorage):
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        source: BinaryIO,
        *,
        extension: str,
        media_type: str,
        max_bytes: int,
    ) -> SavedFile:
        storage_key = f"{uuid4().hex}{extension}"
        destination = self._path_for_key(storage_key)
        temporary = self.root / f".{uuid4().hex}.uploading"
        size_bytes = 0
        prefix = bytearray()

        try:
            with temporary.open("xb") as output:
                while True:
                    chunk = source.read(64 * 1024)
                    if not chunk:
                        break
                    size_bytes += len(chunk)
                    if size_bytes > max_bytes:
                        raise UploadRejected(
                            "UPLOAD_TOO_LARGE",
                            "Uploaded file exceeds the allowed size.",
                        )
                    if len(prefix) < 16:
                        prefix.extend(chunk[: 16 - len(prefix)])
                    output.write(chunk)

            if size_bytes == 0:
                raise UploadRejected("EMPTY_FILE", "Uploaded file must not be empty.")
            validate_content_signature(extension, bytes(prefix))
            temporary.replace(destination)
            return SavedFile(storage_key=storage_key, size_bytes=size_bytes)
        except UploadRejected:
            temporary.unlink(missing_ok=True)
            logger.warning("Upload rejected with code %s", "validation")
            raise
        except OSError as error:
            temporary.unlink(missing_ok=True)
            logger.exception("Local storage write failed")
            raise StorageError("Unable to persist uploaded file.") from error

    def delete(self, storage_key: str) -> None:
        self._path_for_key(storage_key).unlink(missing_ok=True)

    def exists(self, storage_key: str) -> bool:
        return self._path_for_key(storage_key).is_file()

    def open_read(self, storage_key: str) -> BinaryIO:
        return self._path_for_key(storage_key).open("rb")

    def _path_for_key(self, storage_key: str) -> Path:
        candidate = (self.root / storage_key).resolve()
        if candidate.parent != self.root:
            raise StorageError("Invalid storage key.")
        return candidate
