# LearnPilot V1 — M7-2 Implementation Report

## 1. Goal and frozen contract

M7-2 adds read-only, course-scoped learning content to the M7-1 Session workspace. It implements the frozen
`GET /api/learning/sessions/{session_id}/content?phase=&q=` contract. No Tutor, generated instruction, adaptive
practice, assessment, LearningEvidence, Mastery update or recommendation refresh is part of this stage.

## 2. Reused capabilities

- M2 `Material`, `MaterialContent` segments/hash/parser state and real source references.
- M2 `chunk_segments` and `relevant_chunks` (`backend/app/ai/chunking.py`).
- M2/M3 rule that a source is quotable only when its reference exactly matches a saved segment
  (`backend/app/services/knowledge_model_service.py`).
- M3 `KnowledgeNode.course_id` and unique `KnowledgeSource` node/material/reference identity.
- M7-1 configured-user ownership, Session course/target and persistent Session state.
- Existing typed Axios client, Vue Router, Element Plus feedback components and Session workspace.

## 3. Retrieval algorithm

1. Resolve the configured user and owned Session; a foreign Session is reported as not found.
2. Revalidate Course ownership and Session Course/KnowledgeNode ancestry.
3. Load exact M3 sources joined to successfully parsed M2 materials/content in one query.
4. Accept only non-empty saved segments whose reference exactly equals the KnowledgeSource reference.
5. Split long source segments with the existing M2 chunk configuration.
6. When direct content leaves capacity, rank valid same-Course segments using the KnowledgeNode name/description and
   optional query. Zero-match segments are not returned.
7. Deduplicate by material/reference/text, cap each material at two fragments and apply deterministic total limits.

Direct sources precede supplements. The fixture proves Cache Mapping selects the direct PDF, LRU selects the second
same-Course material, and a same-name different-Course material never leaks.

## 4. API and response schema

`GET /api/learning/sessions/{session_id}/content`

- Query: `phase` defaults to `concept_learning`; `q` is optional and capped at 500 characters.
- Response: Session/Course/KnowledgeNode identity, description, phase, `ready|empty`, `grounded`, bounded segments
  and explicit limits.
- Segment: material ID/title/type, persisted segment/fragment indexes, text, exact source reference,
  `direct|supplemental`, content hash and truncation flag.
- Errors: `SESSION_NOT_FOUND` (404); `CONTENT_PHASE_NOT_AVAILABLE` and `SESSION_SCOPE_INVALID` (409); standard
  validation envelope (422).
- Adaptive practice is rejected because it belongs to M7-4. The endpoint is strictly read-only.

M2 stores segments as ordered JSON, not rows, so the conceptual `segment_id` is represented by stable
`segment_index` plus `fragment_index`. This is the only representation-level difference from the M7-0 example.

## 5. Provenance and limits

- Only existing `SUCCESS` and legacy-compatible `EXTRACTED` material states are eligible.
- PDF/TXT/MD/DOCX labels are copied from exact saved references; no page or paragraph is inferred.
- An unknown PDF page in a stale KnowledgeSource is excluded because it cannot match the saved segment allow-list.
- Deleted and parse-failed materials are not returned.
- Limits: 6 fragments, 2 per material, `llm_chunk_chars` per fragment, and
  `min(55% * llm_context_chars, 8,000)` total characters.
- `grounded=true` means at least one exact direct M3 source survived validation. Lexical supplements are traceable
  but explicitly labelled `supplemental`.

## 6. Frontend changes

The existing Session view now renders “课程原始资料” without adding navigation. It shows the KnowledgeNode
description, source title/type/reference, provenance label and a link to the existing Material detail route. Loading,
ready, empty, error and retry are explicit. Long excerpts use native disclosure UI. Copy states that the text is
course material rather than AI instruction.

`useLearningContent` clears prior content on each load and uses a monotonically increasing request version, so a
slow response from a previous Session cannot overwrite the current Session. The server remains the sole source of
content and Session truth.

## 7. Database changes

None. No table, column, index or Alembic revision was added.

## 8. Tests and verification

Focused backend: **8 passed**. Coverage includes exact provenance, multi-material fallback, isolation, deduplication,
stable ordering, parse failure, empty, deletion, invalid PDF reference, ownership, phase rejection, limits,
read-only side effects and live HTTP envelopes.

Focused frontend: **11 passed** across the Session view and content state. Coverage includes loading, PDF/TXT
sources, empty/error/retry, Material navigation, long-content disclosure and stale-response protection.

Final full-suite results:

- Backend pytest: **377 passed** in 294.51 seconds.
- Ruff check: **PASS**; Ruff format check: **PASS** (186 files already formatted).
- Frontend Vitest: **156 passed** in 25 files; TypeScript: **PASS**; ESLint: **PASS**; production build:
  **PASS**. The existing Vite large-chunk advisory and existing Vue test warnings are non-failing and unrelated to
  M7-2.
- Alembic: **PASS**; an empty SQLite database upgraded through `0015_m7_1_sessions (head)`. M7-2 required no
  revision.
- Git diff check: **PASS**. Branch remains `main` at original HEAD `6e7bda3`; no commit, push, switch, `.env`, lock
  file or dependency-manifest change occurred. All pre-existing M7-0/M7-1 work remains present.
- Secret scan: **PASS** for M7-2 code, tests and documents; no credential/private-key/token pattern was found.
- Browser verification: **NOT RUN**. It is intentionally not reported as passed without a real browser run.

## 9. Manual browser acceptance

1. Start the existing backend/frontend against a database with parsed Course material and M3 sources.
2. Open Learn, choose the Course recommendation, then start or resume its Session.
3. Confirm Course, KnowledgeNode and Session state match the recommendation.
4. Confirm “课程原始资料” shows real text and an exact material/page or segment reference.
5. Open “查看原始资料” and compare the excerpt/reference with the persisted material.
6. Refresh; confirm the same bounded content reloads without changing task progress.
7. Open another Course Session; confirm no previous-Course excerpt remains.
8. Exercise empty and failed requests; confirm honest empty/error/retry states with no generated filler.
9. Confirm content reads do not change LearningEvidence, Mastery or LearningPlan records.

## 10. Limits and technical debt

Lexical fallback remains intentionally lightweight: absent synonyms may be missed and no pseudo-precise numeric
score is exposed. This is acceptable for V1 because exact sources lead, scope is strict, output is bounded and empty
is honest. Reconsider semantic retrieval only with repeatable failure evidence; no vector dependency is justified.

Historical Sessions depend on their target/material records remaining present under existing FK/delete rules.
Inactive nodes remain history-readable, consistent with M7-1, while their Session cannot progress.

## 11. M7-3 readiness

Ready after final quality gates pass. M7-3 can consume this bounded response as untrusted quoted material, retain
material/hash/reference identities and refuse citations outside the envelope. It must preserve Course isolation and
must not let Tutor calls update Mastery.
