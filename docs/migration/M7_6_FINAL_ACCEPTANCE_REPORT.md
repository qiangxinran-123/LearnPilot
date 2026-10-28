# LearnPilot V1 — M7-6 Final Acceptance Report

Date: 2026-10-28 · Result: **COMPLETE** · Baseline branch: `main`, HEAD `6e7bda3`

## 1. Final baseline

- Existing uncommitted M7-0–M7-5 files were retained. This stage modified
  `frontend/src/components/learning/TutorPanel.vue`, `frontend/src/views/LearningSessionView.vue`,
  `frontend/src/tests/learning-session-view.spec.ts` and `frontend/src/tests/practice-panel.spec.ts`, plus this report.
- Backend full pytest: **410 passed** in 297.86s against an explicitly isolated test database/upload path.
- Frontend full Vitest after fixes: **181 passed** in 29 files. TypeScript, ESLint, full-backend Ruff lint and format,
  and production build: **PASS**. Existing Vue synthetic-event warnings and Vite chunk-size advisory remain.
- Alembic has one head, `0018_m7_5_practice_evidence`. Empty SQLite databases were upgraded through head by the
  provider smoke and isolated fixtures; the full suite also covered populated earlier revisions upgrading to head.
- Actual Tutor mode: `provider`, using the existing OpenAI-compatible DeepSeek adapter. No credential was recorded.
- Initial and final `git diff --check`: PASS. No dependency, environment file, commit, branch or M5/M6 formula change.

## 2. End-to-end results

The final browser fixture used a dedicated temporary SQLite database and upload directory, not a user's database.
It contained a Computer Systems course, Cache Mapping node, a separate course, a real generated two-page PDF parsed by
the project's `PdfDocumentParser`, validated Cache/locality/LRU questions and a pre-existing persisted M5 state.
The PDF's second-page text was inserted into the isolated test database from the parser output; the fixture did not
exercise file upload/storage through the UI.

| Case | Result and evidence |
| --- | --- |
| E2E-01 recommendation → Session | PASS: M6 plan target Course 1 / Node 1 opened Session 2 from Learn; task order was enforced. |
| E2E-02 materials | PASS: browser showed the exact extracted Cache text and PDF page 2; M7-2 automated tests cover invalid references, missing content and cross-course exclusion. |
| E2E-03 Tutor | PASS: current integrated browser Session sent a real DeepSeek hint with PDF context. The isolated real-provider smoke independently passed hint, full explanation, insufficient evidence and cross-course isolation; browser also exercised full explanation and insufficient evidence. |
| E2E-04 practice | PASS: five actual browser submissions, correct/correct/wrong/wrong/correct; easy → medium after two correct, desired easy after two wrong, nearest available medium fallback. Single choice and true/false were exercised in browser; multiple choice was covered by M7-4 backend and frontend tests. |
| E2E-05 settlement | PASS: 5 persisted scored responses, 3 correct, 60%; five traceable practice Evidence rows, M5 score 88.10 → 75.71, delta −12.39 percentage points, confidence medium. |
| E2E-06 recommendation | PASS: post-commit M6 result remained Cache Mapping with actual knowledge-gap reason codes; no forced target change. M6 context tests verify latest mastery and prerequisite logic. |
| E2E-07 refresh/restart | PASS: browser summary and Tutor history survived reload and a backend restart in the real-PDF isolated environment; database counts and score remained stable after a repeated completion request in the equivalent isolated flow. |

The final user-facing practice fixture contained meaningful question stems and neutral option text. Earlier exploratory
fixtures with generic labels were not used as evidence for the final learning-content claim.

## 3. Data consistency and failure recovery

Read-only SQLite verification for the final Session found Assessment 2 and Response IDs 6–10. Evidence IDs 6–10
reference the corresponding snapshot and Response IDs exactly, source type is `practice`, and normalized scores are
1, 1, 0, 0, 1. Session is completed, recommendation refresh is succeeded, saved summary matches database mastery
75.71 and confidence medium; Tutor history contains two persisted messages. The previous assessment's five evidence
rows account for the state evidence count of ten.

- Repeated completion: browser/API and DB comparison passed; no second evidence or score change.
- Concurrent completion: `test_parallel_settlement_has_one_effect` passed in the full backend suite.
- Evidence/Mastery failure rollback and mismatched target rejection:
  `test_wrong_target_and_evidence_failure_roll_back` and
  `test_failure_rolls_back_and_recommendation_failure_can_retry` passed.
- Recommendation failure/retry preserves committed evidence/mastery: same failure-injection test passed.
- Isolation: M7-1/M7-2/M7-3/M7-5 tests and the actual cross-course provider smoke passed.
- Mastery rise/decrease: M7-5 backend tests passed; unchanged rendering is covered by the summary component test.
- Interrupted answer and settlement response: frontend component tests simulate network errors and retry the same
  request; backend idempotency tests verify persisted replay. A real packet-level connection cut was not performed.
- Tutor provider failure/timeout, no-document and insufficient-bank cases are covered by existing controlled tests;
  no repeated paid call was used to simulate failures.

## 4. Browser UX

Real Chromium was used against local isolated services. At desktop and 1024px, the Tutor panel remained separated
from the learning content; long real replies scroll within the message area and the composer remains visible. At
390px the layout stacks and the Tutor input remains available; the summary comparison and percentage-point wording
were visually reviewed. Screenshots and CLI snapshots are retained outside the Git worktree in the Codex
visualization folder. The responsive review is a local Chromium check, not a cross-browser compatibility claim.

## 5. Defects found and fixed

| Issue | Severity | Reproduction and root cause | Minimal fix / regression | Final |
| --- | --- | --- | --- | --- |
| M76-01 | P1 | First successful Tutor exchange starts a created Session on the server but the header still said “尚未开始”; TutorPanel did not notify its parent. | Emit a change event on successful send/retry and refresh the Session from the server; `learning-session-view.spec.ts` verifies it. A real browser provider exchange showed “学习中”. | Fixed |
| M76-02 | P1 | Completed Session summary hid all Tutor history although the backend retained it; completed template removed TutorPanel. | Add a collapsed, read-only Tutor history panel to completed Sessions; Session view regression and browser reload/restart confirmed history. | Fixed |

Open P0: **0**. Open P1: **0**. P2: **2** existing non-blocking advisories (Vite bundle size and synthetic Vue test
event warnings). No new dependency, algorithm change or M8 work.

## 6. Acceptance matrix

| AC | Result | Verification |
| --- | --- | --- |
| 01–04 | PASS | browser recommendation/Session and real parsed PDF; retrieval isolation tests |
| 05–06 | PASS | actual DeepSeek browser + four-scenario provider smoke; restart history |
| 07–10 | PASS | five browser answers and persisted scores; adaptive and multiple-choice automated tests |
| 11–14 | PASS | direct database provenance/state/summary inspection and M6 context tests |
| 15–18 | PASS | repeat request, concurrent and injected rollback/recommendation failure tests |
| 19–20 | PASS | browser refresh/restart, database inspection and isolation suites |
| 21–23 | PASS | browser full flow, summary, 1024px and 390px Chromium visual review |
| 24–27 | PASS | 410 backend / 181 frontend tests, quality checks and Alembic |
| 28–30 | PASS | Git diff check and scoped secret-pattern scan; M5/M6 formulas preserved; no M8 work |

## 7. Known limitations

- The browser fixture's PDF was generated and parsed as a real file, but its test MaterialContent was seeded directly;
  the separate material upload UI was not part of this M7-6 flow.
- Browser practice covered single-choice and true/false; multiple-choice is verified by existing automated backend
  and component tests. Prerequisite constraints are verified by M6 automated tests rather than this one-node target.
- Network interruption was simulated at the component/service test boundaries rather than by a real network proxy.
- Future M8 analytics remain outside M7 and are not a defect.

M7 acceptance is **COMPLETE**; LearnPilot V1 progress is **84%** and M8 is **READY** for a separate user instruction.
