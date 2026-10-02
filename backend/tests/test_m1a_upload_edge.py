from __future__ import annotations

import io
from pathlib import Path

import pytest

from backend.app.storage import LocalFileStorage, UploadRejected


def test_empty_upload_is_rejected(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "uploads")

    with pytest.raises(UploadRejected) as error:
        storage.save(
            io.BytesIO(b""),
            extension=".txt",
            media_type="text/plain",
            max_bytes=1024,
        )

    assert error.value.code == "EMPTY_FILE"
