from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO


class StorageError(Exception):
    pass


class UploadRejected(StorageError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class SavedFile:
    storage_key: str
    size_bytes: int


class FileStorage(ABC):
    @abstractmethod
    def save(
        self,
        source: BinaryIO,
        *,
        extension: str,
        media_type: str,
        max_bytes: int,
    ) -> SavedFile:
        raise NotImplementedError

    @abstractmethod
    def delete(self, storage_key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def exists(self, storage_key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def open_read(self, storage_key: str) -> BinaryIO:
        raise NotImplementedError
