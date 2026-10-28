# LearnPilot V1 — M7-0 Readiness Report

Date: 2026-10-25 · Result: **COMPLETE — M7-1 READY**

## 1. Repository baseline

| Item | Value |
| --- | --- |
| Repository | `//wsl$/Ubuntu/home/qxrrr/projects/campus-ai` (`/home/qxrrr/projects/campus-ai` in WSL) |
| Branch / HEAD | `main` / `6e7bda340f3d4205e24e86a1bf91c57f0c8c70be` |
| Last commit | `feat: deliver M6 recommendations and learning plans` |
| Prior commits | `0a21c38`, `afc0dab`, `c820274`, `1225bc5` |
| Pre-existing modification | `scripts/start_dev.sh` |
| Pre-existing untracked files | none reported |
| Initial `git diff --check` | PASS (no output in WSL) |

Windows Git first reported UNC safe-directory/sequencer limitations; no global config was changed. Read-only WSL Git
provided the baseline. No reset, clean, restore, checkout, stash, commit, push, tag, switch or branch action occurred.

## 2. Review and verification

| Scope | Actual code reviewed | Result |
| --- | --- | --- |
| M2 Material/LLM | models, parser/chunks, client/prompts/references, service/API/settings/tests | PASS |
| M3 Knowledge | node/edge/source/run models, service/API/repositories/validation/tests | PASS |
| M4 Question/Assessment | Question/link/Assessment/snapshot/Response, services/repositories/API/tests | PASS |
| M5 Evidence/Mastery | evidence/state models, ingestion/validation/mastery/read/calculator/API/tests | PASS; planned practice extension |
| M6 Recommendation | context, pure engine, plans/tasks, persistence/API/tests/frontend | PASS |
| Frontend | router/nav/client/stores/composables/types/Learn/Dashboard/tokens/tests | PASS static review; runtime NOT RUN |

Focused backend verification: **120 passed in 41.90s** across M2 material, M3 model, M4 scoring, M5 ingestion/mastery,
and M6 engine/plan suites. No real/paid LLM call. Frontend Vitest did not start because WSL lacks Linux Node and finds
Windows npm, whose cmd.exe rejects the UNC directory. This is an environment limitation, not a failed test.

## 3. Confirmed interfaces and reuse

Existing: material content and single-material QA; knowledge model/node detail; diagnostic readiness/question bank and
assessment lifecycle; course/node mastery and evidence reads; learning-plan GET/generate. There is no Session, Session
content, Tutor, adaptive-practice or Session-completion API today. All nine M7 APIs are marked PROPOSED.

Reuse 16 capabilities: ownership; parsed text/segments; chunking/ranking; citation validation; provider/mock adapter;
node detail/sources; prerequisite graph; validated question selection; immutable snapshots; Response; deterministic
scorer; Evidence identity; Mastery refresh/read/fingerprint; pure recommendation; persisted plan generation; shared
frontend plan/client/route patterns. Detailed paths are in the contract matrix.

Minimal extensions: M7-1 Session/task execution state; M7-2 node-scoped lexical retrieval; M7-3 Tutor context/messages;
M7-4 practice Assessment type and filtered selector; M7-5 practice evidence source plus transaction-aware M4/M5 core
and post-commit M6 recovery. No duplicate algorithm/model system.

## 4. Frozen outcome

- Proposed entities: **3** — LearningSession, LearningSessionTaskState, TutorMessage.
- `PracticeAttempt` rejected: one M4 practice Assessment per Session plus fresh AssessmentQuestion/Response supports
  repeated use while retaining immutable history.
- Proposed APIs: **9**, with schemas/errors/ownership/state/idempotency/stage in the design §5.
- State machine: CREATED → IN_PROGRESS → COMPLETED; CREATED/IN_PROGRESS → CANCELLED; completed is read-only/replayable.
- Retrieval: Strategy A (KnowledgeSource exact segments + bounded lexical ranking); no vector dependency.
- Tutor: minimal typed context, strict course ancestry/citations, injection separation, answer redaction, no Evidence.
- Completion: one core DB transaction through Mastery; M6 plan refresh after commit with persisted retry status.

## 5. Risk register

| ID | Risk / level | Code evidence | Minimum mitigation | Stage / acceptance |
| --- | --- | --- | --- | --- |
| R1 | Session duplicates plan/task — Medium | M6 task lacks progress (`learning_task.py:19-50`) | store execution only, link plan/task IDs | M7-1 model + race tests |
| R2 | M4 cannot carry practice — Medium confirmed gap | diagnostic-only type; Response unique per snapshot | practice Assessment, fresh snapshots; no PracticeAttempt | M7-4 cross-Session history test |
| R3 | M5 rejects/duplicates practice — **High** confirmed | diagnostic-only validator; evidence unique key | practice source using same FKs/key | M7-5 concurrent replay test |
| R4 | M6 plan refresh has side effects/failure — **High** | `LearningPlanService.generate:96-183` | run post-commit; persist failed/pending; retry | M7-5 injected failure/reuse |
| R5 | lexical retrieval misses content — Medium potential | `relevant_chunks` lexical; QA one material | source-first fixtures; fallback only if proven | M7-2 precision/isolation tests |
| R6 | Tutor leaks answer — **High** potential | snapshots hold answer/explanation | redact pre-submit, strategy gate | M7-3/4 adversarial tests |
| R7 | client/server states diverge — Medium | no Session state today | server authoritative, CAS, refetch conflict | M7-1/6 reload/two-tab E2E |
| R8 | long AI request harms UX — Medium | 45s timeout/retry, no streaming | local pending/cancel, idempotent retry | M7-3/6 timeout tests |
| R9 | migration regresses existing data — **High** potential | accepted 0008–0014 constraints | additive, populated-M6 upgrade | M7-1/4/5 migration + full regression |
| R10 | M7 regresses M0–M6 — **High** general | accepted services own behavior | wrappers/new paths, algorithms unchanged | every stage + full M7-6 regression |
| R11 | nested transactions break atomic completion — **High** confirmed | M4/M5 public methods call `session.begin()` | transaction-aware core under one outer transaction | M7-5 failure injection rollback |
| R12 | node lifecycle breaks Session — Medium | M3 deactivates/deletes nodes | composite FK RESTRICT; inactive blocks writes; history readable | M7-1 lifecycle tests |
| R13 | Tutor contaminates Mastery — invariant | no Tutor Evidence type | never add Tutor weight/source | M7-3/5 zero-evidence test |

Critical/high implementation risks: **6** (R3, R4, R6, R9, R10, R11). Each has an owner and acceptance method;
unresolved blocking decisions: **0**.

## 6. M7-1 entry conditions

| Condition | Result |
| --- | --- |
| M6 target/ownership source identified | PASS |
| minimal Session relations frozen | PASS |
| three phases and recovery frozen | PASS |
| state transitions/idempotency frozen | PASS |
| foundation APIs frozen | PASS |
| later retrieval/Tutor/practice/closed-loop boundaries assigned | PASS |
| no unresolved decision changes M7-1 identity | PASS |
| worktree protected | PASS |

## 7. AC-01–AC-20

| AC | Result | Evidence |
| --- | --- | --- |
| 01–03 actual M2–M6 review/reuse/extensions | PASS | design §2 + matrix |
| 04–06 model/state/API | PASS | design §§3–5 |
| 07 retrieval | PASS | design §6 |
| 08 Tutor context | PASS | design §7 |
| 09 practice/M4 reuse | PASS | design §8 |
| 10 Evidence/dedup | PASS | design §§9–10 |
| 11 Mastery/recommendation | PASS | design §§9–10 |
| 12 transaction/recovery | PASS | design §10 |
| 13 frontend | PASS | design §11 |
| 14 phase non-overlap | PASS | design §13 |
| 15 no M7 capability implemented | PASS | docs-only M7-0 changes |
| 16 M0–M6 business code untouched | PASS | final Git check |
| 17 no DB/migration | PASS | final Git check |
| 18 prior Git edits preserved | PASS | `scripts/start_dev.sh` remains modified |
| 19 complete/executable docs | PASS | three deliverables |
| 20 no M7-1 blocking decision | PASS | blockers 0 |

## 8. Final result

M7-0 is **COMPLETE**; M7-1 is **READY** after user acceptance; LearnPilot V1 may be recorded as **73%**. This report
authorizes no M7 implementation, migration, provider call, commit, push or branch change.

## 9. M7-1 contract amendment (2026-10-25)

M7-1 implementation preserved all nine frozen interface owners and added one narrowly scoped cancellation transport:
`POST /api/learning/sessions/{id}/cancel`. The M7-0 state machine already required `CANCELLED`; the omission was in the
API table only. Current M7 contract count is therefore ten. No M7-2–M7-5 ownership or completion semantics changed.
