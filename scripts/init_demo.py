"""Create an isolated LearnPilot demo environment from the curated snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "demo_data"
EXPECTED_REVISION = "0019_m8_mastery_history"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(root: Path) -> None:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    expected = manifest["files"]
    if set(expected) != {"demo.sqlite3", "uploads/978074a253094d41bb66991b20fefec3.txt"}:
        raise ValueError("Unexpected manifest files")
    for name, expected_hash in expected.items():
        if digest(root / name) != expected_hash:
            raise ValueError(f"Demo file integrity check failed: {name}")
    with sqlite3.connect(f"file:{(root / 'demo.sqlite3').as_posix()}?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Demo database integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Demo database has foreign key errors")
        revision = db.execute("SELECT version_num FROM alembic_version").fetchone()
        if revision != (EXPECTED_REVISION,):
            raise ValueError(f"Incompatible database revision: {revision}")
        for table in (
            "assessments",
            "responses",
            "learning_evidence",
            "learning_sessions",
            "learning_plans",
            "student_knowledge_states",
            "mastery_history",
            "tutor_messages",
        ):
            if db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]:
                raise ValueError(f"Demo contains learning state: {table}")
        if db.execute("SELECT COUNT(*) FROM courses").fetchone()[0] != 1:
            raise ValueError("Expected one demo course")
        if db.execute("SELECT COUNT(*) FROM questions WHERE validation_status='validated'").fetchone()[0] < 8:
            raise ValueError("Insufficient validated questions")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destination", required=True, type=Path, help="New directory for an isolated database and upload directory"
    )
    args = parser.parse_args()
    destination = args.destination.expanduser().resolve()
    if destination.exists():
        marker = destination / "manifest.json"
        if (
            destination.is_dir()
            and marker.is_file()
            and marker.read_bytes() == (FIXTURE / "manifest.json").read_bytes()
            and (destination / "demo.sqlite3").is_file()
            and (destination / "uploads" / "978074a253094d41bb66991b20fefec3.txt").is_file()
        ):
            print(f"Demo already initialized; existing state preserved: {destination}")
            return
        raise SystemExit(f"Destination already exists, nothing overwritten: {destination}")
    if not destination.parent.is_dir():
        raise SystemExit(f"Destination parent does not exist: {destination.parent}")
    validate(FIXTURE)
    with tempfile.TemporaryDirectory(prefix=".learnpilot-demo-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "data"
        staging.mkdir()
        shutil.copy2(FIXTURE / "demo.sqlite3", staging / "demo.sqlite3")
        shutil.copytree(FIXTURE / "uploads", staging / "uploads")
        shutil.copy2(FIXTURE / "manifest.json", staging / "manifest.json")
        validate(staging)
        try:
            destination.mkdir()
        except FileExistsError as error:
            raise SystemExit(f"Destination already exists, nothing overwritten: {destination}") from error
        try:
            shutil.copy2(staging / "demo.sqlite3", destination / "demo.sqlite3")
            shutil.copytree(staging / "uploads", destination / "uploads")
            shutil.copy2(staging / "manifest.json", destination / "manifest.json")
        except OSError as error:
            raise SystemExit(
                f"Initialization interrupted; inspect the new directory: {destination}: {error}"
            ) from error
    print(f"Demo created: {destination}")
    print(f"DATABASE_URL=sqlite+pysqlite:///{(destination / 'demo.sqlite3').as_posix()}")
    print(f"UPLOAD_ROOT={(destination / 'uploads').as_posix()}")
    print("LEGACY_BOOTSTRAP_USER=legacy-bootstrap@learnpilot.local")


if __name__ == "__main__":
    main()
