# M3-E.1-A Knowledge Detail UX Report

## 1. Goal and actual scope

M3-E.1-A refines only the independent knowledge-detail experience. It makes provenance concise by default, separates node-source evidence from relationship evidence, and replaces technical relationship labels with student-facing language while preserving course isolation, evidence fidelity, direct node navigation, and all M2/M3-E learning actions.

No course form/card work, unified knowledge map, graph redesign, graph interaction changes, Student Model, diagnosis, recommendation, Tutor, adaptive practice, course-level RAG, or new knowledge inference was implemented.

## 2. Audit findings

- `KnowledgeDetailView` already loaded the canonical model, node detail, course materials, and current relationship evidence in one guarded request cycle.
- Stale-response protection, course/node membership checks, inaccessible-material fallback, material navigation, and direct related-node routing were already reliable and were retained.
- The page previously rendered every source excerpt and every relationship-evidence reason/excerpt immediately.
- Four relation categories had equal visual weight and always rendered empty cards. Existing directions were correct: `CONTAINS parent -> child`; `PREREQUISITE prerequisite -> dependent`.
- Existing API fields are sufficient. No backend/API/database change is required.
- No reusable disclosure component was needed; the behavior is local to this one page and uses semantic buttons with explicit ARIA state.

## 3. UI structure changes

The reading order is now:

1. knowledge identity;
2. 认识这个知识点;
3. 和哪些知识有关？;
4. 知识出处;
5. 从课程资料继续.

Learning prerequisites and follow-on concepts are visually primary. Theme membership and contained concepts are lighter hierarchy rows. Empty individual categories are omitted, while a single truthful message appears when all relationship categories are empty.

## 4. Provenance presentation before and after

Before: every `KnowledgeSource.excerpt`, relationship reason, material excerpt, and evidence type appeared by default, allowing provenance to dominate the page.

After:

- the default source row shows the real material name/type and each stored source position;
- sources are grouped by stable material ID, preserving every location and keeping equal-titled materials separate;
- each source excerpt has an independent 查看依据/收起依据 control;
- relationship evidence has its own 知识关联依据 summary and independent disclosure;
- long source excerpts remain complete in a bounded, scrollable region;
- missing positions are omitted rather than fabricated;
- deleted/unavailable materials keep a truthful label and never produce a false link;
- route changes reset all disclosure state, preventing evidence from the previous node remaining visible.

No evidence record is modified or removed.

## 5. Relationship terminology and priority

| Domain meaning | Student-facing label |
|---|---|
| Incoming PREREQUISITE | 学习前可以先了解 |
| Outgoing PREREQUISITE | 接下来还可以看看 |
| Incoming CONTAINS | 属于哪个主题？ |
| Outgoing CONTAINS | 这个主题包含什么？ |

These labels do not imply personalization or mastery. Related nodes still navigate directly to the same independent detail route.

## 6. Modified files

- `frontend/src/views/KnowledgeDetailView.vue`
- `frontend/src/tests/knowledge-detail.spec.ts`
- `docs/architecture/M3E_KNOWLEDGE_WORKSPACE.md`
- `docs/migration/M3E1A_KNOWLEDGE_DETAIL_UX_REPORT.md`

## 7. API and database changes

None. Existing `KnowledgeNodeDetailResponse`, `KnowledgeSource`, `KnowledgeEdge`, and `KnowledgeEdgeEvidence` contracts are reused unchanged. No Alembic migration, backend service, prompt, provider, or stored course data was changed.

## 8. Automated verification

Commands were executed with the configured project Python environment and the bundled Node runtime from a temporary mapped project drive, avoiding deletion or reinstall of the existing Linux dependency tree.

| Check | Actual result |
|---|---|
| Focused knowledge-detail Vitest | PASS — 8/8 |
| Full frontend Vitest | PASS — 65/65 |
| `vue-tsc --noEmit` | PASS |
| ESLint (`.ts`, `.vue`, zero warnings) | PASS |
| Prettier full frontend check | PASS |
| Vite production build | PASS |
| Backend `.venv/bin/python -m pytest` | PASS — 146/146 |

The build retains the already documented non-blocking lazy G6 vendor chunk warning. M3-E.1-A adds no dependency and does not change graph loading.

## 9. Browser verification

PASS against the built SPA and existing isolated real-course database:

- desktop default view showed the concept, student-facing relation labels, compact source name/location, and both evidence disclosures collapsed;
- Enter on the source disclosure expanded the authentic node excerpt; the same control collapsed it;
- the separate relationship disclosure expanded only relationship evidence and retained the “non-source-text” labels;
- clicking 矩阵乘法 navigated directly from 特征值 to its independent detail route;
- browser Back and full Refresh reloaded the correct node with all disclosures collapsed;
- 375×812 layout had `innerWidth=375`, document width 360, readable relation/source sections, no horizontal overflow, and non-wrapping disclosure labels;
- inaccessible evidence, missing relationships, missing locations, multi-material sources, and same-material multiple positions are covered by component tests.

No paid provider call was made because this stage changes presentation only.

## 10. Known issues and incomplete items

- Exact PDF-page navigation still depends on a future material-viewer contract; the existing truthful material-page fallback remains.
- Expanded whole-document source excerpts can be long, so the UI bounds them in a scrollable evidence region rather than truncating or altering evidence.
- The existing lazy G6 chunk-size warning remains unrelated and unchanged.

There are no incomplete M3-E.1-A acceptance items.

## 11. E.1-B through E.1-E boundary

Course creation/cards, unified map, graph visual redesign, and graph wheel/focus interaction remain untouched. E.1-B may independently review course creation and card interaction after this stage is accepted.

## 12. Final decision

**COMPLETE**

The knowledge detail is materially easier to scan while preserving complete provenance, strict relationship direction, course isolation, direct navigation, and existing learning functions.
