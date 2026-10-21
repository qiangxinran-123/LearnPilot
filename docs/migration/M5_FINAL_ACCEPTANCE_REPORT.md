# LearnPilot V1 — M5 Unified Final Acceptance Report

Date: 2026-10-21

## Final decision

- M5 status: **COMPLETE**
- LearnPilot V1 progress: **63%**
- M6 readiness: **READY**
- P0/P1 defects: **0**
- Database migration for final closure: **NOT REQUIRED**

This closure changed no production business code, project dependency, database schema, algorithm, or user data. It installed only the WSL system libraries required to run the already-cached Chromium browser.

## Stage acceptance

| Stage | Result | Evidence retained for final acceptance |
| --- | --- | --- |
| M5-A Evidence Domain | PASS | LearningEvidence persistence, ownership, historical identity, database uniqueness, migration, and integrity tests |
| M5-B Evidence Ingestion | PASS | submitted/scored-only extraction, deterministic normalization, multi-node attribution, backfill/dry-run, idempotency, failure recovery, and automatic synchronization tests |
| M5-C Mastery Engine | PASS | deterministic weighted prior smoothing, evidence eligibility, stable fingerprint, versioned idempotent persistence, and recalculation tests |
| M5-C Confidence Engine | PASS | evidence-count, assessment-independence, difficulty-coverage, and performance-variation rules |
| M5-D Student State API | PASS | read-only course/node/evidence APIs, ownership isolation, answer protection, empty/stale/version behavior, and no-write tests |
| M5-E Knowledge Map | PASS | existing M3 map reuse, structure/mastery modes, real M5-D contract mapping, URL focus, async safety, and evidence explanation |
| FIX-1 Source Preview | PASS | verified MaterialContent segment matching, bounded preview, ownership/reference validation, safe fallback, and live browser display |
| FIX-2 AI Tool Discoverability | PASS | status-aware course-material hint and reuse of the existing Material Detail tools |

## Environment closure

The frontend was verified with WSL-native Linux Node v24.22.0 and npm 11.19.1. Vite 6.4.3 and FastAPI were reachable at the normal local ports. Playwright 1.63.0 already had matching Chromium revision 1243 cached, so no browser or project dependency was downloaded.

Chromium initially lacked `libnss3`, `libnspr4`, and `libasound.so.2`. Six Ubuntu runtime packages were installed (`libnss3`, `libnspr4`, `libasound2t64`, `libasound2-data`, `alsa-topology-conf`, and `alsa-ucm-conf`), using approximately 8.2 MB. Chromium then launched successfully. The documentation directory was writable and both required reports were written and reread successfully.

## Real browser verification

Normal read-only checks used:

- frontend: `http://127.0.0.1:5173`
- backend: `http://127.0.0.1:8000`

Evidence-bearing checks used an isolated copy of the demo SQLite database:

- frontend: `http://127.0.0.1:5174`
- backend: `http://127.0.0.1:8001`
- database: `/tmp/learnpilot-m5-browser.sqlite3`

The isolated copy contained three submitted, deterministically scored assessments for the existing course and node. The real M5 ingestion and mastery services produced three evidence records and a persisted `mastery_v1` state: score 60.71, status `needs_reinforcement`, confidence `low`, and three independent assessments. No paid LLM call was made.

| Browser flow | Expected result | Actual result |
| --- | --- | --- |
| Home and navigation | Home, course list, and five primary navigation items load | PASS; HTTP 200, one course visible, no blocking console errors |
| M3 Knowledge Map | Existing nodes/edges, focus, zoom, pan, and URL state remain functional | PASS; 59 nodes, 31 relationships, focused `nodeId=4`; zoom changed 89%→104%; pointer-pan changed translation by 80×35 px; reset restored 100% |
| M4 report → M5 map | Submitted report opens its historical node in the correct course map | PASS; report assessment 3 navigated to course 1 / node 4, then retained the node while entering mastery mode |
| M5 overlay | Persisted mastery, confidence, counts, and unassessed nodes render without frontend recomputation | PASS; node 4 showed 61%, `有待巩固`, confidence `低`, 3 evidence; other nodes showed `待评估` rather than 0%/50% |
| Evidence explanation | Details match the persisted state and included evidence | PASS; algorithm `mastery_v1`, three diagnostic sources, scores 100%/0%/100%, and three independent diagnoses were displayed |
| FIX-1 source preview | Verified, bounded original text is distinct from AI knowledge description | PASS; verified DOCX segment 60/61 excerpts were displayed, further sources were collapsed, and Material Detail links worked |
| FIX-2 material tools | Successful materials advertise existing tools and open the original detail page | PASS; both successful materials showed the hint; Material Detail retained Content, Summary, Study Cards, and Material QA controls |
| Async and refresh | Rapid node changes end on the latest node; URL state remains consistent | PASS; the final rapid selection was node 6 and the URL contained `nodeId=6&mode=mastery` |
| Responsive layout | Core M5-E/FIX views fit at 1024 px and 1440 px | PASS; document scroll width equaled viewport width for map, evidence detail, and material list |
| Read-only browser boundary | Mastery and evidence reads do not mutate business data | PASS; audited map/detail flows issued no POST/PUT/PATCH/DELETE requests |

The normal demo database had no historical assessment, so evidence-bearing browser checks were deliberately performed against the isolated `/tmp` copy. The submitted-diagnostic write path, idempotent re-ingestion, failure recovery, ownership isolation, and immutable-record protection remain covered by the previously passed HTTP/backend integration tests; they were not misrepresented as browser-driven submission.

## Automated and migration evidence

- Frontend full suite: **106/106 PASS** under the current Linux Node runtime.
- Backend full suite: **299/299 PASS**; reused because final closure changed no production code.
- TypeScript: **PASS**.
- ESLint: **PASS**.
- Vite production build: **PASS**; the existing chunk-size warning is non-blocking.
- Ruff lint and format: **PASS**.
- Alembic: **PASS**, upgraded through `0012_m5c_student_knowledge_state`.
- Git diff check: **PASS**.
- Secret scan: **PASS**.
- Frontend dependency versions: unchanged.
- Production business code: unchanged during final closure.

## Architecture and data safety

- ARCH-01 Deterministic Scoring: **PRESERVED**. M5 consumed saved M4 scores and did not rescore or call an LLM.
- ARCH-02 Historical Reproducibility: **PRESERVED**. Immutable question snapshots and historical node references remained the source identity; no name-based remapping occurred.
- ARCH-03 Protected Structured Responses: **PRESERVED**. Evidence/state reads and updates did not write back to submitted responses, snapshots, or scores.
- The user’s dirty worktree and normal demo database were preserved. No commit, push, reset, clean, stash, branch switch, or migration change was performed.

## Non-blocking items

- The Vite chunk-size warning remains informational.
- The safe live material set contained only successfully parsed documents; parsing/failed-state messaging is covered by the existing component tests rather than newly created browser data.
- FIX-3 AI-generation latency, M6 recommendations, M7 tutoring/practice, M8 analytics, MySQL, OAuth, and deployment work remain outside this acceptance.

## Closure

All M5 final acceptance conditions are satisfied. M5 is formally complete at 63%, and M6 may begin only after explicit user authorization.
