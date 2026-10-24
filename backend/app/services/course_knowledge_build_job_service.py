from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Event, Thread

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import (
    CourseKnowledgeBuildState,
    KnowledgeCandidateResolution,
    Material,
    User,
)
from backend.app.db.session import get_db, get_session_factory
from backend.app.repositories import (
    CourseKnowledgeBuildStateRepository,
    CourseRepository,
    KnowledgeCanonicalizationRunRepository,
    KnowledgeEdgeRepository,
    KnowledgeExtractionRunRepository,
    KnowledgeNodeRepository,
    KnowledgeRelationshipRunRepository,
    MaterialContentRepository,
    MaterialRepository,
    UserRepository,
)
from backend.app.services.course_knowledge_build_service import (
    CourseKnowledgeBuildError,
    capture_course_knowledge_checkpoint,
    get_course_knowledge_build_service,
    restore_course_knowledge_checkpoint,
)
from backend.app.services.course_service import ResourceNotFoundError

logger = logging.getLogger(__name__)
BUILD_LEASE = timedelta(minutes=30)


@dataclass(frozen=True)
class CourseKnowledgeBuildJob:
    job_id: int
    status: str
    stage: str | None
    reused: bool
    should_schedule: bool


@dataclass(frozen=True)
class CourseKnowledgeBuildStatus:
    course_id: int
    state: str
    stage: str | None
    job_id: int | None
    material_count: int
    ready_material_count: int
    synced_material_count: int
    pending_sync_material_count: int
    pending_parse_material_count: int
    failed_material_count: int
    last_added_node_count: int
    last_reused_node_count: int
    node_count: int
    contains_edge_count: int
    prerequisite_edge_count: int
    needs_update: bool
    can_build: bool
    has_model: bool
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _material_snapshot(
    materials: list[Material], content_repository: MaterialContentRepository
) -> tuple[list[Material], str]:
    ready: list[Material] = []
    snapshot: list[tuple[int, str]] = []
    for material in materials:
        if material.extraction_status not in {"SUCCESS", "EXTRACTED"}:
            continue
        content = content_repository.get_for_material(material.id)
        if content is None or not content.plain_text.strip():
            continue
        ready.append(material)
        snapshot.append((material.id, content.content_hash))
    encoded = json.dumps(sorted(snapshot), separators=(",", ":")).encode()
    return ready, hashlib.sha256(encoded).hexdigest()


class CourseKnowledgeBuildJobService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.states = CourseKnowledgeBuildStateRepository(session)
        self.courses = CourseRepository(session)
        self.materials = MaterialRepository(session)
        self.contents = MaterialContentRepository(session)
        self.users = UserRepository(session)
        self.canonicalization_runs = KnowledgeCanonicalizationRunRepository(session)
        self.nodes = KnowledgeNodeRepository(session)
        self.edges = KnowledgeEdgeRepository(session)

    def get_status(self, course_id: int) -> CourseKnowledgeBuildStatus:
        with self.session.begin():
            self._require_owned_course(course_id)
            state = self.states.get_for_course(course_id)
            if state is not None:
                self._recover_expired(state)
            materials = self.materials.list_for_course(course_id)
            ready, current_snapshot = _material_snapshot(materials, self.contents)
            extracted_material_ids = {
                run.material_id
                for run in KnowledgeExtractionRunRepository(self.session).list_current_for_course(course_id)
            }
            ready_material_ids = {material.id for material in ready}
            failed_material_count = sum(
                material.extraction_status
                in {
                    "EMPTY_CONTENT",
                    "DECODE_ERROR",
                    "UNSUPPORTED_FORMAT",
                    "PARSE_FAILED",
                    "LEGACY_CONTENT_PARTIAL",
                    "LEGACY_CONTENT_UNAVAILABLE",
                }
                or material.extraction_error_code is not None
                for material in materials
            )
            canonical_ids = self._canonical_node_ids(course_id)
            active_ids = {node.id for node in self.nodes.list_by_course(course_id)}
            canonical_ids &= active_ids
            edges = [
                edge
                for edge in self.edges.list_current_by_course(course_id)
                if edge.source_node_id in canonical_ids and edge.target_node_id in canonical_ids
            ]
            has_model = bool(canonical_ids) and (
                KnowledgeRelationshipRunRepository(self.session).get_current_for_course(course_id) is not None
            )
            needs_update = bool(
                state is not None
                and state.success_material_snapshot_hash is not None
                and state.success_material_snapshot_hash != current_snapshot
            )
            if has_model and (state is None or state.success_material_snapshot_hash is None):
                # M3-D courses predate the durable build snapshot. A current
                # extraction tied to the stored content hash is verifiable
                # evidence that a parsed material participated in the model.
                needs_update = any(material.id not in extracted_material_ids for material in ready)
            if state is not None and state.status == "running":
                display_state = "running"
            elif state is not None and state.status == "failed":
                display_state = "update_failed" if has_model else "failed"
            elif has_model:
                display_state = "update_available" if needs_update else "ready"
            elif not materials:
                display_state = "no_materials"
            elif not ready:
                display_state = "not_ready"
            else:
                display_state = "not_built"
            return CourseKnowledgeBuildStatus(
                course_id=course_id,
                state=display_state,
                stage=state.stage if state is not None and state.status == "running" else None,
                job_id=state.job_id if state is not None and state.job_id > 0 else None,
                material_count=len(materials),
                ready_material_count=len(ready),
                synced_material_count=len(ready_material_ids & extracted_material_ids),
                pending_sync_material_count=len(ready_material_ids - extracted_material_ids),
                pending_parse_material_count=len(materials) - len(ready) - failed_material_count,
                failed_material_count=failed_material_count,
                last_added_node_count=state.last_added_node_count if state is not None else 0,
                last_reused_node_count=state.last_reused_node_count if state is not None else 0,
                node_count=len(canonical_ids),
                contains_edge_count=sum(edge.relation_type.value == "contains" for edge in edges),
                prerequisite_edge_count=sum(edge.relation_type.value == "prerequisite" for edge in edges),
                needs_update=needs_update,
                can_build=bool(ready) and display_state != "running",
                has_model=has_model,
                error_code=state.error_code if state is not None and state.status == "failed" else None,
                error_message=state.error_message if state is not None and state.status == "failed" else None,
                started_at=state.started_at if state is not None else None,
                completed_at=state.completed_at if state is not None else None,
            )

    def start(self, course_id: int) -> CourseKnowledgeBuildJob:
        for attempt in range(2):
            try:
                return self._start_once(course_id)
            except IntegrityError:
                self.session.rollback()
                if attempt:
                    raise
        raise AssertionError("unreachable")

    def _start_once(self, course_id: int) -> CourseKnowledgeBuildJob:
        with self.session.begin():
            self._require_owned_course(course_id)
            materials = self.materials.list_for_course(course_id)
            ready, snapshot_hash = _material_snapshot(materials, self.contents)
            if not ready:
                raise CourseKnowledgeBuildError(
                    "KNOWLEDGE_MODEL_BUILD_NOT_READY",
                    "At least one successfully parsed course material is required before building a knowledge model.",
                )
            state = self.states.get_for_course(course_id)
            if state is None:
                state = self.states.create(CourseKnowledgeBuildState(course_id=course_id, job_id=0, status="idle"))
            self._recover_expired(state)
            if state.status == "running":
                return CourseKnowledgeBuildJob(state.job_id, state.status, state.stage, True, False)
            if (
                state.status == "success"
                and state.success_material_snapshot_hash == snapshot_hash
                and self._canonical_node_ids(course_id)
                and KnowledgeRelationshipRunRepository(self.session).get_current_for_course(course_id) is not None
            ):
                return CourseKnowledgeBuildJob(state.job_id, state.status, state.stage, True, False)
            claimed = self.states.claim(
                course_id,
                material_snapshot_hash=snapshot_hash,
                checkpoint_json=capture_course_knowledge_checkpoint(self.session, course_id),
                started_at=_utc_now(),
            )
            if not claimed:
                current = self.states.get_for_course(course_id)
                if current is None:
                    raise RuntimeError("Knowledge build claim disappeared.")
                return CourseKnowledgeBuildJob(current.job_id, current.status, current.stage, True, False)
            self.session.refresh(state)
            return CourseKnowledgeBuildJob(state.job_id, state.status, state.stage, False, True)

    def _canonical_node_ids(self, course_id: int) -> set[int]:
        run = self.canonicalization_runs.get_current_for_course(course_id)
        if run is None:
            return set()
        return set(
            self.session.scalars(
                select(KnowledgeCandidateResolution.knowledge_node_id).where(
                    KnowledgeCandidateResolution.course_id == course_id,
                    KnowledgeCandidateResolution.canonicalization_run_id == run.id,
                )
            )
        )

    def _recover_expired(self, state: CourseKnowledgeBuildState) -> None:
        if state.status != "running" or state.heartbeat_at is None:
            return
        if _aware(state.heartbeat_at) + BUILD_LEASE > _utc_now():
            return
        # The relationship stage commits before the background task marks success.
        # If that publication finished, keep the valid result; otherwise restore.
        checkpoint = json.loads(state.checkpoint_json or "{}")
        previous_relationship_run_id = checkpoint.get("relationship_run_id")
        current_relationship_run = KnowledgeRelationshipRunRepository(self.session).get_current_for_course(
            state.course_id
        )
        if (
            state.stage == "relationships"
            and current_relationship_run is not None
            and current_relationship_run.id != previous_relationship_run_id
        ):
            state.status = "success"
            state.stage = "complete"
            state.success_material_snapshot_hash = state.requested_material_snapshot_hash
            state.last_success_at = _utc_now()
            state.error_code = None
            state.error_message = None
        else:
            if state.checkpoint_json is not None:
                restore_course_knowledge_checkpoint(self.session, state.course_id, state.checkpoint_json)
            state.status = "failed"
            state.stage = None
            state.error_code = "KNOWLEDGE_MODEL_BUILD_INTERRUPTED"
            state.error_message = "Knowledge model build was interrupted; the previous model remains available."
        state.completed_at = _utc_now()
        state.heartbeat_at = None
        state.checkpoint_json = None
        self.states.save(state)

    def _require_owned_course(self, course_id: int) -> None:
        owner = self.users.get_by_email(self.settings.legacy_bootstrap_user)
        if owner is None:
            owner = self.users.add(
                User(
                    email=self.settings.legacy_bootstrap_user,
                    display_name=self.settings.legacy_bootstrap_user_display_name,
                    is_active=True,
                )
            )
        if self.courses.get_for_owner(course_id, owner.id) is None:
            raise ResourceNotFoundError("Course")


def run_course_knowledge_build_job(course_id: int, job_id: int, settings: Settings) -> None:
    """Execute after the 202 response with an independent database session."""

    factory = get_session_factory()

    def update_stage(stage: str) -> None:
        with factory() as state_session, state_session.begin():
            state = CourseKnowledgeBuildStateRepository(state_session).get_for_course(course_id)
            if state is not None and state.job_id == job_id and state.status == "running":
                state.stage = stage
                state.heartbeat_at = _utc_now()

    stop_heartbeat = Event()

    def keep_lease_alive() -> None:
        while not stop_heartbeat.wait(15):
            try:
                with factory() as state_session, state_session.begin():
                    state = CourseKnowledgeBuildStateRepository(state_session).get_for_course(course_id)
                    if state is None or state.job_id != job_id or state.status != "running":
                        return
                    state.heartbeat_at = _utc_now()
            except Exception:
                logger.exception("course_knowledge_build_heartbeat_failed course_id=%s job_id=%s", course_id, job_id)

    heartbeat = Thread(target=keep_lease_alive, daemon=True, name=f"knowledge-build-heartbeat-{course_id}")
    heartbeat.start()

    try:
        with factory() as build_session:
            service = get_course_knowledge_build_service(session=build_session, settings=settings)
            result = service.build(course_id, on_stage=update_stage)
    except CourseKnowledgeBuildError as error:
        _finish_failed_job(factory, course_id, job_id, error.code, error.message)
        return
    except Exception:
        logger.exception("course_knowledge_build_job_failed course_id=%s job_id=%s", course_id, job_id)
        _finish_failed_job(
            factory,
            course_id,
            job_id,
            "KNOWLEDGE_MODEL_BUILD_FAILED",
            "Knowledge model build failed; the previous model remains available.",
        )
        return
    finally:
        stop_heartbeat.set()
        heartbeat.join(timeout=2)

    with factory() as state_session, state_session.begin():
        state = CourseKnowledgeBuildStateRepository(state_session).get_for_course(course_id)
        if state is None or state.job_id != job_id or state.status != "running":
            return
        state.status = "success"
        state.stage = "complete"
        state.error_code = None
        state.error_message = None
        state.last_added_node_count = result.added_node_count
        state.last_reused_node_count = result.reused_node_count
        state.success_material_snapshot_hash = state.requested_material_snapshot_hash
        state.last_success_at = _utc_now()
        state.completed_at = state.last_success_at
        state.heartbeat_at = None
        state.checkpoint_json = None
        logger.info(
            "course_knowledge_build_job_completed course_id=%s job_id=%s nodes=%s edges=%s",
            course_id,
            job_id,
            result.node_count,
            result.contains_edge_count + result.prerequisite_edge_count,
        )


def _finish_failed_job(factory: sessionmaker[Session], course_id: int, job_id: int, code: str, message: str) -> None:
    with factory() as session, session.begin():
        states = CourseKnowledgeBuildStateRepository(session)
        state = states.get_for_course(course_id)
        if state is None or state.job_id != job_id or state.status != "running":
            return
        if state.checkpoint_json is not None:
            restore_course_knowledge_checkpoint(session, course_id, state.checkpoint_json)
        state.status = "failed"
        state.stage = None
        state.error_code = code
        state.error_message = message[:255]
        state.completed_at = _utc_now()
        state.heartbeat_at = None
        state.checkpoint_json = None
        states.save(state)


def get_course_knowledge_build_job_service(
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CourseKnowledgeBuildJobService:
    return CourseKnowledgeBuildJobService(session, settings)
