from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import BinaryIO

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import Course, Material, MaterialContent, User
from backend.app.db.session import get_db
from backend.app.documents import ParseStatus, parse_document
from backend.app.repositories import (
    CourseRepository,
    MaterialContentRepository,
    MaterialRepository,
    UserRepository,
)
from backend.app.schemas.course import CourseCreate, CourseUpdate, MaterialCreate
from backend.app.storage import LocalFileStorage, StorageError
from backend.app.storage.policy import validate_filename_and_media_type

logger = logging.getLogger(__name__)
LEGACY_EXTRACTED_TEXT_LIMIT = 20_000
PREVIEW_LENGTH = 1_600


class ResourceNotFoundError(Exception):
    def __init__(self, resource: str) -> None:
        self.resource = resource
        super().__init__(f"{resource} not found")


class MaterialNotParsedError(ValueError):
    pass


def serialize_course(course: Course, material_count: int = 0) -> dict[str, object]:
    return {
        "id": course.id,
        "name": course.name,
        "description": course.description,
        "category": course.category,
        "learning_goal": course.learning_goal,
        "target_date": course.target_date,
        "created_at": course.created_at,
        "updated_at": course.updated_at,
        "material_count": material_count,
        "semester": course.category or "",
    }


def serialize_material(material: Material) -> dict[str, object]:
    content = material.content
    return {
        "id": material.id,
        "course_id": material.course_id,
        "title": material.title,
        "type": material.material_type,
        "summary": material.summary,
        "filename": material.original_filename,
        "original_filename": material.original_filename,
        "media_type": material.media_type,
        "extension": material.extension,
        "size_bytes": material.size_bytes,
        "storage_status": material.storage_status,
        "text_preview": material.text_preview,
        "text_length": material.text_length,
        "extracted": material.text_extracted,
        "extraction_status": material.extraction_status,
        "extraction_error_code": material.extraction_error_code,
        "extraction_error_message": material.extraction_error_message,
        "parser_name": content.parser_name if content else None,
        "parser_version": content.parser_version if content else None,
        "page_count": content.page_count if content else 0,
        "created_at": material.created_at,
        "updated_at": material.updated_at,
        "ai_summary": material.ai_summary,
        "summary_generated": material.summary_generated,
        "summary_method": material.summary_method,
        "summary_updated_at": material.summary_updated_at,
        "cards": [serialize_study_card(card) for card in material.study_cards] if material.study_cards else None,
        "cards_generated": material.cards_generated,
        "cards_generated_at": material.cards_generated_at,
        "cards_method": material.cards_method,
    }


def serialize_study_card(card: object) -> dict[str, object]:
    created_at = card.created_at
    if hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()
    return {
        "id": card.id,
        "question": card.question,
        "answer": card.answer,
        "knowledge_hint": card.knowledge_hint,
        "source_reference": card.source_reference,
        "order_index": card.order_index,
        "source_material_id": card.material_id,
        "card_type": "study",
        "created_at": created_at,
    }


class CourseService:
    def __init__(
        self,
        session: Session,
        course_repository: CourseRepository,
        material_repository: MaterialRepository,
        content_repository: MaterialContentRepository,
        user_repository: UserRepository,
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        self.session = session
        self.course_repository = course_repository
        self.material_repository = material_repository
        self.content_repository = content_repository
        self.user_repository = user_repository
        self.storage = storage
        self.settings = settings

    def list_courses(self) -> list[tuple[Course, int]]:
        with self.session.begin():
            owner = self._get_or_create_owner()
            return self.course_repository.list_with_material_counts(owner.id)

    def create_course(self, payload: CourseCreate) -> Course:
        with self.session.begin():
            owner = self._get_or_create_owner()
            return self.course_repository.add(
                Course(
                    owner_id=owner.id,
                    name=payload.name,
                    description=payload.description or "",
                    category=payload.category,
                    learning_goal=payload.learning_goal,
                    target_date=payload.target_date,
                )
            )

    def get_course(self, course_id: int) -> Course:
        with self.session.begin():
            owner = self._get_or_create_owner()
            return self._require_course(course_id, owner.id)

    def update_course(self, course_id: int, payload: CourseUpdate) -> Course:
        with self.session.begin():
            owner = self._get_or_create_owner()
            course = self._require_course(course_id, owner.id)
            for field, value in payload.model_dump(exclude_unset=True).items():
                if field == "description" and value is None:
                    value = ""
                setattr(course, field, value)
            self.session.flush()
            return course

    def delete_course(self, course_id: int) -> None:
        with self.session.begin():
            owner = self._get_or_create_owner()
            course = self._require_course(course_id, owner.id)
            storage_keys = [
                material.storage_key
                for material in self.material_repository.list_for_course(course.id)
                if material.storage_key
            ]
        self._delete_storage_keys(storage_keys, resource="course")
        with self.session.begin():
            owner = self._get_or_create_owner()
            course = self._require_course(course_id, owner.id)
            self.course_repository.delete(course)

    def list_materials(self, course_id: int) -> list[Material]:
        with self.session.begin():
            owner = self._get_or_create_owner()
            self._require_course(course_id, owner.id)
            return self.material_repository.list_for_owned_course(course_id, owner.id)

    def get_material(self, material_id: int) -> Material:
        with self.session.begin():
            owner = self._get_or_create_owner()
            return self._require_material(material_id, owner.id)

    def create_material(self, course_id: int, payload: MaterialCreate) -> Material:
        with self.session.begin():
            owner = self._get_or_create_owner()
            self._require_course(course_id, owner.id)
            return self.material_repository.add(
                Material(
                    course_id=course_id,
                    title=payload.title,
                    material_type=payload.type,
                    summary=payload.summary,
                    storage_status="NOT_STORED",
                    extraction_status="NOT_REQUESTED",
                )
            )

    def create_uploaded_material(
        self, course_id: int, filename: str, media_type: str | None, source: BinaryIO
    ) -> Material:
        extension = validate_filename_and_media_type(filename, media_type)
        saved_file = None
        try:
            with self.session.begin():
                owner = self._get_or_create_owner()
                self._require_course(course_id, owner.id)
                saved_file = self.storage.save(
                    source,
                    extension=extension,
                    media_type=media_type or "",
                    max_bytes=self.settings.max_upload_bytes,
                )
                with self.storage.open_read(saved_file.storage_key) as stored_file:
                    parsed = parse_document(stored_file, extension)
                material = self.material_repository.add(
                    Material(
                        course_id=course_id,
                        title=Path(filename).stem or filename,
                        material_type=extension.removeprefix("."),
                        summary=f"Uploaded course material: {filename}",
                        original_filename=filename,
                        storage_key=saved_file.storage_key,
                        storage_status="STORED",
                        media_type=media_type,
                        extension=extension,
                        size_bytes=saved_file.size_bytes,
                        text_extracted=parsed.successful,
                        text_preview=parsed.text[:PREVIEW_LENGTH],
                        text_length=len(parsed.text),
                        extracted_text=parsed.text[:LEGACY_EXTRACTED_TEXT_LIMIT] if parsed.successful else None,
                        extraction_status=parsed.status.value,
                        extraction_error_code=parsed.error_code,
                        extraction_error_message=parsed.error_message,
                    )
                )
                if parsed.successful:
                    self.content_repository.save(
                        MaterialContent(
                            material_id=material.id,
                            plain_text=parsed.text,
                            segments=[segment.to_dict() for segment in parsed.segments],
                            content_hash=hashlib.sha256(parsed.text.encode("utf-8")).hexdigest(),
                            parser_name=parsed.parser_name,
                            parser_version=parsed.parser_version,
                            page_count=parsed.page_count,
                        )
                    )
                self.session.flush()
                return material
        except Exception:
            if saved_file is not None:
                try:
                    self.storage.delete(saved_file.storage_key)
                except StorageError:
                    logger.exception("Unable to clean up failed upload")
            raise

    def delete_material(self, material_id: int) -> None:
        with self.session.begin():
            owner = self._get_or_create_owner()
            material = self._require_material(material_id, owner.id)
            storage_key = material.storage_key
        self._delete_storage_keys([storage_key] if storage_key else [], resource="material")
        with self.session.begin():
            owner = self._get_or_create_owner()
            material = self._require_material(material_id, owner.id)
            self.material_repository.delete(material)

    def get_content(self, material_id: int) -> MaterialContent:
        with self.session.begin():
            owner = self._get_or_create_owner()
            material = self._require_material(material_id, owner.id)
            content = self.content_repository.get_for_material(material.id)
            if content is None or material.extraction_status not in {ParseStatus.SUCCESS.value, "EXTRACTED"}:
                raise MaterialNotParsedError("Material has not been parsed successfully.")
            return content

    def search_materials(self, keyword: str, course_id: int | None = None) -> list[Material]:
        with self.session.begin():
            owner = self._get_or_create_owner()
            if course_id is not None:
                self._require_course(course_id, owner.id)
            return self.material_repository.search(keyword, owner.id, course_id)

    def _get_or_create_owner(self) -> User:
        owner = self.user_repository.get_by_email(self.settings.legacy_bootstrap_user)
        if owner is not None:
            return owner
        return self.user_repository.add(
            User(
                email=self.settings.legacy_bootstrap_user,
                display_name=self.settings.legacy_bootstrap_user_display_name,
                is_active=True,
            )
        )

    def _require_course(self, course_id: int, owner_id: int) -> Course:
        course = self.course_repository.get_for_owner(course_id, owner_id)
        if course is None:
            raise ResourceNotFoundError("Course")
        return course

    def _require_material(self, material_id: int, owner_id: int) -> Material:
        material = self.material_repository.get_for_owner(material_id, owner_id)
        if material is None:
            raise ResourceNotFoundError("Material")
        return material

    def _delete_storage_keys(self, storage_keys: list[str], *, resource: str) -> None:
        for storage_key in storage_keys:
            try:
                self.storage.delete(storage_key)
            except StorageError as error:
                logger.exception("Storage deletion failed resource=%s storage_key=%s", resource, storage_key)
                raise StorageError("Unable to delete the stored file. The database record was preserved.") from error


def get_course_service(session: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> CourseService:
    return CourseService(
        session=session,
        course_repository=CourseRepository(session),
        material_repository=MaterialRepository(session),
        content_repository=MaterialContentRepository(session),
        user_repository=UserRepository(session),
        storage=LocalFileStorage(settings.normalized_upload_root),
        settings=settings,
    )


__all__ = [
    "CourseService",
    "MaterialNotParsedError",
    "ResourceNotFoundError",
    "get_course_service",
    "serialize_course",
    "serialize_material",
    "serialize_study_card",
]
