# M3-E.1-C Unified Knowledge Map Implementation Report

## 1. Goal and delivered scope

M3-E.1-C replaces the user-facing hierarchy/relationship-graph mode switch with one course-scoped knowledge map. The delivered workspace combines a CONTAINS navigator, a direct PREREQUISITE focus view, one shared focus state, a compact knowledge preview, and an explicit full-detail route. It does not add student state, recommendations, new knowledge generation, E.1-D visual graph work, or E.1-E canvas interaction work.

Final status: **COMPLETE**.

## 2. Audit findings

- `KnowledgeStructurePanel` previously mounted two separate products: an Element Plus CONTAINS tree and a lazy G6 all-relations graph selected by a `view` query.
- `treeAdapter` already enforced canonical, same-course hierarchy semantics and handled multiple roots, isolated nodes, invalid endpoints, second parents, and cycles.
- `graphAdapter` and `KnowledgeGraph` mixed CONTAINS and PREREQUISITE for the former full-graph experience. They remain in the repository for the later visual/interaction stages, but the unified map no longer mounts them.
- The backend contract is `PREREQUISITE source_node_id = prerequisite` and `target_node_id = dependent`; incoming sources are therefore predecessors and outgoing targets are successors.
- `CourseDetailView` already owns the canonical knowledge model and persisted build status through `useCourseKnowledgeWorkspace`; no duplicate request layer was needed.
- `KnowledgeDetailView` already had one course-scoped detail route and E.1-A provenance presentation. Only the map-return context needed adapting.
- Existing canonical model responses are complete course models, not the bounded overview browse page, so the unified map does not present a first page as a complete course.

### Old to new responsibility mapping

| Previous responsibility                     | Unified-map responsibility                                  |
| ------------------------------------------- | ----------------------------------------------------------- |
| hierarchy mode in `KnowledgeStructurePanel` | always-visible `KnowledgeNavigator` region inside the panel |
| G6 relationship mode                        | `KnowledgeFocusGraph` direct one-hop dependency view        |
| `view=hierarchy/graph` query                | one authoritative `nodeId` focus query                      |
| tree click opens detail                     | tree click changes map focus                                |
| graph click opens detail                    | graph neighbor click changes map focus                      |
| separate graph side detail                  | compact `KnowledgePreview` plus explicit full-detail link   |
| detail return to a structure mode           | detail return to map with the same `nodeId`                 |

## 3. Component and state flow

- `KnowledgeStructurePanel.vue` is the orchestration boundary. It receives the shared canonical model/build status and owns `focusNodeId`, search, URL reconciliation, navigator selection, focus data, and preview data.
- `knowledgeMapAdapter.ts` is a pure adapter for same-course canonical indexing, deterministic default focus, direct CONTAINS parents, and direct PREREQUISITE predecessors/successors.
- `KnowledgeFocusGraph.vue` is a DOM-based, keyboard-operable focus presentation. It renders predecessor → current → successor in three semantic regions, becoming a single vertical sequence at narrow widths.
- Left navigator labels are native buttons. The Element Plus expand control remains separate, so expanding a topic does not change focus.
- A focus change updates all three regions and performs `router.replace` with `nodeId`. Invalid or stale IDs safely fall back to a stable valid root and are normalized in the URL.
- Full detail remains an explicit RouterLink. `KnowledgeDetailView` exposes “在知识地图中查看” and preserves the current node in the return query.

## 4. Relation semantics and data integrity

- `CONTAINS source -> target` is used only for navigation and parent-topic preview.
- `PREREQUISITE source -> target` is used only for the direct learning sequence.
- Only edges whose course and both endpoints match the current canonical node index are rendered.
- Self edges, dangling endpoints, cross-course entries, and wrong relation types are filtered by the pure adapters and reported as ignored relation IDs where applicable.
- Duplicate names remain separate because IDs are authoritative.
- The focus view includes only one-hop direct neighbors. The default visual limit is five per side; explicit “show remaining” controls reveal the full list, so high-degree relationships are not silently dropped.
- No KnowledgeCandidate data, inferred frontend hierarchy, personalized ordering, or fabricated description is used.

## 5. URL and navigation behavior

- URL form: `/courses/:courseId?tab=knowledge-structure&nodeId=:nodeId`.
- Direct URL, refresh, and detail return restore the requested valid node.
- Invalid, deleted, or other-course node IDs fall back deterministically to the first valid root, then the stable first canonical node.
- Map-internal selections use history replacement; deliberate detail navigation uses a normal route push.
- Overview knowledge links and knowledge-detail relation links still navigate directly to the independent detail page. Only map navigator/focus nodes stay within the map.

## 6. Responsive and boundary behavior

- Desktop uses a bounded left navigator and a larger direct-relation/preview column.
- At approximately 375 px the workspace becomes one column, the relationship sequence becomes vertical, and the document has no horizontal overflow.
- Multiple roots, isolated nodes, no CONTAINS edges, no PREREQUISITE edges, dangling edges, invalid focus IDs, long names, and high-degree nodes have explicit tested behavior.
- Empty courses continue to use the existing build/empty state. No second build workflow was introduced.

## 7. Files changed for E.1-C

- `frontend/src/components/knowledge/KnowledgeStructurePanel.vue`
- `frontend/src/components/knowledge/KnowledgeFocusGraph.vue` (new)
- `frontend/src/components/knowledge/knowledgeMapAdapter.ts` (new)
- `frontend/src/views/KnowledgeDetailView.vue`
- `frontend/src/tests/knowledge-map-adapter.spec.ts` (new)
- `frontend/src/tests/knowledge-focus-graph.spec.ts` (new)
- `frontend/src/tests/knowledge-structure-panel.spec.ts`
- `frontend/src/tests/knowledge-detail.spec.ts`
- `docs/architecture/M3E_KNOWLEDGE_WORKSPACE.md`
- `docs/migration/M3E1C_UNIFIED_KNOWLEDGE_MAP_REPORT.md` (this report)

## 8. API and database changes

None. The implementation reuses the canonical-only course knowledge model, current build status, existing relationship direction, and existing knowledge-detail endpoints. No migration, model, prompt, provider, or build-job change was made for E.1-C.

## 9. Automated verification

Executed on 2026-10-13 in the repository's WSL/Linux Node environment to avoid Windows/WSL native dependency mixing.

| Check                               | Result                                                      |
| ----------------------------------- | ----------------------------------------------------------- |
| Focused map/detail Vitest           | PASS — 26/26                                                |
| Full frontend Vitest                | PASS — 82/82 in 15 files                                    |
| Vue TypeScript (`vue-tsc --noEmit`) | PASS                                                        |
| ESLint (`--max-warnings=0`)         | PASS                                                        |
| Prettier check                      | PASS                                                        |
| Vite production build               | PASS — 1,744 modules transformed                            |
| Full backend pytest                 | PASS — 146/146                                              |
| Ruff check                          | PASS                                                        |
| Ruff format check                   | PASS — 105 files already formatted                          |
| `git diff --check`                  | PASS                                                        |
| Secret/runtime-file scan            | PASS — no secret or runtime artifact entered the change set |

The production build retains the pre-existing main-chunk size warning. E.1-C removes G6 from the mounted knowledge-map path rather than adding a new graph dependency; dependency/chunk redesign remains outside this stage.

## 10. Real browser verification

Status: **PASS** using the real in-app browser against an isolated `/tmp` SQLite database and upload directory.

- Created an isolated course and material, then executed the real persisted course-build job in explicit mock-provider mode.
- Because the deterministic mock intentionally produced only one canonical node, the isolated database was supplemented with constraint-valid canonical nodes plus real CONTAINS/PREREQUISITE records solely to cover relationship interaction. No source file or user database was modified, and no result was presented as paid-provider output.
- Verified the unified map has no hierarchy/graph mode switch.
- Verified left navigation click, search, clear, and Enter-key focus.
- Verified two consecutive central-neighbor focus changes without leaving the map.
- Verified URL focus update, direct URL loading, refresh behavior, and invalid `nodeId` fallback.
- Verified explicit full-detail navigation and “在知识地图中查看” return to the same node.
- Verified the E.1-A headings and provenance page still render.
- Verified desktop layout and 375×812 responsive layout. At 375 px, `scrollWidth` equaled `clientWidth` and the relationship sequence remained readable.
- Browser validation exposed one stale `returnView` reference in a detail relation-link branch. It was removed, regression-tested, and the full flow was re-run successfully.

No paid DeepSeek call was made because E.1-C changes only presentation and focus navigation.

## 11. Known limitations and E.1-D/E boundary

- The central view intentionally uses a stable, accessible three-region focus layout instead of a canvas. Advanced node styling, layout animation, dense-graph visual optimization, and a full visual design system belong to E.1-D.
- Wheel behavior, zoom controls, canvas toolbars, and more advanced mobile graph gestures belong to E.1-E.
- The old G6 component and adapter remain available but are not user-facing in the unified map. They were not deleted because later D/E work may reuse parts of their lifecycle and data boundary.
- The Vite build still reports the established global main-chunk size warning; it is not caused by an E.1-C dependency addition.

## 12. Final conclusion

M3-E.1-C is **COMPLETE**. The course knowledge structure is now one coherent, URL-restorable, course-isolated exploration workspace. The implementation preserves M3-E build/update behavior, E.1-A knowledge detail, E.1-B course management, M2 material learning, and the Course Model versus Student Model boundary.
