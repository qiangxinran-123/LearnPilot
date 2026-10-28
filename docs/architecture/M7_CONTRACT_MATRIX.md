# LearnPilot V1 — M7 Contract Matrix

`EXISTING` predates M7; `IMPLEMENTED` is now present in M7-1/M7-2; `PROPOSED` remains frozen but unimplemented. Every row cites code proving reuse or the gap.

| M7 function | Existing module | Actual entry | Request/data | Reuse | Extension | Stage |
| --- | --- | --- | --- | --- | --- | --- |
| Course ownership | Course | `CourseService._require_course` (`course_service.py:302-306`) | owner + course ID | yes | no | M7-1 |
| Plan target | M6 | EXISTING `GET /api/courses/{id}/learning-plan` (`api/learning_plans.py:26-34`) | plan/course/target/task IDs | yes | adapter | M7-1 |
| Create Session | M7-1 | IMPLEMENTED `POST /api/learning/sessions` (`api/learning_sessions.py`) | course + plan/target | no | Session + 3 task states | M7-1 |
| Active Session | M7-1 | IMPLEMENTED `GET /api/learning/sessions/active` (`api/learning_sessions.py`) | course query | no | scoped lookup | M7-1 |
| Session detail | M7-1 | IMPLEMENTED `GET /api/learning/sessions/{id}` (`api/learning_sessions.py`) | aggregate | no | recovery model | M7-1 |
| Task progress | M7-1 + M6 task reference | IMPLEMENTED `PATCH /api/learning/sessions/{id}/tasks/{phase}` (`api/learning_sessions.py`) | phase + monotonic status | partial | SessionTaskState | M7-1 |
| Cancel Session | Session state machine | IMPLEMENTED `POST /api/learning/sessions/{id}/cancel` (`api/learning_sessions.py`) | empty → owned detail | no | idempotent terminal transition | M7-1 |
| State CAS | M4 pattern | `diagnostic_domain_service.py:162-171,277-284` | expected→target | pattern | Session enum/CAS | M7-1 |
| Node detail | M3 | EXISTING `GET .../knowledge-nodes/{node_id}` (`api/knowledge.py:223-259`) | node/sources/edges | yes | no | M7-1/2 |
| Node sources | M3 KnowledgeSource | unique node/material/reference (`db/models/knowledge_source.py`) | exact source identity | yes | no | M7-2 |
| Verified text | M3+M2 | `get_verified_source_previews` (`knowledge_model_service.py:160-217`) | exact saved segment | yes | longer bounded item | M7-2 |
| Chunk/rank | M2 | `chunk_segments`, `relevant_chunks` (`ai/chunking.py`) | query + chunks | yes | scoped adapter | M7-2 |
| Learning content | M2 + M3 + M7-1 | IMPLEMENTED `GET /api/learning/sessions/{id}/content?phase=&q=` (`api/learning_sessions.py`; `learning_content_service.py`) | owned Session → course/node → cited segments | yes | deterministic source-first adapter | M7-2 |
| Citation validation | M2 | exact saved segment match in `knowledge_model_service.py`; reused by `learning_content_service.py` | persisted material/reference/hash | yes | bounded retrieval identity | M7-2/3 |
| LLM provider | M2 | `OpenAICompatibleLLMClient.generate_structured` | messages + schema | yes | Tutor schema/prompt | M7-3 |
| Tutor context/API | M2 + M5 + M7-1/2 | IMPLEMENTED `GET/POST /api/learning/sessions/{id}/tutor/messages` (`tutor_service.py`; `api/learning_sessions.py`) | server context + message + strategy + `Idempotency-Key` | yes | bounded assembler + TutorMessage | M7-3 |
| Tutor evidence | M5 | `EvidenceSourceType` only diagnostic (`models/evidence.py`) | none | no by design | never add Tutor scoring | M7-3/5 |
| Questions by node | M4 | `QuestionRepository.list_for_primary_node` (`question_repository.py:49-62`) | course/node | yes | status/difficulty/exclusion filters | M7-4 |
| Difficulty/status | M4 Question | `db/models/question.py`; `list_validated_for_course` | easy/medium/hard + validation | yes | combined selector | M7-4 |
| Snapshot | M4 AssessmentQuestion | `db/models/assessment_question.py`; builder at `diagnostic_domain_service.py:347-377` | immutable source facts | yes | practice type | M7-4 |
| Response/multiple use | M4 | unique per snapshot (`db/models/response.py`), source Question reusable | answer/score/times | yes | one practice Assessment/Session | M7-4 |
| Scoring | M4 | `DeterministicObjectiveScorer.score` | snapshot + selected options | yes | none | M7-4 |
| Next question | none | PROPOSED `/practice/next` | preferred difficulty | partial | selector/snapshot write | M7-4 |
| Answer | diagnostic PUT exists | `api/diagnostics.py:212-226` | selected options | pattern | PROPOSED practice PUT + locked score | M7-4 |
| Practice Evidence | M5 | strict diagnostic validator (`learning_evidence_service.py`) | assessment/snapshot/response/node/score | partial | add practice source | M7-5 |
| Evidence dedup | M5 | `uq_learning_evidence_source_node_version` (`db/models/learning_evidence.py`) | type+snapshot+node+version | yes | none | M7-5 |
| Score normalization | M5 | `diagnostic_evidence_ingestion.py:118-170` | points/max, weight, version | yes | generalize source | M7-5 |
| Mastery update | M5 | `MasteryService.refresh_state` (`mastery_service.py:45-120`) | user/course/node | yes | transaction-aware core | M7-5 |
| Mastery read | M5 | EXISTING APIs (`api/mastery.py:27-60`) | course/node/evidence | yes | internal before/after | M7-5 |
| Mastery idempotency | M5 | unchanged fingerprint returns `updated=false` (`mastery_service.py:73-89`) | evidence set/version | yes | none | M7-5 |
| Recommendation | M6 | pure engine (`recommendation_engine.py:51-83`) | typed context | yes | none | M7-5 |
| Plan refresh/idempotency | M6 | `LearningPlanService.generate` (`learning_plan_service.py:96-183`) | current context fingerprint | yes | post-commit recovery wrapper | M7-5 |
| Complete Session | none | PROPOSED completion POST | stored summary replay | no | atomic orchestrator | M7-5 |
| Learn route | Vue Router | EXISTING `/learn` (`frontend/src/router/index.ts`) | course query | yes | nested Session route | M7-1/6 |
| API client | Axios | `frontend/src/services/http.ts` | typed HTTP, 45s timeout | yes | Session service | M7-1/3/4 |
| Plan UI state | Vue | `composables/useLearningPlan.ts` | explicit view states | yes | Session composable | M7-1 |
| Learn UI | Vue | `views/LearnView.vue` | course + plan | yes | append workspace only | M7-1/6 |
| Acceptance tests | pytest/Vitest | M2–M6 tests; `learning-plan-views.spec.ts`, `router.spec.ts` | unit/integration/view | yes | Session E2E/errors | M7-6 |

## Counts

- Reusable implementation capabilities: **15 grouped entries** (16 when M5 read and refresh are counted separately).
- Proposed new entities: **3**.
- Original frozen proposed APIs: **9**.
- M7-1 minimum cancellation amendment: **1**; current total M7 contract APIs: **10**.
- M7-2 content endpoint: **IMPLEMENTED**.
- M7-3 Tutor GET/POST message endpoints: **IMPLEMENTED**. No M7-4–M7-5 API was implemented.
