# LearnPilot V1 — M3-E Implementation Report

## Actual Changes

M3-E adds a course-local, inspectable view of the completed M3 Course Knowledge Model. It is implemented inside the existing Course Detail workspace as a new `课程知识结构` tab; it does not add a global knowledge-graph route or navigation entry.

The delivered work includes a typed frontend data boundary, a lazy real graph canvas, node and edge detail drawers, provenance/evidence presentation, local relation filters, responsive graph controls, and one thin course-level build endpoint. It consumes the persisted M3-A through M3-D model rather than recreating any extraction, canonicalization, hierarchy, or prerequisite logic in the client.

M3-E adds no Student Model, mastery, confidence, learner progress, recommendation, assessment, graph editing, coordinate persistence, graph database, vector store, or additional knowledge-generation algorithm.

## Frontend Dependencies

`@antv/g6` is added at the exact version `5.1.1` and is the sole graph-rendering library. The package lock is updated consistently with that dependency.

`KnowledgeGraph.vue` loads G6 through `g6Loader.ts` using a dynamic import. The Vite manual chunk rule puts AntV modules into `knowledge-graph-vendor`, so the graph runtime is not loaded by the normal Course Detail material view. The graph adapter is library-neutral and does not expose G6 runtime types through API or domain contracts.

The production build reports the G6 vendor bundle-size advisory, but it is a lazily loaded visualization chunk rather than an initial-course-view dependency. This is documented as a non-blocking bundle warning, not hidden or suppressed.

## Frontend Design Workflow

The requested `frontend-design` skill is not available in this environment. The available `frontend-app-builder` skill was used instead to guide the M3-E visual work: a calm, course-local information layout, compact overview counters, a legible hierarchy/dependency canvas, and clear detail drawers without adding a separate dashboard or product surface.

## Knowledge Structure UI

`CourseDetailView` now has two lazy tabs:

- `课程资料`, preserving the existing M2 workflow;
- `课程知识结构`, which mounts `KnowledgeStructurePanel` only while active.

The panel uses the existing shared HTTP client and the typed `KnowledgeNode`, `KnowledgeEdge`, `KnowledgeSource`, edge-evidence, relationship-run, and build-result contracts in `frontend/src/types/knowledge.ts`. It renders:

- node, `CONTAINS`, and `PREREQUISITE` counts from the loaded model;
- independently toggled local relation filters;
- an explicit Chinese legend for both directed relation semantics;
- truthful loading, empty, error, disabled-build, in-progress, and update-failure states;
- a build/update control enabled after at least one current `SUCCESS` or retained M2 `EXTRACTED` parsed course material is available.

The UI intentionally contains no mastery, confidence, student status, completion, recommendation, or persisted presentation field.

## Graph Adapter and Visualization

`graphAdapter.ts` transforms the API model into a small local rendering shape while preserving real backend IDs. It validates displayed endpoints and relation types defensively, rejects malformed self/unknown edges from the canvas, and never creates a synthetic course, domain, category, or fallback root node.

Layout is deterministic and derived only from `CONTAINS` edges. Multiple real roots and disconnected concepts remain real top-level components; components are packed into bounded rows for readable fit-to-view behavior. `PREREQUISITE` edges do not influence hierarchy layout.

The visual semantics are explicit:

- `CONTAINS`: solid muted directed edge, parent/broader concept to child/specific concept;
- `PREREQUISITE`: blue dashed directed overlay, required prior knowledge to dependent knowledge.

The real G6 canvas supports drag-to-pan, wheel/gesture zoom, explicit zoom in/out, fit-to-view, reset, resize handling, and node/edge click selection. A visible fallback appears if the runtime graph cannot render.

## Provenance and Detail Drawers

Clicking a graph node uses `GET /api/courses/{course_id}/knowledge-nodes/{node_id}` and opens a drawer with its course-model description, constrained importance/difficulty labels, source material title, source reference, and bounded excerpt controls.

Clicking a graph edge opens a relation drawer that resolves both stored endpoints and states the direction in plain Chinese. It displays actual active relationship evidence when available, distinguishing material evidence, model inference, and structural evidence. The client does not invent citations; when no displayable evidence exists, it says so.

## Build Orchestration

M3-E adds `POST /api/courses/{course_id}/knowledge-model/build` with a typed response containing:

```text
course_id
material_count
node_count
contains_edge_count
prerequisite_edge_count
reused
```

`CourseKnowledgeBuildService` is deliberately an orchestration boundary. It validates bootstrap-owner course access and requires at least one same-course material whose parse status and persisted text content are usable. It then calls the existing M3-B extraction, M3-C canonicalization, and M3-D relationship services in order with `regenerate=False`.

It introduces no prompt, provider call format, extraction rule, deduplication policy, hierarchy inference, or prerequisite inference. Existing stage idempotency remains authoritative. If a newly published canonical result is followed by a relationship-stage failure, the service restores the prior current canonical run and managed-node activation state.

Build failures are mapped through the established API error contract: not-ready is `409`, invalid output is `422`, and stage failure is `502`. The frontend uses an endpoint-specific 180-second timeout and preserves an already displayed knowledge model if an update fails.

M3-E requires no new database migration; it uses the current M3-D schema and Alembic head.

## Tests

Focused backend coverage is in `backend/tests/test_m3e_course_knowledge_build.py` (4 tests). It verifies ordered reuse of the existing stages, parsed-material readiness, course ownership hiding, typed build payloads, and recovery of the previously active canonical model after a relationship failure.

Focused frontend coverage is split across two files (14 tests):

- `knowledge-graph-adapter.spec.ts` covers multiple roots without a synthetic node, disconnected nodes, bounded deterministic component layout, local relation filtering, malformed-edge exclusion, and a 50-node/80-edge fixture;
- `knowledge-structure-panel.spec.ts` covers empty and recoverable error states, build/reload, retained M2 `EXTRACTED` compatibility, post-build refresh-failure preservation, source provenance rendering, and explicit relation-direction drawers.

The observed focused M3-E backend result is `4/4`, the M3-A through M3-E backend subset is `60/60`, the full backend regression is `139/139`, and the full frontend Vitest suite is `31/31`.

## Frontend Toolchain Resolution

The workspace was verified with an isolated Linux Node.js `22.22.2` and npm `10.9.7` runtime, satisfying the frontend package engine range (`node >=22.12.0 <25`, `npm >=10`). No application dependency was replaced to work around the local toolchain; the package manifest and lockfile remain the project source of truth.

The observed frontend gates are:

- `npm run typecheck`: pass;
- `npm run lint`: pass;
- `npm run test`: `31/31` pass;
- `npm run build`: pass, with the documented lazy G6 vendor-size advisory.

## Browser Verification

Real-browser verification was performed against the built application using a self-authored, parsed course fixture. It exercised the Course Detail tab, graph loading, local relation filtering, graph pan, zoom, fit, reset, a node provenance drawer, and an edge relationship/evidence drawer.

The final graph was visually checked at `1440px`, `1280px`, and `1024px` widths. Resize handling refits the canvas so the course-content layout remains legible without a clipped graph at these acceptance widths.

## Real Provider E2E

The course fixture contained two self-authored TXT materials. Through the real course-level build flow, the configured OpenAI-compatible provider completed the existing M3-B through M3-D stages and returned a persisted model observed in the browser with 12 nodes, 3 `CONTAINS` edges, and 13 `PREREQUISITE` edges.

The browser check opened a real node drawer with stored source provenance and a real prerequisite-edge drawer with its stored explanation/evidence. No credential, provider endpoint, or secret value was logged in this report.

## Backend Regression

The focused M3-E backend tests passed `4/4`; the combined M3-A through M3-E backend subset passed `60/60`; the final full backend suite passed `139/139` in 102.18 seconds. Fresh SQLite and M2-to-current-head Alembic upgrades also passed.

## Frontend Regression

The frontend typecheck, lint, full Vitest suite (`31/31`), and production build passed after the M3-E changes. The existing Course Detail material workflow remains the default first tab, and the G6 module is not loaded unless the knowledge-structure tab is opened.

## Known Limitations

- No graph editing, manual positioning, coordinate persistence, or graph export is implemented.
- No new LLM extraction, canonicalization, hierarchy, or prerequisite algorithm was introduced by M3-E.
- No mobile-specific alternate graph representation or complete keyboard graph traversal is claimed.
- No Student Model, mastery, assessment, recommendation, learning path, tutor, agent, embedding, vector database, or graph database is implemented.
- The graph remains a course-model inspection surface, not a learner-progress surface.

## M4 Entry Conditions

M4 may compose a separate student-specific model with stable M3 course concepts only after preserving M3 course isolation, node identity, relationship semantics, source/evidence provenance, and current-run visibility.

M4 must not add mastery, confidence, progress, learner state, recommendation, or UI-coordinate fields to `KnowledgeNode`, `KnowledgeEdge`, the M3 graph adapter, or the M3 read/build contracts. Any learner-state visualization must remain distinguishable from this canonical course knowledge structure.
