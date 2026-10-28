# LearnPilot V1 — M7 Integration Design

> **FROZEN FOR M7-1** · M7-0 design only; no runtime code or migration.
> Baseline: `main` / `6e7bda340f3d4205e24e86a1bf91c57f0c8c70be`, 2026-10-25.

## 1. Project status

The review used the checked-in ORM models, Pydantic schemas, repositories, services, routers, migrations, tests, Vue
routes, Axios client, Pinia stores, composables and views. The pre-existing `scripts/start_dev.sh` modification is
untouched. `git diff --check` passed. Focused M2–M6 backend verification passed 120/120. Selected frontend Vitest did
not start because WSL resolves `npm` to Windows and `cmd.exe` rejects the UNC directory; this is NOT RUN, not a pass.

## 2. M2–M6 reuse inventory

| Existing capability | M7 use | Evidence |
| --- | --- | --- |
| Course/material ownership | validate every aggregate | `backend/app/services/course_service.py:283-312` |
| MaterialContent text, segments, hash, parser/page data | cited content | `backend/app/db/models/material_content.py`; `documents/parser.py` |
| chunking + lexical ranking | lightweight retrieval | `backend/app/ai/chunking.py` |
| grounded QA/reference allow-list | citation-validation pattern | `services/material_ai_service.py`; `ai/references.py` |
| OpenAI-compatible provider/mock, schema, timeout/retry | Tutor adapter | `backend/app/ai/client.py`; `core/settings.py` |
| node detail + verified source previews | node-to-material retrieval | `knowledge_model_service.py:145-217`; `api/knowledge.py:223-259` |
| current prerequisite DAG | preserve M6 prerequisite rules | `recommendation_context_service.py:49-102,156-226` |
| validated Question bank + primary node links | practice candidates | `repositories/question_repository.py:49-77` |
| immutable AssessmentQuestion snapshot | historical question facts | `diagnostic_domain_service.py:347-377` |
| Response + deterministic objective scorer | answer record and score | `db/models/response.py`; `deterministic_objective_scorer.py` |
| LearningEvidence identity/validation | practice evidence after source extension | `db/models/learning_evidence.py`; `learning_evidence_service.py` |
| Mastery/Confidence + fingerprint | refresh affected nodes | `mastery_service.py:45-120`; `mastery_read_service.py:34-62` |
| pure RecommendationEngine | recommendation calculation | `recommendation_engine.py:51-83` |
| persisted LearningPlan generation/reuse | Session source and post-completion refresh | `learning_plan_service.py:73-183` |
| `/learn`, shared plan composable/client/tokens | frontend integration | `frontend/src/views/LearnView.vue`; `composables/useLearningPlan.ts` |

### 2.1 Actual findings

- **M2:** PDF references are exact page labels; DOCX uses paragraph/table labels. Material QA validates references but
  accepts one material only. `GET /api/materials/search` searches metadata/preview/summary, not full segments. Current
  ranking is lexical token overlap, not semantic search. Provider mode never silently falls back to mock.
- **M3:** `KnowledgeSource` uniquely links node/material/reference. Verified previews only trust an exact match in
  saved M2 segments. `PREREQUISITE` is source prerequisite → target dependent and forms a DAG. Node detail is directly
  reusable. There is no single public knowledge-model version; current runs/snapshot hashes exist internally.
- **M4:** Question already has type, difficulty, answer, explanation, source refs, validation and content version.
  Response is unique per AssessmentQuestion, but a source Question can be snapshotted in separate assessments, so
  repeated attempts across Sessions need no second response model. Assessment type is currently diagnostic-only and
  the diagnostic assembler requires 8–20 questions.
- **M5:** Evidence is diagnostic-only and its assessment/snapshot/response FKs are required. Its database identity is
  `(source_type, source_question_snapshot_id, historical_knowledge_node_ref, evidence_schema_version)`. Mastery refresh
  is fingerprint-idempotent, but diagnostic submit does not automatically refresh Mastery. Tutor has no evidence type.
- **M6:** Plan responses expose course/target/plan/task IDs. `RecommendationEngine` is pure; plan generation can
  supersede/create a row. Existing LearningTask is a static recommendation description with no progress and a plan
  may have 1–3 tasks, so it cannot represent the fixed three Session phases.

## 3. Minimal new entities

Exactly three are proposed.

### `LearningSession`

Fields: `id`, `user_id`, `course_id`, `target_knowledge_node_id`, nullable `source_learning_plan_id`, nullable unique
`practice_assessment_id`, `status`, fixed `session_contract_version=learning_session_v1`, `started_at`, `completed_at`,
`cancelled_at`, bounded immutable `completion_summary`, `recommendation_refresh_status`
(`not_requested|pending|succeeded|failed`), and timestamps. Use a composite course/node FK with direct node deletion
restricted. One active Session per user/course/target is enforced using the M6 nullable-active-slot pattern if needed
for SQLite/MySQL portability.

### `LearningSessionTaskState`

Three rows are created atomically: `concept_learning` (0), `guided_example` (1), `adaptive_practice` (2). Fields are
`id`, `session_id`, `phase`, `order_index`, optional `source_learning_task_id`, status
`not_started|in_progress|completed`, timestamps and small phase progress JSON. Unique `(session_id, phase)` and
`(session_id, order_index)`. This stores execution state, not copied M6 scoring/content or a workflow engine.

### `TutorMessage`

Fields: `id`, `session_id`, `task_state_id`, `role`, optional `teaching_strategy`, bounded content, citation JSON,
`grounded`, provider/model/prompt version and `created_at`. Persistence is required for resume. It has no score,
Evidence weight or Mastery relationship.

**Not added:** PracticeAttempt, Question, scoring, evidence, mastery, recommendation, workflow, vector/cache/event
entities. Practice reuses one M4 practice Assessment per Session, fresh AssessmentQuestion snapshots and Responses.

## 4. Session state machine

```text
CREATED --first learning write--> IN_PROGRESS --complete--> COMPLETED
   |                                  |
   +--------------- cancel -----------+----> CANCELLED
```

| State | Allowed | Rules |
| --- | --- | --- |
| CREATED | read/start/content/Tutor/practice/cancel | first write atomically sets started_at + IN_PROGRESS |
| IN_PROGRESS | read/resume/task/Tutor/practice/complete/cancel | page close leaves it resumable |
| COMPLETED | read detail/messages/results/stored summary | all writes rejected except idempotent complete replay/refresh recovery |
| CANCELLED | history read only | cannot resume/answer/complete |

Every request checks user, course, Session and target ancestry; mismatch is hidden as `SESSION_NOT_FOUND`. Completion
requires three completed phases and at least one deterministically scored Response. Completion locks/CASes the row;
repeat returns the stored summary and never rewrites Evidence, Mastery or scores. A pre-commit failure rolls back all
core writes; a client timeout after commit is safe to retry. Completed Sessions remain read-only viewable.

## 5. Proposed API contract

The original nine interfaces were **PROPOSED** at M7-0 freeze time.

| Method/path | Request → response | Existing service reuse | State/idempotency | Stage |
| --- | --- | --- | --- | --- |
| `POST /api/learning/sessions` | `{course_id,target_knowledge_node_id?,learning_plan_id?}` → detail | Course/Knowledge/Plan reads | create + 3 tasks; active identity returns `reused=true` | M7-1 |
| `GET /api/learning/sessions/active?course_id=` | query → detail/null | Session repo | read-only | M7-1 |
| `GET /api/learning/sessions/{id}` | path → aggregate detail | Session + M4 reads | read-only, including completed | M7-1 |
| `PATCH /api/learning/sessions/{id}/tasks/{phase}` | monotonic status → task/detail | Session service | same state replay safe; regression 409 | M7-1 |
| `GET /api/learning/sessions/{id}/content?phase=&q=` | phase/query → cited items | M3 verified previews + M2 chunking | deterministic read | M7-2 |
| `POST /api/learning/sessions/{id}/tutor/messages` | task/message/strategy → persisted pair | M2 LLM + M7 retrieval + M5 read | `Idempotency-Key` returns same pair | M7-3 |
| `POST /api/learning/sessions/{id}/practice/next` | preferred difficulty → redacted snapshot | M4 Question/snapshot | retry returns current unanswered item | M7-4 |
| `PUT /api/learning/sessions/{id}/practice/responses/{assessment_question_id}` | selected options → locked score/explanation/next difficulty | M4 validation/Response/scorer | identical replay safe; changed locked answer 409 | M7-4 |
| `POST /api/learning/sessions/{id}/complete` | empty → immutable summary + refresh state | M4 finalize, M5 Evidence/Mastery, post-commit M6 plan | repeat returns stored summary | M7-5 |

### M7-1 contract amendment (2026-10-25)

M7-1 acceptance requires explicit cancellation, while the frozen state machine included `CANCELLED` but the original
nine-interface table omitted its transport. The minimum amendment is now implemented as
`POST /api/learning/sessions/{id}/cancel`: empty request, owned aggregate detail response, `CREATED|IN_PROGRESS →
CANCELLED`, repeated cancellation returns the same terminal state, completed cancellation is 409. This is the tenth M7
API; it does not complete a Session, write Evidence/Mastery, or recalculate recommendations.

Detail includes IDs, status/timestamps/version, three tasks, practice counts, recent messages and nullable summary. It
never exposes an unanswered correct answer. Content items contain `material_id`, title, exact reference, bounded text
and content hash. Summary contains task/practice totals, accuracy, affected nodes, Mastery before/after, evidence
created/skipped and recommendation refresh state; Tutor messages are excluded.

Errors use the existing envelope. 404: session/course/node/question not found. 409: invalid Session state, inactive
target, task order violation, practice not ready/locked, incomplete Session, state conflict, exhausted bank. 422:
invalid phase/answer/AI output. Existing 429/503 AI mappings remain.

## 6. M7-2 retrieval decision

| Criterion | A: sources + lexical | B: semantic layer |
| --- | --- | --- |
| Existing data | exact links/segments exist | embedding/index absent |
| Citation | exact and verifiable | needs mapping/freshness design |
| Complexity/cost | small, no dependency/call | SDK, calls, index lifecycle |
| Demo fit | sufficient when nodes are sourced | unproven incremental value |

**Freeze Strategy A.** Resolve only same-course sources for the target node, exact-match their MaterialContent segment,
chunk long segments, rank with target name/description and optional query, use stable material/segment tie-breaks and
bound total chars by existing LLM settings. If direct sources are empty, return `grounded=false`; enable a bounded
same-course lexical fallback only after M7-2 fixtures prove precision. Strategy B is reconsidered only if those fixtures
fail. No embedding SDK, Chroma or FAISS in M7-0.

## 7. Tutor context contract

| Context | Required | Source |
| --- | --- | --- |
| Course, KnowledgeNode, Session, current task | yes | M1/M3/M7 |
| Relevant material | optional structurally; required for grounded factual answer | M7-2 exact items |
| Current Mastery | optional; missing/stale explicit | M5 read |
| Current practice question | optional and redacted until answered | M4 snapshot |
| Recent messages | optional | M7 TutorMessage |

System teaching rules, untrusted quoted source blocks and user text remain separate. Document instructions are data,
not commands; Tutor has no write tools and cannot call Evidence/Mastery/recommendation. Context IDs must share Session
ancestry. Budget `llm_context_chars`: policy ≤20%, sources ≤55%, recent messages ≤20%, user/reserve ≥5%. Returned
citations must be in the sent allow-list. Before answer submission, exclude correct answer/explanation and allow only
Hint, Guided Question or parallel Example; Step-by-Step/Full Explanation for that item is allowed only after locking
the Response. Strategies are `hint|guided_question|example|step_by_step_explanation|full_explanation`.

## 8. Adaptive Practice

- Pool: same course, active primary target node, validated questions; difficulty is existing easy/medium/hard.
- Initial: missing/stale Mastery → medium (easy fallback); needs attention/low → easy; reinforcement/middle → medium;
  good performance → hard. This maps M5 state and does not change its formula.
- Two consecutive correct raises one level; two incorrect lowers one; otherwise hold. Server derives streak from
  persisted Responses.
- Exclude source Question IDs already snapshotted in this Session. Order by requested bucket, least prior exposure,
  then Question ID. Exposure comes from owned AssessmentQuestion history, not a new table.
- Fallback: medium→easy→hard, easy→medium→hard, hard→medium→easy. When exhausted, return explicit counts and allow
  completion only if at least one scored response and other requirements hold.
- Add `AssessmentType.PRACTICE`; do not use/alter the diagnostic 8–20 assembler. Reuse snapshot building, answer
  validation, Response and exact-match scorer. Multiple Sessions create distinct snapshots/Responses.
- V1 writes Evidence only at Session completion, never per answer; abandoned Sessions do not affect Mastery.

## 9. Evidence → Mastery → Recommendation

Practice Evidence uses the same snapshot node links, persisted points/max, difficulty, equal node attribution, scoring
version and occurrence time. Extend only `EvidenceSourceType.PRACTICE` and the existing source validator; retain its FK
shape and unique identity. Tutor never produces Evidence. Read Mastery before, refresh affected current nodes with the
existing calculator/fingerprint, then call M6 only after that commit.

## 10. Transaction and idempotency

One DB transaction must: lock/validate Session; validate all tasks and practice ownership; finalize practice
Assessment/scores; insert missing Evidence; refresh affected Mastery; store immutable summary; mark completed and
refresh pending. Current M4/M5 public methods open their own transactions, so M7-5 must expose transaction-aware core
entry points beneath unchanged public wrappers—no nested independent commits.

After commit, call `LearningPlanService.generate`. Success marks refresh succeeded. Failure marks failed, logs the typed
error and leaves the valid completed Session/Evidence/Mastery intact; retry uses M6 fingerprint reuse. Defense in depth:
Session CAS/lock, Evidence unique key, Mastery fingerprint, stored summary replay and M6 active-slot/fingerprint.
Frontend button disabling is not correctness.

## 11. Frontend integration

Keep `/learn` and existing top-level navigation. Add nested `/learn/sessions/:sessionId` with nav label 学习, a typed
`learningSessions.ts` client and focused `useLearningSession`; do not overload the global course store. The server is
authoritative on reload/conflict. Append a workspace below the current recommendation: goal, three-phase progress,
active concept/example/practice, Tutor and summary. Reuse existing blue/white tokens, typography, components and
responsive patterns; no Dashboard/Diagnose/Knowledge/Progress redesign, copied Course page, new palette or M8 chart.

## 12. Security/failures

Owner/course/session scope every query; never send cross-course material. Do not expose answers before lock. Bound all
inputs/context. Log IDs, operation/provider/model/latency/error code, never keys/full documents/answers/private
messages. AI timeout/rate limit changes no Session/task state. Empty sources, question exhaustion, stale Mastery and
failed recommendation refresh are explicit states, never fabricated content or scores.

## 13. Phase ownership

| Stage | Exclusive output | Depends on |
| --- | --- | --- |
| M7-1 | Session/task models, state/API, workspace/recovery | M6 plan reads |
| M7-2 | exact node/course retrieval, citations, content API | M7-1 + M2/M3 |
| M7-3 | Tutor context/prompt/messages/policy/citations | M7-1/2 + M2 |
| M7-4 | practice Assessment, selector, next/answer, scoring | M7-1 + M4 |
| M7-5 | practice Evidence, atomic completion, Mastery, post-commit plan, summary | M7-1/4 + M5/M6 |
| M7-6 | browser E2E, configured DeepSeek, failures/full regression/manual acceptance | M7-1–5 |

## 14. Confirmed constraints / unverified non-blockers

Confirmed: bootstrap-user identity; no public M3 model version; single-material lexical M2 QA; objective-only M4 and
diagnostic-only Assessment today; diagnostic-only M5 Evidence; no automatic production Mastery refresh; M6 GET is
read-only while generate may write; M6 tasks have no execution state; frontend has no Session UI.

Non-blocking verification remains: Strategy A precision fixtures (M7-2); SQLite/MySQL active-slot DDL (M7-1);
transaction-aware internal method shape while preserving algorithms (M7-5); frontend suite in a Linux Node-capable
environment (M7-6); real DeepSeek check (M7-6). None changes the M7-1 aggregate/API identity.

## M7-2 implementation note (2026-10-25)

The frozen Strategy A is now implemented by `backend/app/services/learning_content_service.py` and exposed as
`GET /api/learning/sessions/{session_id}/content`. Retrieval first resolves exact `KnowledgeSource` records against
the persisted `MaterialContent.segments` reference. Missing, cross-course, parse-failed and stale references are
excluded. A same-course lexical supplement using the existing M2 `chunk_segments` and `relevant_chunks` helpers is
enabled because the M7-2 fixture suite proves the intended Cache/LRU selection and cross-course isolation.

The deterministic envelope is capped at six segments, two segments per material, the configured
`llm_chunk_chars` per segment, and the smaller of 55% of `llm_context_chars` or 8,000 total characters. A real
segment index replaces the earlier conceptual `segment_id`, because M2 persists segments as ordered JSON rather
than separate rows. Every returned item carries material identity, type, exact source reference, persisted content
hash, direct/supplemental provenance and truncation state. `grounded=true` means at least one exact M3 direct source
was returned; supplemental results remain traceable but do not claim a direct KnowledgeNode source relation.

No schema migration, embedding service, vector store, LLM call, Session mutation, Evidence write, Mastery refresh or
Recommendation recomputation was added. Cancelled/completed sessions remain history-readable under the M7-1 state
contract; retrieval is read-only and still enforces configured-user, Course and KnowledgeNode ancestry.

## M7-3 implementation note (2026-10-25)

The frozen Tutor contract is implemented by `backend/app/services/tutor_service.py` and the two Session-scoped
message endpoints. Server-side context resolves the owned Session, Course, active KnowledgeNode, current task,
read-only M5 mastery state, M7-2 retrieval envelope and eight recent messages. The prompt preserves the frozen
budget split, separates system policy from untrusted material blocks and user text, and exposes the five strategies
including the frozen internal value `step_by_step_explanation`.

`TutorMessage` is the only M7-3 entity. It stores a bounded user/assistant pair, current task reference, strategy,
validated citations, grounding/evidence status, provider/model/prompt version and an idempotency identity. Migration
`0016_m7_3_tutor_messages` adds this table without changing any M4, M5 or M6 table. Sequential retries with the same
`Idempotency-Key` replay the stored pair without another provider call.

Tutor output is validated by Pydantic and every citation must exactly match the material/reference allow-list sent
from M7-2; unknown or cross-course citations reject the response before persistence. Missing citations are surfaced
as insufficient evidence. Tutor writes can only move a CREATED Session to IN_PROGRESS, as already defined by the
state machine; they never create Evidence, refresh Mastery, score a Response or recalculate recommendations.

The Session view now uses a restrained reading-plus-Tutor layout. History is persisted and restored, errors preserve
the draft and retry with the same idempotency key, and request versions prevent previous-Session history from
overwriting the current panel. Real configured DeepSeek smoke tests passed hint, full explanation, insufficient
evidence and cross-course isolation scenarios.
