# LearnPilot V1 — M4-D Diagnostic Frontend Architecture

## Scope

M4-D exposes the existing M4-A/C diagnostic lifecycle through a thin owner-scoped HTTP boundary and implements the
Vue experience for course readiness, start/resume, objective answering, autosave, refresh recovery, submission, basic
persisted score display, and lightweight history. It does not implement knowledge-node performance, weakness analysis,
answer explanations, knowledge-map overlays, recommendations, Learning Evidence, Mastery, or Confidence.

## Non-Negotiable M4 Architecture Decisions

- **ARCH-01 — Deterministic Scoring:** the frontend submits no score, correctness flag, answer key, or scoring policy.
  `POST .../submit` invokes the M4-C submission service, which reads immutable snapshots and runs the versioned pure
  scorer. Vue only renders the persisted aggregate response.
- **ARCH-02 — Historical Reproducibility:** assessment reads convert stored `AssessmentQuestion` snapshots to a safe
  candidate DTO. Recovery and history never reassemble a paper or reconstruct content from current Question or
  KnowledgeNode rows.
- **ARCH-03 — Structured Protected Responses:** draft writes use `objective_answer_v1`; the backend enforces owner,
  assessment-question membership, state, and answer shape. Submission waits for frontend saves, creates explicit empty
  responses for unanswered items, scores and locks all rows transactionally, and makes subsequent writes fail.

These decisions remain binding for M4-E and M4-F.

## Frontend Routes and Page Structure

- `/diagnose` loads real courses, owner history, and a side-effect-free readiness preview. It presents a restrained
  course setup panel and recent diagnostic list within the existing LearnPilot navigation.
- `/diagnose/assessments/:assessmentId` loads the fixed paper, starts a READY attempt idempotently, restores server
  answers, provides question navigation, and shows either the answer surface or the persisted completion summary.

The implementation uses existing Vue 3, Vue Router, Element Plus, Axios and LearnPilot design tokens. A single
`useDiagnosticAssessment` composable owns attempt state; no redundant Pinia store hierarchy was introduced.

## Diagnostic API Contract

The `/api/diagnostics` router is an input/output adapter over `AssessmentAssemblyService`,
`DiagnosticDomainService`, and persisted score summaries:

```text
GET  /courses/{course_id}/readiness
POST /assessments
GET  /assessments
GET  /assessments/{assessment_id}
POST /assessments/{assessment_id}/start
PUT  /assessments/{assessment_id}/responses/{assessment_question_id}
POST /assessments/{assessment_id}/submit
GET  /assessments/{assessment_id}/result
```

The existing demo-user ownership foundation is resolved server-side. Other-owner courses and assessments are
indistinguishable from missing resources. The create operation reuses the newest READY/IN_PROGRESS assessment for the
same owner and course, preventing ordinary request retries from creating duplicates.

## Candidate View Security

`DiagnosticAssessmentDetailSchema` contains fixed order, type, stem, ordered options, difficulty, and the user's saved
selection. It never contains correct answers, explanation, source references, scoring policy, correctness, or points.
Aggregate score data is available only after the persisted Assessment is SUBMITTED. This protection is applied in the
server DTO, not by hiding browser fields.

## Readiness and Start/Resume

`preview_readiness` reuses M4-C's current core-node, eligible-question, dynamic-count, and coverage rules without
creating an Assessment. It reports actual eligible/covered/available counts, estimated paper size, and estimated time.
Missing knowledge structure and insufficient validated bank are distinct states. No question generation or quality
threshold degradation occurs in M4-D.

## Autosave and Refresh Recovery

An answer changes local state immediately, then enters a per-question promise chain. Repeated changes to one question
are persisted serially; revision tokens prevent an older completion from marking a newer selection as saved. UI states
are `idle`, `unsaved`, `saving`, `saved`, and `failed`. A failed write remains visibly failed and can be retried.

On refresh, the paper and saved answers are loaded from the server. `sessionStorage` stores only the current display
index; it is never an answer source of truth.

## Submission and Idempotency

Confirmation shows total, locally answered, and unanswered counts. Confirming submission locks editing, waits until all
save chains settle, blocks if any save failed, and then calls the bodyless submit endpoint. The server uses its own
saved responses; missing responses become versioned empty answers and deterministically score zero. A repeated submit
returns the same persisted result without rescoring. On an ambiguous network failure, the frontend first reloads server
state and presents the result if submission actually committed.

## Error, Loading, and Empty States

The pages explicitly handle course/history loading, no courses, missing knowledge structure, insufficient bank,
readiness failure, assessment load failure, save failure, submission failure, submitted state, not found, and hidden
unauthorized resources. Backend stack traces are never rendered.

## History

History returns course, created/submitted timestamps, status, fixed item count, answered count, and aggregate accuracy
only for submitted attempts. In-progress attempts display no fabricated score and route back to their stored paper.
No progress trend or M4-E analysis is calculated.

## M4-E Boundary and Known Limitations

M4-E may derive a knowledge-level report from immutable snapshots and persisted M4-C scores. M4-D intentionally shows
only total items, correct items, and accuracy. It exposes no answer explanation or node result. Authentication remains
the existing demo-user ownership foundation. Browser automation on this workstation was blocked by its proxy routing
of isolated localhost ports; HTTP integration and Vue tests cover the workflow, but this is not represented as a
successful manual browser run.
