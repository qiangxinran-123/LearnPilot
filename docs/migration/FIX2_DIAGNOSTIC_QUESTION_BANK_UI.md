# LearnPilot V1 — FIX-2 Diagnostic Question Bank UI Report

## Scope

FIX-2 adds the smallest course-scoped interface needed to prepare and review diagnostic questions through the existing FIX-1 backend. It does not implement a second validator, change M4 assembly policy, modify M5/M6, call a real LLM during tests, generate production questions, or enter M7.

## Modified files

- `frontend/src/components/diagnostic/QuestionBankPanel.vue`
  - Course-scoped readiness, required-node and question display.
  - Explicit single-question generation confirmation.
  - Full review detail with answer, explanation, material reference and excerpt.
  - Official approve/reject calls with submission locks and server refresh.
- `frontend/src/views/CourseDetailView.vue`
  - Mounts the panel in the existing course overview without adding navigation.
- `frontend/src/services/diagnostics.ts`
  - Typed FIX-1 API client methods.
- `frontend/src/types/diagnostic.ts`
  - TypeScript contracts matching the FIX-1 Pydantic responses.
- `frontend/src/tests/question-bank-panel.spec.ts`
  - Eight focused interaction tests.
- `frontend/src/tests/course-material-discoverability.spec.ts`
  - Stubs the new child in the pre-existing material-only Course Detail tests to keep those tests isolated.

No backend source, database model, migration, M5/M6 logic, or Vue route was changed by FIX-2.

## FIX-1 API reused

All requests continue through the shared `httpClient`.

| Purpose | Method and path |
|---|---|
| Readiness | `GET /diagnostics/courses/{course_id}/question-bank` |
| Question list | `GET /diagnostics/courses/{course_id}/questions` |
| Generate one | `POST /diagnostics/courses/{course_id}/questions/generate` |
| Approve | `POST /diagnostics/courses/{course_id}/questions/{question_id}/approve` |
| Reject | `POST /diagnostics/courses/{course_id}/questions/{question_id}/reject` |

Generation sends only `knowledge_node_id` and the literal `count: 1`. The client cannot supply validation status, answer, source references, provider or model.

## Readiness presentation

The panel displays server-provided:

- validated, pending and rejected counts;
- minimum and current required question counts;
- covered and total core-node counts;
- `can_start`, `reason_code`, and ordered required nodes;
- per-required-node validated/pending status.

The frontend does not reproduce M4 sorting or coverage logic and never increments counts locally. After successful review, it fetches both readiness and the question list again.

## Generation interaction and cost control

Generation requires two distinct actions:

1. select an uncovered server-provided required node;
2. open the confirmation dialog and explicitly confirm one question.

The dialog identifies the node, fixes the quantity at one, and states that a real AI call may incur cost and still requires human review. A synchronous request lock disables duplicate submission. No lifecycle hook, refresh, readiness state, review success, loop, automatic retry, or batch control calls generation.

If a request times out, the UI instructs the user to refresh the server state before deciding whether to retry. It never retries a paid request automatically.

## Review workflow

The review dialog shows:

- knowledge node, question type and difficulty;
- stem and options;
- correct answer and explanation;
- material title when supplied;
- exact source reference;
- source excerpt when supplied.

Approve and reject remain server-authoritative. The component waits for the official API response, never mutates `validation_status` optimistically, disables both actions during submission, and preserves the current pending display on failure. A successful transition triggers fresh GET requests and never starts generation for another node.

## READY navigation

When the backend returns `can_start=true`, the panel shows “前往诊断” and navigates to the existing `diagnose` route with `courseId` in the query. `DiagnoseView` already consumes that query and performs its own readiness check. Navigation neither creates an assessment nor generates questions.

## Error and empty states

The panel provides explicit loading, recoverable load error, empty question bank, missing required-node, pending, validated, rejected, generation error, provider-not-configured, timeout, invalid-state and invalid-source presentations. Backend messages are normalized; internal prompts, stacks and provider details are not exposed.

## Tests and validation

Focused command:

```bash
npm run test -- --run src/tests/question-bank-panel.spec.ts
```

Result: `8/8 passed`.

The focused tests cover:

- GET-only initial load;
- confirmation before POST;
- fixed node and one-question payload;
- duplicate-submit lock;
- pending display after generation;
- no automatic retry on generation failure;
- full review evidence;
- server-authoritative approve/reject;
- no optimistic status update;
- refresh after successful review;
- stable pending state after review failure;
- server-derived readiness values;
- READY navigation with current course;
- recoverable load errors.

Full frontend validation:

- `npm run typecheck`: PASS
- `npm run lint`: PASS
- `npm run test`: `124/124 passed` across 23 files
- `npm run build`: PASS

The production build retains the existing non-blocking large-chunk warning. Two pre-existing Vue event-validation warnings remain in `diagnostic-assessment.spec.ts`; they do not fail tests and are outside FIX-2.

Backend regression was not rerun because FIX-2 made no backend changes. FIX-1 had already passed its backend acceptance.

## Browser verification

`BROWSER_CHECK = NOT VERIFIED`.

The available browser-control helper exited unexpectedly during initialization twice. Per its recovery rules, no further UI input was attempted. No generation confirmation was submitted and real LLM calls remained zero. The browser path remains for the user to verify manually against the running application.

## Impact and limitations

- Existing M4 diagnosis and M6 pages remain unchanged.
- No real diagnostic questions were generated.
- No assessment, Mastery, Learning Evidence, recommendation or learning plan was changed.
- Source availability is not guessed per node because FIX-1 does not expose that field; generation errors provide the authoritative result.
- Browser-level verification remains outstanding, while the equivalent UI states and actions are covered by mocked Vitest tests.

## Acceptance

FIX-2 is complete at the code and automated-test level. The UI provides an explicit, one-node/one-question, human-reviewed workflow over the official FIX-1 APIs. LearnPilot project progress remains 72%.
