from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from backend.app.core.settings import Settings
from backend.app.db.models import Course, Material, MaterialContent, MaterialSummary, StudyCard, User
from backend.app.repositories import CourseRepository, MaterialRepository, UserRepository

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class ImportSummary:
    users_created: int = 0
    courses_created: int = 0
    courses_skipped: int = 0
    materials_created: int = 0
    materials_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def parse_args() -> argparse.Namespace:
    settings = Settings()
    parser = argparse.ArgumentParser(description="Import CampusAI legacy JSON into LearnPilot.")
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "backend" / "app" / "data" / "courses.json",
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument(
        "--bootstrap-user-email",
        default=settings.legacy_bootstrap_user,
    )
    parser.add_argument(
        "--bootstrap-user-display-name",
        default=settings.legacy_bootstrap_user_display_name,
    )
    return parser.parse_args()


def parse_optional_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00"))


def _optional_text(value: object, max_length: int | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.strip()
    if not result:
        return None
    return result[:max_length] if max_length is not None else result


def _backfill_m2_artifacts(session, material: Material, raw_material: dict[str, object]) -> None:
    """Preserve available M1 data with explicit provenance after the M2 schema exists."""
    now = datetime.now(timezone.utc)
    raw_text = raw_material.get("extracted_text")
    text = raw_text if isinstance(raw_text, str) and raw_text.strip() else None
    if text is not None and material.content is None:
        saved_length = int(raw_material.get("text_length", len(text)))
        partial = saved_length > len(text)
        material.extracted_text = text
        material.text_extracted = not partial
        material.extraction_status = "LEGACY_CONTENT_PARTIAL" if partial else "SUCCESS"
        material.extraction_error_code = "LEGACY_TEXT_TRUNCATED" if partial else None
        material.extraction_error_message = (
            "Only the M1 saved text excerpt is available; re-upload the original file." if partial else None
        )
        session.add(
            MaterialContent(
                material_id=material.id,
                plain_text=text,
                segments=[{"text": text, "source_reference": "旧版提取文本"}],
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                parser_name="m1-legacy-partial" if partial else "m1-legacy",
                parser_version="m1-backfill-v1",
                page_count=0,
            )
        )
    elif text is None and bool(raw_material.get("extracted", False)) and material.content is None:
        material.text_extracted = False
        material.extraction_status = "LEGACY_CONTENT_UNAVAILABLE"
        material.extraction_error_code = "LEGACY_CONTENT_UNAVAILABLE"
        material.extraction_error_message = "M1 did not save extracted text; re-upload the original file."

    summary = _optional_text(raw_material.get("ai_summary"))
    if summary is not None and material.summary_artifact is None:
        generated_at = parse_optional_datetime(raw_material.get("summary_updated_at")) or now
        session.add(
            MaterialSummary(
                material_id=material.id,
                overview=summary,
                key_concepts=[],
                important_points=[],
                common_mistakes=[],
                review_suggestions=[],
                model_provider="legacy-mock",
                model_name="campusai-m1",
                prompt_version="legacy_m1_mock",
                created_at=generated_at,
                updated_at=generated_at,
            )
        )

    legacy_cards = raw_material.get("cards")
    if isinstance(legacy_cards, list) and not material.study_cards:
        generated_at = parse_optional_datetime(raw_material.get("cards_generated_at")) or now
        order_index = 0
        for legacy_card in legacy_cards:
            if not isinstance(legacy_card, dict):
                continue
            question = _optional_text(legacy_card.get("question"))
            answer = _optional_text(legacy_card.get("answer"))
            if question is None or answer is None:
                continue
            order_index += 1
            session.add(
                StudyCard(
                    material_id=material.id,
                    question=question,
                    answer=answer,
                    knowledge_hint=_optional_text(legacy_card.get("knowledge_hint"), 500),
                    source_reference=_optional_text(legacy_card.get("source_reference"), 255),
                    order_index=order_index,
                    model_provider="legacy-mock",
                    model_name="campusai-m1",
                    prompt_version="legacy_m1_mock",
                    created_at=generated_at,
                    updated_at=generated_at,
                )
            )


def backup_source(source: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = backup_dir / f"{source.stem}-{timestamp}{source.suffix}"
    shutil.copy2(source, destination)
    return destination


def get_or_create_bootstrap_user(
    repository: UserRepository,
    dry_run: bool,
    email: str,
    display_name: str,
) -> tuple[User | None, bool]:
    existing = repository.get_by_email(email)
    if existing is not None:
        return existing, False
    if dry_run:
        return None, True
    return repository.add(
        User(
            email=email,
            display_name=display_name,
            is_active=True,
        )
    ), True


def import_legacy_data(
    *,
    source: Path,
    database_url: str,
    dry_run: bool,
    backup_dir: Path | None,
    bootstrap_user_email: str = "legacy-bootstrap@learnpilot.local",
    bootstrap_user_display_name: str = "Legacy CampusAI",
) -> ImportSummary:
    summary = ImportSummary()
    if not source.is_file():
        summary.errors.append(f"Source file does not exist: {source}")
        return summary

    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        summary.errors.append(f"Unable to read source JSON: {error}")
        return summary

    if not isinstance(payload, dict) or not isinstance(payload.get("courses"), list):
        summary.errors.append("Source JSON does not contain a courses array.")
        return summary

    if backup_dir is not None and not dry_run:
        try:
            backup_source(source, backup_dir)
        except OSError as error:
            summary.errors.append(f"Unable to back up source JSON: {error}")
            return summary

    engine = create_engine(database_url, future=True)
    existing_tables = set(inspect(engine).get_table_names())
    m2_artifacts_available = {
        "material_contents",
        "material_summaries",
        "study_cards",
    }.issubset(existing_tables)
    if "users" not in existing_tables:
        summary.errors.append("Database schema is missing. Run alembic upgrade head first.")
        return summary

    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        user_repository = UserRepository(session)
        course_repository = CourseRepository(session)
        material_repository = MaterialRepository(session)

        with session.begin():
            bootstrap_user, created = get_or_create_bootstrap_user(
                user_repository,
                dry_run,
                bootstrap_user_email,
                bootstrap_user_display_name,
            )
            if created:
                summary.users_created += 1

        course_map: dict[int, int] = {}
        source_materials = payload.get("materials", {})
        if not isinstance(source_materials, dict):
            summary.errors.append("Source JSON materials must be an object.")
            return summary

        for raw_course in payload["courses"]:
            if not isinstance(raw_course, dict):
                summary.errors.append("Skipped invalid course record.")
                continue
            legacy_id = raw_course.get("id")
            if not isinstance(legacy_id, int):
                summary.errors.append("Skipped course with invalid legacy id.")
                continue

            course_key = f"legacy-json:course:{legacy_id}"
            try:
                with session.begin():
                    existing = course_repository.get_by_legacy_key(course_key)
                    if existing is not None:
                        summary.courses_skipped += 1
                        course_map[legacy_id] = existing.id
                    elif dry_run:
                        summary.courses_created += 1
                        course_map[legacy_id] = legacy_id
                    else:
                        if bootstrap_user is None:
                            raise RuntimeError("Bootstrap user is unavailable.")
                        course = course_repository.add(
                            Course(
                                id=legacy_id,
                                owner_id=bootstrap_user.id,
                                name=str(raw_course.get("name", "Untitled course")),
                                description=str(raw_course.get("description", "")),
                                category=str(raw_course.get("semester", "")) or None,
                                legacy_key=course_key,
                            )
                        )
                        summary.courses_created += 1
                        course_map[legacy_id] = course.id
            except Exception as error:
                summary.errors.append(f"Course {legacy_id}: {error}")
                continue

            raw_materials = source_materials.get(str(legacy_id), [])
            if not isinstance(raw_materials, list):
                summary.errors.append(f"Course {legacy_id}: materials are not an array.")
                continue

            for raw_material in raw_materials:
                if not isinstance(raw_material, dict):
                    summary.errors.append(f"Course {legacy_id}: skipped invalid material record.")
                    continue
                material_id = raw_material.get("id")
                if not isinstance(material_id, int):
                    summary.errors.append(f"Course {legacy_id}: skipped material with invalid id.")
                    continue
                material_key = f"legacy-json:material:{legacy_id}:{material_id}"
                try:
                    with session.begin():
                        existing_material = material_repository.get_by_legacy_key(material_key)
                        if existing_material is not None:
                            if m2_artifacts_available:
                                _backfill_m2_artifacts(session, existing_material, raw_material)
                            summary.materials_skipped += 1
                            continue
                        if dry_run:
                            summary.materials_created += 1
                            continue
                        preview = str(raw_material.get("text_preview", ""))
                        filename = raw_material.get("filename")
                        if filename is not None:
                            filename = str(filename)
                        created_material = material_repository.add(
                            Material(
                                id=material_id,
                                course_id=course_map[legacy_id],
                                title=str(raw_material.get("title", "Untitled material")),
                                material_type=str(raw_material.get("type", "document")),
                                summary=str(raw_material.get("summary", "")),
                                original_filename=filename,
                                storage_status=("LEGACY_FILE_UNMIGRATED" if filename else "NOT_STORED"),
                                extension=Path(filename).suffix.lower() if filename else None,
                                size_bytes=0,
                                text_extracted=bool(raw_material.get("extracted", False)),
                                text_preview=preview,
                                text_length=int(raw_material.get("text_length", len(preview))),
                                extraction_status=(
                                    "EXTRACTED" if raw_material.get("extracted", False) else "NOT_REQUESTED"
                                ),
                                ai_summary=raw_material.get("ai_summary"),
                                summary_generated=raw_material.get("summary_generated"),
                                summary_method=raw_material.get("summary_method"),
                                summary_updated_at=parse_optional_datetime(raw_material.get("summary_updated_at")),
                                cards=raw_material.get("cards"),
                                cards_generated=raw_material.get("cards_generated"),
                                cards_generated_at=parse_optional_datetime(raw_material.get("cards_generated_at")),
                                cards_method=raw_material.get("cards_method"),
                                legacy_key=material_key,
                            )
                        )
                        if m2_artifacts_available:
                            _backfill_m2_artifacts(session, created_material, raw_material)
                        summary.materials_created += 1
                except Exception as error:
                    summary.errors.append(f"Material {material_id}: {error}")
    finally:
        session.close()
        engine.dispose()

    return summary


def main() -> int:
    args = parse_args()
    summary = import_legacy_data(
        source=args.source,
        database_url=args.database_url,
        dry_run=args.dry_run,
        backup_dir=args.backup_dir,
        bootstrap_user_email=args.bootstrap_user_email,
        bootstrap_user_display_name=args.bootstrap_user_display_name,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 1 if summary.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
