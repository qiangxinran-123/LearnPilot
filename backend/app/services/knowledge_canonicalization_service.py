from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.ai import AIServiceError, LLMClient, get_llm_client
from backend.app.ai.models import KnowledgeCanonicalizationOutput
from backend.app.ai.prompts import knowledge_canonicalization as canonicalization_prompt
from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import (
    KnowledgeCandidate,
    KnowledgeCandidateResolution,
    KnowledgeCanonicalizationRun,
    KnowledgeNode,
    KnowledgeSource,
    User,
)
from backend.app.db.session import get_db
from backend.app.models import (
    KnowledgeCanonicalizationStatus,
    KnowledgeDifficulty,
    KnowledgeImportance,
    KnowledgeResolutionType,
    normalize_knowledge_name,
)
from backend.app.repositories import (
    CourseRepository,
    KnowledgeCandidateRepository,
    KnowledgeCandidateResolutionRepository,
    KnowledgeCanonicalizationRunRepository,
    KnowledgeExtractionRunRepository,
    KnowledgeNodeRepository,
    KnowledgeSourceRepository,
    MaterialContentRepository,
    UserRepository,
)
from backend.app.services.course_service import ResourceNotFoundError

logger = logging.getLogger(__name__)

_IMPORTANCE_RANK = {
    KnowledgeImportance.LOW: 0,
    KnowledgeImportance.MEDIUM: 1,
    KnowledgeImportance.HIGH: 2,
}
_DIFFICULTY_RANK = {
    KnowledgeDifficulty.BASIC: 0,
    KnowledgeDifficulty.INTERMEDIATE: 1,
    KnowledgeDifficulty.ADVANCED: 2,
}
_TOKEN_PATTERN = re.compile(r"[a-z0-9+#]+|[\u3400-\u9fff]+")


class KnowledgeCanonicalizationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class CandidateSnapshot:
    course_id: int
    candidates: list[KnowledgeCandidate]
    snapshot_hash: str


@dataclass(frozen=True)
class ExactCandidateGroup:
    normalized_name: str
    candidates: list[KnowledgeCandidate]
    name: str
    description: str
    importance: KnowledgeImportance
    difficulty: KnowledgeDifficulty

    @property
    def representative_id(self) -> int:
        return self.candidates[0].id


@dataclass(frozen=True)
class CanonicalPlan:
    exact_groups: list[ExactCandidateGroup]
    name: str
    description: str
    importance: KnowledgeImportance
    difficulty: KnowledgeDifficulty
    semantic_merge: bool = False

    @property
    def candidates(self) -> list[KnowledgeCandidate]:
        return [candidate for group in self.exact_groups for candidate in group.candidates]


@dataclass(frozen=True)
class KnowledgeCanonicalizationResult:
    run: KnowledgeCanonicalizationRun
    nodes: list[KnowledgeNode]
    resolutions: list[KnowledgeCandidateResolution]
    reused: bool


class KnowledgeCanonicalizationService:
    def __init__(
        self,
        session: Session,
        course_repository: CourseRepository,
        extraction_run_repository: KnowledgeExtractionRunRepository,
        candidate_repository: KnowledgeCandidateRepository,
        content_repository: MaterialContentRepository,
        run_repository: KnowledgeCanonicalizationRunRepository,
        resolution_repository: KnowledgeCandidateResolutionRepository,
        node_repository: KnowledgeNodeRepository,
        source_repository: KnowledgeSourceRepository,
        user_repository: UserRepository,
        settings: Settings,
        llm_client_factory: Callable[[Settings], LLMClient] = get_llm_client,
    ) -> None:
        self.session = session
        self.course_repository = course_repository
        self.extraction_run_repository = extraction_run_repository
        self.candidate_repository = candidate_repository
        self.content_repository = content_repository
        self.run_repository = run_repository
        self.resolution_repository = resolution_repository
        self.node_repository = node_repository
        self.source_repository = source_repository
        self.user_repository = user_repository
        self.settings = settings
        self.llm_client_factory = llm_client_factory

    def get_canonicalization(self, course_id: int) -> KnowledgeCanonicalizationResult:
        with self.session.begin():
            owner = self._get_or_create_owner()
            self._require_course(course_id, owner.id)
            run = self.run_repository.get_current_for_course(course_id)
            if run is None:
                run = self.run_repository.get_latest_for_course(course_id)
            if run is None:
                raise KnowledgeCanonicalizationError(
                    "KNOWLEDGE_CANONICALIZATION_NOT_READY",
                    "Knowledge canonicalization has not been run for this course.",
                )
            nodes = self._nodes_for_run(run) if run.status == KnowledgeCanonicalizationStatus.SUCCESS else []
            resolutions = (
                self.resolution_repository.list_for_run(run.id)
                if run.status == KnowledgeCanonicalizationStatus.SUCCESS
                else []
            )
            return KnowledgeCanonicalizationResult(run, nodes, resolutions, True)

    def canonicalize(
        self,
        course_id: int,
        *,
        regenerate: bool = False,
    ) -> KnowledgeCanonicalizationResult:
        snapshot = self._load_snapshot(course_id)
        exact_groups = self._build_exact_groups(snapshot.candidates)
        semantic_blocks = self._build_semantic_blocks(exact_groups)

        client: LLMClient | None = None
        if semantic_blocks:
            try:
                client = self.llm_client_factory(self.settings)
            except AIServiceError as error:
                raise self._map_ai_error(error) from error
            provider, model = self._client_identity(client)
        else:
            provider, model = "deterministic", "exact-canonicalization-v1"

        with self.session.begin():
            if not regenerate:
                current = self.run_repository.find_current_by_key(
                    course_id,
                    snapshot.snapshot_hash,
                    canonicalization_prompt.PROMPT_VERSION,
                    model,
                    canonicalization_prompt.CONFIGURATION_VERSION,
                )
                if current is not None:
                    return KnowledgeCanonicalizationResult(
                        current,
                        self._nodes_for_run(current),
                        self.resolution_repository.list_for_run(current.id),
                        True,
                    )
            run = self.run_repository.create(
                KnowledgeCanonicalizationRun(
                    course_id=course_id,
                    candidate_snapshot_hash=snapshot.snapshot_hash,
                    status=KnowledgeCanonicalizationStatus.RUNNING,
                    provider=provider,
                    model=model,
                    prompt_version=canonicalization_prompt.PROMPT_VERSION,
                    configuration_version=canonicalization_prompt.CONFIGURATION_VERSION,
                    candidate_count=len(snapshot.candidates),
                    canonical_node_count=0,
                    merged_candidate_count=0,
                    unresolved_count=len(snapshot.candidates),
                    is_current=False,
                )
            )
            run_id = run.id

        try:
            plans = self._build_canonical_plans(exact_groups, semantic_blocks, client)
            self._validate_plan_completeness(snapshot.candidates, plans)
            with self.session.begin():
                current_snapshot = self._collect_snapshot(course_id)
                if current_snapshot.snapshot_hash != snapshot.snapshot_hash:
                    raise KnowledgeCanonicalizationError(
                        "KNOWLEDGE_CANONICALIZATION_NOT_READY",
                        "Knowledge candidates changed during canonicalization; no model was replaced.",
                    )
                run = self.run_repository.get_by_id(run_id)
                if run is None:
                    raise KnowledgeCanonicalizationError(
                        "KNOWLEDGE_CANONICALIZATION_FAILED",
                        "Knowledge canonicalization run no longer exists.",
                    )
                nodes = self._persist_plans(run, plans)
                resolutions = self.resolution_repository.list_for_run(run.id)
                if len(resolutions) != len(snapshot.candidates):
                    raise KnowledgeCanonicalizationError(
                        "KNOWLEDGE_CANONICALIZATION_INVALID_OUTPUT",
                        "Every current candidate must resolve exactly once.",
                    )
                self.node_repository.deactivate_managed_except(course_id, {node.id for node in nodes})
                self.run_repository.clear_current(course_id)
                run.status = KnowledgeCanonicalizationStatus.SUCCESS
                run.canonical_node_count = len(nodes)
                run.merged_candidate_count = len(snapshot.candidates) - len(nodes)
                run.unresolved_count = 0
                run.error_code = None
                run.error_message = None
                run.is_current = True
                run.completed_at = datetime.now(timezone.utc)
                self.run_repository.save(run)
                return KnowledgeCanonicalizationResult(run, nodes, resolutions, False)
        except KnowledgeCanonicalizationError as error:
            self._mark_failed(run_id, error.code, error.message)
            raise
        except AIServiceError as error:
            mapped = self._map_ai_error(error)
            self._mark_failed(run_id, mapped.code, mapped.message)
            raise mapped from error
        except Exception as error:
            logger.exception("knowledge_canonicalization_failed run_id=%s", run_id)
            mapped = KnowledgeCanonicalizationError(
                "KNOWLEDGE_CANONICALIZATION_FAILED",
                "Knowledge canonicalization failed before a valid model could be saved.",
            )
            self._mark_failed(run_id, mapped.code, mapped.message)
            raise mapped from error

    def _load_snapshot(self, course_id: int) -> CandidateSnapshot:
        with self.session.begin():
            owner = self._get_or_create_owner()
            self._require_course(course_id, owner.id)
            return self._collect_snapshot(course_id)

    def _collect_snapshot(self, course_id: int) -> CandidateSnapshot:
        runs = self.extraction_run_repository.list_current_for_course(course_id)
        if not runs:
            raise KnowledgeCanonicalizationError(
                "KNOWLEDGE_CANONICALIZATION_NOT_READY",
                "The course has no current successful knowledge extraction candidates.",
            )
        if len({run.material_id for run in runs}) != len(runs):
            raise KnowledgeCanonicalizationError(
                "KNOWLEDGE_CANONICALIZATION_NOT_READY",
                "Each material must have exactly one current successful extraction run.",
            )
        candidates = self.candidate_repository.list_for_runs([run.id for run in runs])
        if not candidates:
            raise KnowledgeCanonicalizationError(
                "KNOWLEDGE_CANONICALIZATION_NOT_READY",
                "The current extraction runs do not contain knowledge candidates.",
            )
        if len(candidates) > self.settings.knowledge_canonicalization_max_candidates:
            raise KnowledgeCanonicalizationError(
                "KNOWLEDGE_CANONICALIZATION_NOT_READY",
                "The course exceeds the configured canonicalization candidate limit.",
            )

        run_by_id = {run.id: run for run in runs}
        candidates_by_run: dict[int, int] = {run.id: 0 for run in runs}
        content_by_material: dict[int, object] = {}
        snapshot_candidates: list[dict[str, object]] = []
        for candidate in candidates:
            run = run_by_id.get(candidate.extraction_run_id)
            if run is None or candidate.course_id != course_id or candidate.material_id != run.material_id:
                raise KnowledgeCanonicalizationError(
                    "KNOWLEDGE_CANONICALIZATION_NOT_READY",
                    "A knowledge candidate is outside the current course extraction snapshot.",
                )
            candidates_by_run[run.id] += 1
            content = content_by_material.get(candidate.material_id)
            if content is None:
                content = self.content_repository.get_for_material(candidate.material_id)
                content_by_material[candidate.material_id] = content
            if content is None:
                raise KnowledgeCanonicalizationError(
                    "KNOWLEDGE_CANONICALIZATION_NOT_READY",
                    "A candidate source material no longer has parsed content.",
                )
            valid_references = {
                str(segment.get("source_reference"))
                for segment in content.segments
                if isinstance(segment, dict) and segment.get("source_reference") is not None
            }
            if not candidate.sources:
                raise KnowledgeCanonicalizationError(
                    "KNOWLEDGE_CANONICALIZATION_NOT_READY",
                    "Every candidate requires at least one traceable source.",
                )
            source_payload: list[dict[str, object]] = []
            for source in candidate.sources:
                if (
                    source.material_id != candidate.material_id
                    or source.source_reference not in valid_references
                    or not source.excerpt.strip()
                ):
                    raise KnowledgeCanonicalizationError(
                        "KNOWLEDGE_CANONICALIZATION_NOT_READY",
                        "A candidate contains an invalid or stale source reference.",
                    )
                source_payload.append(
                    {
                        "material_id": source.material_id,
                        "source_reference": source.source_reference,
                        "excerpt": source.excerpt,
                    }
                )
            snapshot_candidates.append(
                {
                    "id": candidate.id,
                    "run_id": candidate.extraction_run_id,
                    "material_id": candidate.material_id,
                    "name": candidate.name,
                    "normalized_name": normalize_knowledge_name(candidate.name),
                    "description": candidate.description,
                    "importance": candidate.importance.value,
                    "difficulty": candidate.difficulty.value,
                    "sources": sorted(
                        source_payload,
                        key=lambda item: (item["material_id"], item["source_reference"]),
                    ),
                }
            )
        if any(candidates_by_run[run.id] != run.candidate_count for run in runs):
            raise KnowledgeCanonicalizationError(
                "KNOWLEDGE_CANONICALIZATION_NOT_READY",
                "A current extraction run has an inconsistent candidate count.",
            )

        payload = {
            "course_id": course_id,
            "runs": [
                {
                    "id": run.id,
                    "material_id": run.material_id,
                    "content_hash": run.material_content_hash,
                    "prompt_version": run.prompt_version,
                    "model": run.model,
                }
                for run in runs
            ],
            "candidates": snapshot_candidates,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        return CandidateSnapshot(course_id, candidates, hashlib.sha256(encoded).hexdigest())

    @staticmethod
    def _build_exact_groups(candidates: list[KnowledgeCandidate]) -> list[ExactCandidateGroup]:
        grouped: OrderedDict[str, list[KnowledgeCandidate]] = OrderedDict()
        for candidate in sorted(candidates, key=lambda item: item.id):
            normalized = normalize_knowledge_name(candidate.name)
            grouped.setdefault(normalized, []).append(candidate)
        result: list[ExactCandidateGroup] = []
        for normalized, members in grouped.items():
            display = min(members, key=lambda item: (len(item.name), item.name.casefold(), item.id))
            description = max(members, key=lambda item: (len(item.description), -item.id)).description
            result.append(
                ExactCandidateGroup(
                    normalized_name=normalized,
                    candidates=members,
                    name=display.name,
                    description=description,
                    importance=max(members, key=lambda item: _IMPORTANCE_RANK[item.importance]).importance,
                    difficulty=max(members, key=lambda item: _DIFFICULTY_RANK[item.difficulty]).difficulty,
                )
            )
        return result

    def _build_semantic_blocks(
        self,
        exact_groups: list[ExactCandidateGroup],
    ) -> list[list[ExactCandidateGroup]]:
        if len(exact_groups) < 2:
            return []
        block_size = self.settings.knowledge_canonicalization_block_size
        if len(exact_groups) <= block_size:
            return self._split_block_for_context(exact_groups)

        parent = list(range(len(exact_groups)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left: int, right: int) -> None:
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        for left in range(len(exact_groups)):
            for right in range(left + 1, len(exact_groups)):
                if self._same_semantic_block(exact_groups[left], exact_groups[right]):
                    union(left, right)

        components: OrderedDict[int, list[ExactCandidateGroup]] = OrderedDict()
        for index, group in enumerate(exact_groups):
            components.setdefault(find(index), []).append(group)
        blocks: list[list[ExactCandidateGroup]] = []
        for component in components.values():
            if len(component) < 2:
                continue
            for offset in range(0, len(component), block_size):
                blocks.extend(self._split_block_for_context(component[offset : offset + block_size]))
        return blocks

    def _split_block_for_context(
        self,
        groups: list[ExactCandidateGroup],
    ) -> list[list[ExactCandidateGroup]]:
        budget = max(
            600,
            self.settings.llm_context_chars - len(canonicalization_prompt.SYSTEM_PROMPT) - 600,
        )
        blocks: list[list[ExactCandidateGroup]] = []
        current: list[ExactCandidateGroup] = []
        for group in groups:
            proposed = [*current, group]
            if current and len(self._render_block(proposed)) > budget:
                if len(current) >= 2:
                    blocks.append(current)
                current = [group]
            else:
                current = proposed
        if len(current) >= 2:
            blocks.append(current)
        return blocks

    @classmethod
    def _same_semantic_block(cls, left: ExactCandidateGroup, right: ExactCandidateGroup) -> bool:
        left_tokens = cls._tokens(left.normalized_name)
        right_tokens = cls._tokens(right.normalized_name)
        shared = (left_tokens & right_tokens) - {"the", "of", "and", "a", "an"}
        if shared:
            return True
        left_acronym = cls._acronym(left.name)
        right_acronym = cls._acronym(right.name)
        if left_acronym and (left_acronym in right_tokens or left_acronym == right_acronym):
            return True
        if right_acronym and right_acronym in left_tokens:
            return True
        return SequenceMatcher(None, left.normalized_name, right.normalized_name).ratio() >= 0.62

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return set(_TOKEN_PATTERN.findall(value.casefold()))

    @staticmethod
    def _acronym(value: str) -> str:
        words = re.findall(r"[A-Za-z0-9]+", value)
        if len(words) < 2:
            return ""
        acronym = "".join(word[0] for word in words).casefold()
        return acronym if len(acronym) >= 2 else ""

    def _build_canonical_plans(
        self,
        exact_groups: list[ExactCandidateGroup],
        semantic_blocks: list[list[ExactCandidateGroup]],
        client: LLMClient | None,
    ) -> list[CanonicalPlan]:
        if semantic_blocks and client is None:
            raise KnowledgeCanonicalizationError(
                "KNOWLEDGE_CANONICALIZATION_FAILED",
                "Semantic canonicalization requires a configured AI provider.",
            )
        merged_representatives: set[int] = set()
        decided_representatives: set[int] = set()
        plans: list[CanonicalPlan] = []
        for block in semantic_blocks:
            allowed = {group.representative_id: group for group in block}
            data = self._canonicalize_block(client, block, decided_representatives)
            for decision in data.groups:
                candidate_ids = set(decision.candidate_ids)
                decided_representatives.update(candidate_ids)
                if not decision.same_concept:
                    continue
                groups = [allowed[candidate_id] for candidate_id in decision.candidate_ids]
                assert decision.canonical_name is not None
                assert decision.canonical_description is not None
                plans.append(
                    CanonicalPlan(
                        exact_groups=groups,
                        name=decision.canonical_name,
                        description=decision.canonical_description,
                        importance=max(
                            groups,
                            key=lambda item: _IMPORTANCE_RANK[item.importance],
                        ).importance,
                        difficulty=max(
                            groups,
                            key=lambda item: _DIFFICULTY_RANK[item.difficulty],
                        ).difficulty,
                        semantic_merge=True,
                    )
                )
                merged_representatives.update(candidate_ids)

        for group in exact_groups:
            if group.representative_id in merged_representatives:
                continue
            plans.append(
                CanonicalPlan(
                    exact_groups=[group],
                    name=group.name,
                    description=group.description,
                    importance=group.importance,
                    difficulty=group.difficulty,
                )
            )
        plans.sort(key=lambda plan: min(candidate.id for candidate in plan.candidates))
        return plans

    def _canonicalize_block(
        self,
        client: LLMClient,
        block: list[ExactCandidateGroup],
        already_decided: set[int],
    ) -> KnowledgeCanonicalizationOutput:
        allowed = {group.representative_id: group for group in block}
        messages = canonicalization_prompt.messages(self._render_block(block))
        last_error: KnowledgeCanonicalizationError | None = None
        for attempt in range(self.settings.llm_max_attempts):
            output = client.generate_structured(
                operation="knowledge_canonicalization",
                messages=messages,
                schema=KnowledgeCanonicalizationOutput,
            )
            data = output.data
            try:
                if not isinstance(data, KnowledgeCanonicalizationOutput):
                    raise KnowledgeCanonicalizationError(
                        "KNOWLEDGE_CANONICALIZATION_INVALID_OUTPUT",
                        "AI returned an invalid canonicalization structure.",
                    )
                seen: set[int] = set()
                for decision in data.groups:
                    candidate_ids = set(decision.candidate_ids)
                    if not candidate_ids.issubset(allowed):
                        raise KnowledgeCanonicalizationError(
                            "KNOWLEDGE_CANONICALIZATION_INVALID_OUTPUT",
                            "AI returned a candidate ID outside the supplied canonicalization block.",
                        )
                    if candidate_ids & (seen | already_decided):
                        raise KnowledgeCanonicalizationError(
                            "KNOWLEDGE_CANONICALIZATION_INVALID_OUTPUT",
                            "AI assigned a candidate to more than one canonicalization decision.",
                        )
                    seen.update(candidate_ids)
                    if decision.same_concept:
                        assert decision.canonical_name is not None
                        groups = [allowed[candidate_id] for candidate_id in decision.candidate_ids]
                        self._validate_canonical_name(decision.canonical_name, groups)
                return data
            except KnowledgeCanonicalizationError as error:
                last_error = error
                if attempt + 1 >= self.settings.llm_max_attempts:
                    break
                messages = canonicalization_prompt.messages(self._render_block(block))
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "The previous JSON violated candidate-ID or grounding constraints. "
                            "Return a complete corrected JSON object using only the supplied candidate_id values."
                        ),
                    }
                )
        if last_error is None:
            raise KnowledgeCanonicalizationError(
                "KNOWLEDGE_CANONICALIZATION_INVALID_OUTPUT",
                "AI did not return a valid canonicalization decision set.",
            )
        raise last_error

    @staticmethod
    def _render_block(block: list[ExactCandidateGroup]) -> str:
        payload: list[dict[str, object]] = []
        for group in block:
            evidence = []
            for candidate in group.candidates:
                for source in candidate.sources:
                    evidence.append(source.excerpt[:160])
                    if len(evidence) == 2:
                        break
                if len(evidence) == 2:
                    break
            payload.append(
                {
                    "candidate_id": group.representative_id,
                    "exact_candidate_ids": [candidate.id for candidate in group.candidates],
                    "name_variants": list(dict.fromkeys(candidate.name for candidate in group.candidates))[:3],
                    "description": group.description[:300],
                    "evidence_context": evidence,
                }
            )
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def _validate_canonical_name(
        cls,
        canonical_name: str,
        groups: list[ExactCandidateGroup],
    ) -> None:
        normalized = normalize_knowledge_name(canonical_name)
        if not normalized:
            raise KnowledgeCanonicalizationError(
                "KNOWLEDGE_CANONICALIZATION_INVALID_OUTPUT",
                "AI returned a blank canonical name.",
            )
        input_names = {group.normalized_name for group in groups}
        if normalized in input_names:
            return
        canonical_tokens = cls._tokens(normalized)
        input_tokens = set().union(*(cls._tokens(name) for name in input_names))
        overlap = canonical_tokens & input_tokens
        acronyms = {cls._acronym(group.name) for group in groups} - {""}
        if not canonical_tokens or (
            len(overlap) * 2 < len(canonical_tokens) and not canonical_tokens.intersection(acronyms)
        ):
            raise KnowledgeCanonicalizationError(
                "KNOWLEDGE_CANONICALIZATION_INVALID_OUTPUT",
                "AI returned a canonical name not grounded in the supplied candidates.",
            )

    @staticmethod
    def _validate_plan_completeness(
        candidates: list[KnowledgeCandidate],
        plans: list[CanonicalPlan],
    ) -> None:
        expected_ids = [candidate.id for candidate in candidates]
        actual_ids = [candidate.id for plan in plans for candidate in plan.candidates]
        if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected_ids):
            raise KnowledgeCanonicalizationError(
                "KNOWLEDGE_CANONICALIZATION_INVALID_OUTPUT",
                "Every current candidate must resolve exactly once.",
            )
        normalized_names = [normalize_knowledge_name(plan.name) for plan in plans]
        if len(normalized_names) != len(set(normalized_names)):
            raise KnowledgeCanonicalizationError(
                "KNOWLEDGE_CANONICALIZATION_INVALID_OUTPUT",
                "Canonicalization produced duplicate canonical node names.",
            )

    def _persist_plans(
        self,
        run: KnowledgeCanonicalizationRun,
        plans: list[CanonicalPlan],
    ) -> list[KnowledgeNode]:
        existing_by_name: dict[str, list[KnowledgeNode]] = {}
        for node in self.node_repository.list_all_by_course(run.course_id):
            existing_by_name.setdefault(node.normalized_name, []).append(node)

        nodes: list[KnowledgeNode] = []
        for plan in plans:
            normalized_name = normalize_knowledge_name(plan.name)
            matches = existing_by_name.get(normalized_name, [])
            if len(matches) > 1:
                raise KnowledgeCanonicalizationError(
                    "KNOWLEDGE_CANONICALIZATION_FAILED",
                    "Existing course nodes contain an ambiguous normalized-name collision.",
                )
            if matches:
                node = matches[0]
                node.name = plan.name
                node.description = plan.description
                node.importance = plan.importance
                node.difficulty = plan.difficulty
                node.is_active = True
                self.node_repository.update(node)
            else:
                node = self.node_repository.create(
                    KnowledgeNode(
                        course_id=run.course_id,
                        name=plan.name,
                        normalized_name=normalized_name,
                        description=plan.description,
                        importance=plan.importance,
                        difficulty=plan.difficulty,
                        is_active=True,
                        managed_by_canonicalization=True,
                    )
                )
                existing_by_name[normalized_name] = [node]

            if node.managed_by_canonicalization:
                self.source_repository.delete_for_node(node.id)
            existing_sources = {
                (source.material_id, source.source_reference)
                for source in self.source_repository.list_for_node(node.id)
            }
            source_excerpts: OrderedDict[tuple[int, str], str] = OrderedDict()
            for candidate in plan.candidates:
                for source in candidate.sources:
                    key = (source.material_id, source.source_reference)
                    previous = source_excerpts.get(key, "")
                    if len(source.excerpt) > len(previous):
                        source_excerpts[key] = source.excerpt
            for (material_id, source_reference), excerpt in source_excerpts.items():
                if (material_id, source_reference) in existing_sources:
                    continue
                self.source_repository.create(
                    KnowledgeSource(
                        knowledge_node_id=node.id,
                        material_id=material_id,
                        source_reference=source_reference,
                        excerpt=excerpt[:1000],
                    )
                )

            for candidate in plan.candidates:
                if plan.semantic_merge:
                    resolution_type = KnowledgeResolutionType.SEMANTIC_MERGE
                elif len(plan.candidates) > 1:
                    resolution_type = KnowledgeResolutionType.EXACT
                else:
                    resolution_type = KnowledgeResolutionType.NEW_NODE
                self.resolution_repository.create(
                    KnowledgeCandidateResolution(
                        canonicalization_run_id=run.id,
                        course_id=run.course_id,
                        candidate_id=candidate.id,
                        knowledge_node_id=node.id,
                        resolution_type=resolution_type,
                    )
                )
            nodes.append(node)
        return nodes

    def _nodes_for_run(self, run: KnowledgeCanonicalizationRun) -> list[KnowledgeNode]:
        resolutions = self.resolution_repository.list_for_run(run.id)
        node_ids = list(dict.fromkeys(resolution.knowledge_node_id for resolution in resolutions))
        nodes: list[KnowledgeNode] = []
        for node_id in node_ids:
            node = self.node_repository.get_by_id(node_id)
            if node is not None and node.course_id == run.course_id and node.is_active:
                nodes.append(node)
        return nodes

    def _mark_failed(self, run_id: int, code: str, message: str) -> None:
        with self.session.begin():
            run = self.run_repository.get_by_id(run_id)
            if run is None:
                return
            run.status = KnowledgeCanonicalizationStatus.FAILED
            run.canonical_node_count = 0
            run.merged_candidate_count = 0
            run.unresolved_count = run.candidate_count
            run.error_code = code[:64]
            run.error_message = message[:255]
            run.is_current = False
            run.completed_at = datetime.now(timezone.utc)
            self.run_repository.save(run)

    @staticmethod
    def _map_ai_error(error: AIServiceError) -> KnowledgeCanonicalizationError:
        if error.code == "AI_INVALID_OUTPUT":
            return KnowledgeCanonicalizationError(
                "KNOWLEDGE_CANONICALIZATION_INVALID_OUTPUT",
                "AI returned output that did not match the required canonicalization schema.",
            )
        return KnowledgeCanonicalizationError(
            "KNOWLEDGE_CANONICALIZATION_FAILED",
            "The AI provider could not complete knowledge canonicalization.",
        )

    @staticmethod
    def _client_identity(client: LLMClient) -> tuple[str, str]:
        provider = str(getattr(client, "provider", "")).strip()
        model = str(getattr(client, "model", "")).strip()
        if not provider or not model:
            raise KnowledgeCanonicalizationError(
                "KNOWLEDGE_CANONICALIZATION_FAILED",
                "The configured AI provider did not expose traceable provider and model identifiers.",
            )
        return provider[:80], model[:160]

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

    def _require_course(self, course_id: int, owner_id: int) -> None:
        if self.course_repository.get_for_owner(course_id, owner_id) is None:
            raise ResourceNotFoundError("Course")


def get_knowledge_canonicalization_service(
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> KnowledgeCanonicalizationService:
    return KnowledgeCanonicalizationService(
        session=session,
        course_repository=CourseRepository(session),
        extraction_run_repository=KnowledgeExtractionRunRepository(session),
        candidate_repository=KnowledgeCandidateRepository(session),
        content_repository=MaterialContentRepository(session),
        run_repository=KnowledgeCanonicalizationRunRepository(session),
        resolution_repository=KnowledgeCandidateResolutionRepository(session),
        node_repository=KnowledgeNodeRepository(session),
        source_repository=KnowledgeSourceRepository(session),
        user_repository=UserRepository(session),
        settings=settings,
    )


__all__ = [
    "KnowledgeCanonicalizationError",
    "KnowledgeCanonicalizationResult",
    "KnowledgeCanonicalizationService",
    "get_knowledge_canonicalization_service",
]
