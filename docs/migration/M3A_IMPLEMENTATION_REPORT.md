# LearnPilot V1 — M3-A Implementation Report

## Actual changes

- Added course-only knowledge domain enums and deterministic name normalization.
- Added KnowledgeNode, KnowledgeEdge, and KnowledgeSource SQLAlchemy models.
- Added database constraints for enum values, self edges, exact duplicate edges, same-course edge endpoints, duplicate sources, foreign keys, and cascades.
- Added three dedicated repositories and KnowledgeModelService.
- Added Pydantic write inputs and read response contracts.
- Added course knowledge-model and node-detail read APIs.
- Added 15 real SQLite M3-A tests.
- Added this report and the M3-A architecture document.

No M2 prompt, parser, AI service, frontend file, or provider behavior was changed.

## Migration

Migration 0003_m3a_knowledge_model is based on 0002_m2_course_material_ai and creates:

- knowledge_nodes;
- knowledge_edges;
- knowledge_sources;
- their indexes, enum constraints, check/unique constraints, and cascading foreign keys.

Verified results:

- fresh SQLite upgrade to head: PASS;
- populated 0002 database upgrade to head with existing Course data retained: PASS;
- Alembic head schema inspection: PASS.

No earlier migration was edited.

## Models

KnowledgeNode stores course knowledge only: name, normalized name, description, importance, difficulty, and timestamps. It contains no learner or UI state.

KnowledgeEdge supports contains and prerequisite semantics. M3-A only defines and validates the schema; it does not infer or generate relationships.

KnowledgeSource links a node to a same-course Material and a real M2 segment reference. Excerpts are optional and limited to 1000 characters.

## Repositories

Implemented:

- KnowledgeNodeRepository;
- KnowledgeEdgeRepository;
- KnowledgeSourceRepository.

They implement the M3-A persistence operations only. No LLM, HTTP, traversal engine, or speculative infrastructure was added.

## Services

KnowledgeModelService implements owner-scoped reads and typed write methods for future pipelines/tests. It validates node/edge/source integrity and translates expected conflicts into stable domain error codes.

Source creation requires an exact MaterialContent segment reference. Edge course isolation is additionally enforced by composite foreign keys.

## API

Implemented:

- GET /api/courses/{course_id}/knowledge-model
- GET /api/courses/{course_id}/knowledge-nodes/{node_id}

The first returns nodes and edges. The second returns a node with its sources and related edges. Neither response contains mastery, progress, confidence, recommendations, or presentation coordinates.

No management UI or temporary write endpoint was added.

## Tests

New M3-A tests: 15/15 PASS.

Coverage includes node CRUD/list/normalization; Repository methods; ownership; edge self/duplicate/cross-course rejection; source traceability/duplicate/cross-course rejection; real database constraints; material/node/course cascades; read APIs; and 404 behavior.

Full backend regression: 93/93 PASS.

## Regression

- pytest: 93/93 PASS.
- ruff check backend: PASS.
- ruff format --check backend: PASS.
- frontend source changes: none.
- frontend typecheck: PASS.
- frontend lint: PASS.
- frontend Vitest/Vite execution: not used as a completion gate because frontend is not affected; the available Node runtime is Windows while the existing node_modules native packages are Linux/WSL, so those commands cannot start in this host configuration.
- frontend milestone result: NOT AFFECTED.

The pre-change backend baseline was 78/78 PASS. No existing test was removed.

## Known limitations

Knowledge Model currently contains infrastructure only.

- No AI extraction.
- No semantic deduplication.
- No hierarchy generation.
- No prerequisite inference.
- No frontend graph visualization.
- No graph traversal engine.
- No student mastery or learning evidence.

These are intentional later M3/M4/M5 responsibilities, not M3-A defects.

## M3-B entry conditions

M3-B may begin only after formal M3-A acceptance. It must:

1. consume existing M2 MaterialContent and segment provenance;
2. preserve exact source traceability;
3. write through KnowledgeModelService;
4. keep Course Model separate from Student Model;
5. introduce no semantic deduplication, hierarchy inference, prerequisite inference, or graph frontend unless separately approved for the correct later stage.
