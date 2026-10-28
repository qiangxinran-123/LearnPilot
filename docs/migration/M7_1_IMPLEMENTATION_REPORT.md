# LearnPilot V1 — M7-1 Implementation Report

Date: 2026-10-25 · Branch: `main` · Baseline HEAD: `6e7bda340f3d4205e24e86a1bf91c57f0c8c70be`

## 1. Development goal and contract review

M7-1 implements only the persisted Learning Session foundation: enter from the current M6 learning plan, create or
reuse a Session, maintain the frozen three-phase task state, restore it after interruption, and safely leave or cancel.
The three M7-0 entities are `LearningSession`, `LearningSessionTaskState`, and `TutorMessage`; this stage implements only
the first two. `TutorMessage` remains owned by M7-3.

M7-0 assigned four original APIs to M7-1 (create, active, detail, task PATCH), one to M7-2, one to M7-3, two to M7-4,
and one to M7-5. The frozen state machine required cancellation but omitted its HTTP transport, so M7-1 adds exactly one
contract amendment, `POST /api/learning/sessions/{id}/cancel`. It neither completes a Session nor invokes M5/M6 writes.

M7-1 owns mitigation of R1 (execution state is separate from M6 plan tasks), R7 (server-authoritative reload), R9
(additive migration on fresh and populated databases), R10 (full regression), and R12 (inactive node history/read and
write rules). R3/R4/R6/R11 remain with M7-3/M7-5 as frozen.

## 2. Existing modules reused

| Capability | Reuse evidence |
| --- | --- |
| Demo-user identity | `backend/app/repositories/user_repository.py`; `Settings.legacy_bootstrap_user` |
| Course ownership | `CourseRepository.get_for_owner` |
| KnowledgeNode course/activity | `KnowledgeNodeRepository.get_by_id` and composite course/node FK |
| M6 current plan/task source | `LearningPlan`, `LearningTask`, `LearningPlanStatus.AVAILABLE` |
| Active-row race pattern | M6 nullable `active_slot` pattern in `db/models/learning_plan.py` |
| Error envelope | `backend/app/core/errors.py` |
| HTTP/UI patterns | `frontend/src/services/http.ts`, `useLearningPlan`, `/learn`, existing design tokens |

No Question, Response, Evidence, Mastery, Recommendation algorithm, Tutor, retrieval, or workflow abstraction was
duplicated.

## 3. New models

### LearningSession

Implemented in `backend/app/db/models/learning_session.py`. It binds one user, course, active target KnowledgeNode, and
optional source M6 plan. Status is `created|in_progress|completed|cancelled`; `completed` has no M7-1 transition. The
model includes the frozen future hand-off fields (`practice_assessment_id`, immutable nullable `completion_summary`, and
`recommendation_refresh_status`) but M7-1 never populates them beyond `not_requested`.

The `(user_id, course_id, target_knowledge_node_id, active_slot)` unique key prevents duplicate active Sessions for the
same target under SQLite/MySQL-compatible semantics. The composite course/node FK prevents cross-course targets and
restricts direct target deletion. Source plan/task links use `SET NULL` so historical execution state remains readable.

### LearningSessionTaskState

Implemented in `backend/app/db/models/learning_session_task_state.py`. Creation atomically adds exactly:

1. `concept_learning` / order 0;
2. `guided_example` / order 1;
3. `adaptive_practice` / order 2.

Task status is the frozen `not_started|in_progress|completed`. Unique phase/order constraints and a small JSON progress
object support persistence without creating a workflow engine. M6 task IDs are linked where task types match.

## 4. Alembic migration

`backend/alembic/versions/0015_m7_1_learning_sessions.py` adds only `learning_sessions` and
`learning_session_task_states`; prior migrations and M0–M6 tables are unchanged. Automated checks cover both empty
database → head and a populated M6 database at `0014` → head. SQLite foreign keys, uniqueness, enum checks, and indexes
match the ORM; no dialect-specific feature or external database was introduced.

## 5. Implemented APIs

| Method/path | Behavior | Idempotency/errors |
| --- | --- | --- |
| `POST /api/learning/sessions` | validates owned course + active in-course node or available owned M6 plan; creates three tasks | same active target returns 200 + `reused=true`; new returns 201; race recovers winner |
| `GET /api/learning/sessions/active?course_id=` | latest owned active Session for the course or `null` | read-only; foreign course is 404 |
| `GET /api/learning/sessions/{id}` | owned aggregate for reload/history | cross-user and missing are hidden as 404 |
| `PATCH /api/learning/sessions/{id}/tasks/{phase}` | monotonic, ordered progress; first write starts Session | same-state replay is safe; regressions/skips/terminal writes are 409 |
| `POST /api/learning/sessions/{id}/cancel` | created/in-progress → cancelled and clears active slot | repeat returns stored terminal state; completed cancellation is 409 |

The response includes course/node display names so the workspace does not need an unscoped secondary lookup. Existing
API error envelopes are preserved. Core rules live in `LearningSessionService`; repository code only performs scoped
data access.

## 6. Session state machine

```text
CREATED --first supported task write--> IN_PROGRESS
   |                                      |
   +---------------- cancel --------------+--> CANCELLED

COMPLETED is reserved for the M7-5 verified completion transaction.
```

Concept and guided-example tasks advance one state per request in order. Adaptive practice is a persisted placeholder;
any attempted state change returns `TASK_PHASE_NOT_AVAILABLE`. Inactive targets remain historically readable but reject
new progress. Browser close performs no write; the next GET restores server state.

## 7. Frontend changes

- `LearnView.vue` loads the course's active Session, exposes “开始学习 / 继续学习”, guards repeated clicks, and displays
  actionable loading/error state.
- `/learn/sessions/:sessionId` keeps the existing Learning navigation label and opens `LearningSessionView.vue`.
- The workspace displays the real course, target, three persisted phases and server status. Concept/example progress is
  saved through the typed client. Adaptive practice explicitly says it is unavailable and never shows a fake question,
  score, learning time, summary, Tutor, or Mastery change.
- Return leaves the resumable Session unchanged; cancel first persists `cancelled`, then returns to `/learn`.
- `learningSessions.ts`, `learningSession.ts`, and `useLearningSession.ts` reuse the existing Axios/error/composable
  conventions. No new Pinia/global-state layer or navigation item was added.

The `frontend-design` guidance was applied only to hierarchy, feedback, accessibility and responsive behavior while
retaining LearnPilot's existing blue/white tokens and component language.

## 8. Git change scope

Changed scope is limited to the two ORM models/enums, schema/repository/service/router registration, one additive
migration, M7-1 tests, the Learn route/workspace/client/types/composable/tests, this report, and the minimal M7-0
cancellation addendum. The user's three untracked M7-0 documents remain present. No `.env`, secret, lockfile, dependency
version, M4/M5/M6 algorithm, commit, branch, tag, or remote state was changed.

## 9. Verification results

| Check | Result |
| --- | --- |
| M7-1 backend focused | PASS — 10/10 |
| Full backend regression | PASS — 369/369 |
| Frontend Vitest | PASS — 150/150 across 24 files |
| TypeScript | PASS |
| ESLint | PASS |
| Production build | PASS (existing large-chunk warning only) |
| Ruff lint / format | PASS |
| Alembic fresh database | PASS |
| Alembic populated M6 upgrade | PASS |
| `git diff --check` | PASS |

WSL uses the already-installed nvm `0.40.8`, Linux Node `v24.22.0`, and npm `11.19.1`, satisfying `>=22.12 <25`.
`npm ci` used the committed lockfile. npm reported eight dependency audit advisories (3 moderate, 3 high, 2 critical);
no automatic dependency mutation was authorized. Existing diagnostic tests emit non-failing Vue event-validation
warnings. Repository-wide Prettier still reports unrelated pre-existing style differences; every M7-1 frontend file
was explicitly formatted and passes targeted Prettier verification.

## 10. Manual acceptance procedure

1. Start the existing backend and frontend with the repository's documented commands.
2. Open a course that has a current M6 learning plan and go to Learning.
3. Click “开始学习”; verify the URL is `/learn/sessions/{real-id}` and the course/KnowledgeNode match the plan.
4. Verify the three ordered phases appear and Adaptive Practice clearly reports M7-4 is not available.
5. Start Concept Learning. Refresh the browser; verify Session and task remain `in_progress`.
6. Mark Concept Learning complete, then start Guided Example; confirm guided cannot be started before concept completion.
7. Return to Learning without cancelling; verify the “可继续的学习会话” banner and resume the same ID.
8. Click start/continue repeatedly; verify only one active Session row exists for that user/course/target.
9. Cancel the Session; verify it disappears from active recovery and its detail remains read-only.
10. Try an unknown Session ID and verify the explicit error state.
11. Inspect `learning_evidence`, `student_knowledge_states`, and active M6 plan rows before/after; verify no new Evidence,
    Mastery update, or recommendation regeneration occurred.

## 11. Deferred M7 capabilities and known limits

- M7-2 owns actual concept/example material retrieval and citations; M7-1 displays no fabricated content.
- M7-3 owns TutorMessage, prompts and provider calls; no Tutor UI or DeepSeek call exists here.
- M7-4 owns practice Assessment/questions/scoring; the task cannot advance in M7-1.
- M7-5 owns verified completion, Evidence, Mastery, post-commit recommendation refresh and summary. There is no M7-1
  completion endpoint.
- The active endpoint returns the most recently updated active Session for a course. The database permits separate active
  Sessions for different targets as frozen; the normal M6 path exposes only the current target.
- npm audit advisories should be handled in a separately authorized dependency-maintenance task, not by changing the
  M7-1 lockfile.

## 12. M7-2 entry conditions

M7-2 may proceed after human acceptance when: migration `0015` is applied; the Session aggregate and five M7-1 APIs are
treated as stable; retrieval remains course/target scoped; content writes use only supported task progress; and M7-2
does not make Adaptive Practice completable or write Evidence/Mastery/Recommendation. No unresolved M7-1 architecture
decision blocks M7-2.

## 13. Acceptance status

AC-01–AC-30 are satisfied by the implementation and verification above. M7-1 implementation status is **COMPLETE**
and awaits the user's human acceptance. Project progress may be recorded as **75% only after that acceptance**.
