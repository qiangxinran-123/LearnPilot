# M3-E Implementation Report

## 1. Stage goal

Deliver a product-ready course learning workspace over verified M2 and M3-A through M3-D capabilities, with direct canonical knowledge discovery, a dedicated detail route, hierarchy-first exploration, and a durable build/update loop.

## 2. Audit findings

- The repository began this iteration clean on main.
- Backend baseline: 139 tests passed; Ruff lint and format passed.
- Frontend baseline: typecheck, lint, 31 tests, and production build passed.
- Frontend Prettier baseline failed on 24 existing files. The configured formatter was applied mechanically; the final whole-project format check passes.
- Prior course detail had two local tabs and defaulted to materials.
- Prior M3-E had a graph and synchronous course build, but no persisted course-level job status, reload recovery, bounded canonical browse, overview, hierarchy-first view, or independent detail page.
- Existing M2 material summary/cards/Q&A are single-material scoped and remain labelled that way.

## 3. Reused capabilities

- Existing course/material persistence, upload, parsing, and ownership.
- Existing material content, summary, study cards, and grounded single-material Q&A.
- M3-B extraction services and run history.
- M3-C canonicalization, candidate resolutions, node/source persistence, and idempotency.
- M3-D relationship generation, forest/DAG checks, relationship evidence, and current publication.
- Existing G6 lazy loader and graph adapter.

No M3-B/C/D prompt or inference algorithm was reimplemented in the frontend or new orchestration layer.

## 4. Main changes

### Backend

- Added course_knowledge_build_states, repository, migration, job service, heartbeat lease, material snapshots, checkpoint rollback, and stale-run recovery.
- Added asynchronous 202 build-job and durable status endpoints.
- Added bounded canonical-node browse/search.
- Added optional canonical-only filtering to the existing knowledge-model endpoint.
- Strengthened failed update restoration to preserve prior node fields and provenance, not only publication flags.

### Frontend

- Course default tab is now 学习概览; URL queries restore overview/materials/structure and tree/graph state.
- Added real status banner, three statistics, three permanent task cards, bounded search, empty/error/loading states, and full-list pagination.
- Added independent knowledge detail with concept, four relation directions, node sources, edge evidence, material links, and existing learning actions.
- Added a multi-root hierarchy view and retained the real relationship graph as the auxiliary mode.
- Added persisted polling, stale-request protection, and conservative model retention during updates.
- Material detail now honors tab/source query state and reloads safely on route-param changes.

### Demonstration assets

- Added two small linear-algebra text notes under docs/demo. They contain course content only and were uploaded through the same normal material API as user files.

## 5. API and migration

New endpoints:

- GET /api/courses/{course_id}/knowledge-nodes?q=&offset=&limit=
- GET /api/courses/{course_id}/knowledge-model/build-status
- POST /api/courses/{course_id}/knowledge-model/build-jobs (202)

Extended endpoint:

- GET /api/courses/{course_id}/knowledge-model?canonical_only=true

Existing synchronous POST /knowledge-model/build remains for compatibility.

Migration 0007_m3e_workspace_build_state adds only the durable per-course build state and cascades with course deletion. Fresh SQLite migration and 0006_m3d_relationships → head both passed.

## 6. Delivered product behavior

- Overview: real identity/status/counts, three functional task cards, direct canonical search/detail, pagination.
- Materials: existing upload/content/summary/cards/single-material Q&A preserved.
- Detail: canonical guard, concept, hierarchy vs prerequisite groups, node provenance, relationship evidence, safe material fallbacks.
- Structure: hierarchy default, multi-root/isolated handling, expand/search/locate, real graph, filters, zoom/drag/fit/reset, unified detail navigation.
- Build/update: user-triggered persisted job, real stages, duplicate protection, reload recovery, material-change detection, safe rollback.

No Student Model, mastery, diagnosis, recommendation, adaptive practice, tutor, or course-level RAG was added.

## 7. Verification results

| Check | Result |
|---|---|
| Backend pytest | PASS — 146/146 |
| Backend Ruff lint | PASS |
| Backend Ruff format | PASS — 105 files |
| Frontend Vitest | PASS — 62/62 |
| Frontend typecheck | PASS |
| Frontend ESLint | PASS |
| Frontend Prettier | PASS |
| Frontend production build | PASS |
| Fresh migration | PASS |
| M3-D → M3-E migration | PASS |
| Desktop browser | PASS |
| 375px browser | PASS — no horizontal document overflow |

The production build retains an existing non-blocking warning for the lazy G6 vendor chunk (about 1.42 MB before gzip). The graph is loaded only when needed.

## 8. Browser verification

Executed against the built SPA and isolated SQLite databases:

- Existing course: overview showed real counts; search narrowed to 特征值; clearing restored six deterministic rows; detail showed saved description, prerequisite, source, and relationship evidence; source link opened the material with an explicit 全文 fallback note.
- Structure: hierarchy was default with 13 real nodes; graph exposed relation legend, filters, four viewport controls, and a real graph-node click navigated to the unified detail route.
- Initial build: course creation, material upload, 202 job start, durable polling, and successful publication were observed.
- Update: a second parsed material changed status to 有新资料待更新; the update retained the 13-node/15-edge old model while running and completed at 24 nodes/31 edges.
- M2 regression: generated a summary, generated five study cards, and completed a grounded single-material question through real APIs in explicit mock mode.
- Responsive: at 375×812 the header, tabs, status, stats, cards, and knowledge content remained readable with document width below viewport width.

## 9. Real Provider verification

PASS. The environment reported configured provider credentials without exposing them. An isolated two-material course completed the real OpenAI-compatible/DeepSeek workflow:

- first build: 13 canonical nodes and 15 relations;
- update build: 24 canonical nodes, 8 CONTAINS, and 23 PREREQUISITE relations;
- final durable state: ready, needs_update=false.

No silent fallback to mock occurred. Provider operations were logged by operation/model/latency only; no key was printed.

## 10. Limitations and risks

- Exact PDF page navigation is only available if a future material viewer exposes such a contract; current links open the real material and display the stored reference.
- G6 remains a relatively large lazy chunk. It does not affect non-structure route loading, but further graph-specific code splitting can be considered later.
- Background execution is process-local but state/lease/checkpoint data is durable. A restart is recovered from persisted state; this competition-grade design intentionally does not introduce Celery/Redis.
- The deterministic mock build is intentionally sparse; it verifies workflow mechanics, not model quality.

## 11. Final status

COMPLETE

All P0/P1 workspace capabilities, migrations, automated checks, browser flows, and a controlled real-provider build/update were completed. Future Student Model and personalized learning work remains out of scope.
