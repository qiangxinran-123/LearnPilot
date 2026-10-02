from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app.core.settings import Settings
from backend.app.db.models import Course, Material, User
from backend.app.repositories import CourseRepository, MaterialRepository, UserRepository
from backend.app.services.course_service import serialize_material
from backend.app.services.text_extraction_service import ExtractionStatus, extract_text
from backend.app.storage import LocalFileStorage, UploadRejected
from backend.app.storage.policy import validate_filename_and_media_type
from backend.scripts.import_legacy_json import import_legacy_data


def migrate_database(tmp_path: Path) -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'foundation.sqlite3'}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return database_url


def test_alembic_creates_ownership_schema(tmp_path: Path) -> None:
    database_url = migrate_database(tmp_path)
    engine = create_engine(database_url)
    inspector = inspect(engine)

    assert {"users", "courses", "materials"}.issubset(set(inspector.get_table_names()))
    course_foreign_keys = inspector.get_foreign_keys("courses")
    material_foreign_keys = inspector.get_foreign_keys("materials")
    assert course_foreign_keys[0]["referred_table"] == "users"
    assert material_foreign_keys[0]["referred_table"] == "courses"
    engine.dispose()


def test_repository_persists_owned_course_and_material(tmp_path: Path) -> None:
    database_url = migrate_database(tmp_path)
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        with session.begin():
            user = UserRepository(session).add(User(email="owner@example.test", display_name="Owner", is_active=True))
            course = CourseRepository(session).add(Course(owner_id=user.id, name="Algorithms", description="Graphs"))
            material = MaterialRepository(session).add(
                Material(
                    course_id=course.id,
                    title="Traversal",
                    material_type="txt",
                    summary="Graph traversal",
                    storage_status="NOT_STORED",
                    extraction_status="NOT_REQUESTED",
                )
            )

    with session_factory() as session:
        stored_course = CourseRepository(session).get_by_id(course.id)
        stored_material = MaterialRepository(session).get_by_id(material.id)
        assert stored_course is not None
        assert stored_course.owner_id == user.id
        assert stored_material is not None
        assert stored_material.course_id == course.id
    engine.dispose()


def test_database_transaction_rolls_back_duplicate_user(tmp_path: Path) -> None:
    database_url = migrate_database(tmp_path)
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(User(email="duplicate@example.test", display_name="One", is_active=True))
                session.add(User(email="duplicate@example.test", display_name="Two", is_active=True))

    with session_factory() as session:
        assert session.scalars(select(User)).all() == []
    engine.dispose()


def test_legacy_import_dry_run_actual_import_and_idempotency(tmp_path: Path) -> None:
    source = tmp_path / "legacy.json"
    source.write_text(
        json.dumps(
            {
                "courses": [
                    {
                        "id": 9,
                        "name": "Legacy Course",
                        "semester": "Legacy",
                        "description": "Imported safely",
                    }
                ],
                "materials": {
                    "9": [
                        {
                            "id": 901,
                            "title": "Legacy Notes",
                            "type": "txt",
                            "summary": "Legacy summary",
                            "filename": "legacy.txt",
                            "text_preview": "Legacy content",
                            "text_length": 14,
                            "extracted": True,
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    source_before = source.read_bytes()
    database_url = migrate_database(tmp_path)
    backup_dir = tmp_path / "backups"

    dry_run = import_legacy_data(
        source=source,
        database_url=database_url,
        dry_run=True,
        backup_dir=None,
        bootstrap_user_email="legacy-owner@example.test",
        bootstrap_user_display_name="Legacy Owner",
    )
    first = import_legacy_data(
        source=source,
        database_url=database_url,
        dry_run=False,
        backup_dir=backup_dir,
        bootstrap_user_email="legacy-owner@example.test",
        bootstrap_user_display_name="Legacy Owner",
    )
    repeat = import_legacy_data(
        source=source,
        database_url=database_url,
        dry_run=False,
        backup_dir=None,
        bootstrap_user_email="legacy-owner@example.test",
        bootstrap_user_display_name="Legacy Owner",
    )

    assert dry_run.errors == []
    assert dry_run.courses_created == 1
    assert dry_run.materials_created == 1
    assert first.errors == []
    assert first.users_created == 1
    assert first.courses_created == 1
    assert first.materials_created == 1
    assert repeat.errors == []
    assert repeat.users_created == 0
    assert repeat.courses_skipped == 1
    assert repeat.materials_skipped == 1
    assert source.read_bytes() == source_before
    assert list(backup_dir.glob("legacy-*.json"))


def test_storage_uses_unique_internal_keys_and_bounded_size(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "uploads")
    first = storage.save(
        io.BytesIO(b"first"),
        extension=".txt",
        media_type="text/plain",
        max_bytes=10,
    )
    second = storage.save(
        io.BytesIO(b"second"),
        extension=".txt",
        media_type="text/plain",
        max_bytes=10,
    )

    assert first.storage_key != second.storage_key
    assert storage.exists(first.storage_key)
    assert storage.exists(second.storage_key)
    with pytest.raises(UploadRejected) as error:
        storage.save(
            io.BytesIO(b"too large"),
            extension=".txt",
            media_type="text/plain",
            max_bytes=3,
        )
    assert error.value.code == "UPLOAD_TOO_LARGE"


def test_upload_policy_rejects_path_components_and_invalid_signature(tmp_path: Path) -> None:
    with pytest.raises(UploadRejected) as path_error:
        validate_filename_and_media_type("../outside.txt", "text/plain")
    assert path_error.value.code == "INVALID_FILENAME"

    with pytest.raises(UploadRejected) as windows_error:
        validate_filename_and_media_type(f"C:{chr(92)}outside.txt", "text/plain")
    assert windows_error.value.code == "INVALID_FILENAME"

    storage = LocalFileStorage(tmp_path / "policy-storage")
    with pytest.raises(UploadRejected) as signature_error:
        storage.save(
            io.BytesIO(b"not a pdf"),
            extension=".pdf",
            media_type="application/pdf",
            max_bytes=100,
        )
    assert signature_error.value.code == "INVALID_FILE_SIGNATURE"


def test_text_extraction_reports_required_statuses() -> None:
    extracted = extract_text(io.BytesIO(b"Readable text"), ".txt")
    invalid_utf8 = extract_text(io.BytesIO(bytes([255, 254])), ".txt")
    malformed_pdf = extract_text(io.BytesIO(b"%PDF-1.4"), ".pdf")
    empty = extract_text(io.BytesIO(b""), ".md")

    assert extracted.status == ExtractionStatus.EXTRACTED
    assert invalid_utf8.status == ExtractionStatus.DECODE_ERROR
    assert malformed_pdf.status == ExtractionStatus.PARSE_FAILED
    assert empty.status == ExtractionStatus.EMPTY_CONTENT


def test_public_material_serialization_redacts_storage_implementation(tmp_path: Path) -> None:
    material = Material(
        id=1,
        course_id=1,
        title="Secure material",
        material_type="txt",
        summary="",
        original_filename="notes.txt",
        storage_key="private-key.txt",
        storage_status="STORED",
        extension=".txt",
        extraction_status="EXTRACTED",
    )

    payload = serialize_material(material)
    encoded = json.dumps(payload)

    assert "file_path" not in payload
    assert "storage_key" not in payload
    assert str(tmp_path) not in encoded


def test_missing_database_url_has_explicit_error() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        Settings(database_url="").require_database_url()
