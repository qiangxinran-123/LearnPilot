# M3-E Course Knowledge Workspace

## Scope

M3-E turns the M2 material tools and M3-A through M3-D course knowledge model into one course-scoped learning workspace. It adds discovery, navigation, visualization, and a durable user-triggered build/update workflow. It does not add student mastery, diagnosis, personalized recommendations, adaptive practice, or course-wide RAG.

## Product information architecture

The global navigation remains Dashboard, Course, Diagnose, Learn, and Progress. A course route contains three URL-restorable local tabs:

1. 学习概览 (default)
2. 课程资料
3. 知识结构

The independent `/courses/:courseId/knowledge/:nodeId` route is the only knowledge-detail experience. It is reached directly from the overview or detail relations, and explicitly from the unified map preview. The detail page returns to the map with the current `nodeId` preserved.

## Core user flows

- New course: create course → upload parsed material → start knowledge build → observe persisted stage → browse the published model.
- Daily learning: open course → search a canonical concept → read its description, relations, provenance, and related material.
- Structure exploration: open the unified map → expand/search the CONTAINS navigator → focus a node → follow its direct PREREQUISITE neighbors without leaving the map → open full detail when needed.
- Material study: enter the material tab or a provenance link → use existing M2 content, summary, cards, and single-material Q&A.
- Update: upload changed/new material → see 有新资料待更新 → explicitly start update → keep the old model available until successful publication.

## Page and component architecture

- CourseDetailView owns course/material loading, URL tabs, and the single course knowledge workspace composable.
- CourseOverview renders build state, three real statistics, three permanent task cards, and bounded canonical search/browse.
- KnowledgeStructurePanel owns the unified `focusNodeId`, URL synchronization, left knowledge navigator, direct-dependency focus view, and compact preview.
- KnowledgeFocusGraph renders one-hop PREREQUISITE predecessors/current/successors as accessible controls; clicking a related node changes focus rather than navigating away.
- KnowledgeDetailView loads a course-scoped canonical model, node detail, materials, relationship evidence, and guards stale requests.
- useCourseKnowledgeWorkspace is the only frontend owner of build-status polling and canonical model refresh.
- treeAdapter remains the pure CONTAINS forest boundary. knowledgeMapAdapter is the pure canonical index, deterministic default-focus, parent-topic, and direct PREREQUISITE boundary. The legacy graphAdapter/G6 component is retained for the later E.1-D/E visual work but is no longer mounted by the unified map.

The existing material-detail page remains the M2 learning surface. Query parameters select content, summary, cards, or QA; a provenance link carries a bounded source reference and explicitly degrades when exact page navigation is unavailable.

## Course overview data sources

| UI data              | Source                                                       |
| -------------------- | ------------------------------------------------------------ |
| Course identity      | existing course API                                          |
| Material count       | existing course material list                                |
| Canonical node count | durable build status                                         |
| Valid relation count | durable build status (contains + prerequisite)               |
| Search/list          | bounded canonical-node browse API                            |
| Build/update label   | persisted build state plus current material-content snapshot |

No count is derived from frontend filtering. Knowledge candidates are never included in overview, tree, or graph counts.

## Canonical knowledge adapter

GET '/api/courses/{course_id}/knowledge-nodes' resolves nodes through the current successful canonicalization run, enforces ownership, accepts a bounded query, and paginates with a maximum of 100 rows. GET '/knowledge-model?canonical_only=true' returns only those node IDs and edges whose endpoints are both in that set. Existing unfiltered M3-A behavior remains the default for backwards compatibility.

## Relations and provenance

CONTAINS is directional parent → child and is used only for hierarchy. PREREQUISITE is directional prerequisite → dependent and is used only for learning dependency. Node sources and relationship evidence remain visually separate:

- material evidence may show a material title, stored reference, and stored excerpt;
- model-inference/structural evidence is explicitly labelled as non-source-text reasoning;
- inaccessible/deleted materials are shown as unavailable, with no fabricated link or location.

All detail requests validate the route course, node course, canonical membership, edge endpoints, and material ownership.

### M3-E.1-A knowledge-detail presentation

The detail route keeps the same course-scoped API contract and relation semantics while presenting them in a student-first order:

1. saved concept description;
2. direct PREREQUISITE predecessors and successors;
3. direct CONTAINS parent and children;
4. compact source material/location rows;
5. existing material learning actions.

User-facing labels describe learning context without changing the domain model. `PREREQUISITE source -> target` appears as “学习前可以先了解” when the current node is the target and “接下来还可以看看” when it is the source. `CONTAINS source -> target` appears as “属于哪个主题？” for the target and “这个主题包含什么？” for the source. Empty relation categories are omitted; when all categories are empty the page states only that no connections have been established.

KnowledgeSource excerpts and KnowledgeEdgeEvidence are independently disclosed and collapsed by default. Source rows are grouped by stable `material_id`, never by title, so two materials with the same title remain distinct while multiple positions in one material remain visible. A source row exposes only the real material name, type, stored reference, and valid navigation by default. Disclosure state is component-local, is never persisted to the domain model, and resets on every course/node route change. Long source excerpts remain complete but use a bounded scroll region when expanded.

## Unified knowledge map transformations

adaptKnowledgeModelToTree consumes canonical nodes and real CONTAINS edges only. It produces a deterministic multi-root forest, retains isolated nodes, and rejects stale endpoints, self edges, a second parent, cross-course edges, and cycles. Search keeps matching nodes, their ancestors, and matched subtrees visible and returns expansion IDs.

adaptKnowledgeModelToFocus consumes the same canonical model but accepts only valid PREREQUISITE edges. Because the persisted contract is `source = prerequisite` and `target = dependent`, incoming sources are shown as “学习前可以先了解” and outgoing targets as “接下来还可以看看”. Only direct one-hop neighbors are included. More than five neighbors are initially condensed behind explicit expand controls; the complete set remains available and is never silently discarded.

The map uses one parent-owned `focusNodeId`. The navigator, focus view, and preview all derive from it. A valid `nodeId` query restores the focus; an absent or cross-course/stale ID falls back deterministically to the first valid root, then the first stable canonical node. Internal focus changes use router replacement to avoid filling browser history. The detail route is a deliberate navigation and returns with the same node context.

## Durable build and update model

The course_knowledge_build_states table stores one atomic claim per course:

- monotonically increasing job ID;
- status/stage and heartbeat lease;
- requested and last-successful material snapshot hashes;
- timestamps and safe error contract;
- a temporary checkpoint of published node content/provenance used only for rollback.

The 202 API registers a background build that opens an independent database session and reuses the existing M3-B extraction, M3-C canonicalization, and M3-D relationship services. Repeated requests reuse the running or already-current job. Stage callbacks update the durable lease. Failure or stale-job recovery restores the prior canonical publication, node descriptions, active flags, and sources. Successful publication records the exact material-content snapshot.

The frontend polls durable status, so reload/navigation does not erase task state. No percentage is displayed because the provider exposes no defensible percentage progress.

## State model

| State            | Meaning                                                  |
| ---------------- | -------------------------------------------------------- |
| no_materials     | no course material exists                                |
| not_ready        | material exists but none has parsed content              |
| not_built        | ready material exists without a complete published model |
| running          | persisted job claim with a real stage                    |
| ready            | canonical nodes plus a current relationship publication  |
| update_available | published model exists and material evidence changed     |
| failed           | initial build failed; no published model                 |
| update_failed    | update failed; previous model remains available          |

For pre-M3-E databases without a successful snapshot, current extraction runs tied to current material content provide the compatibility baseline; newly added ready materials cause update_available.

## Course Model versus Student Model

Everything in this workspace describes what the course contains and how its concepts relate. Importance and difficulty are course metadata. There is no mastery score, student status, learned flag, confidence, completion percentage, personalized ordering, or recommendation. Those remain explicit future Student Model responsibilities.

## Accessibility and responsive behavior

Task cards and knowledge links are semantic buttons/links with focus states. Navigator node names are native buttons, while expand controls remain independent. Search fields have labels; build/error/loading states use text and live regions; relation meaning is not color-only. The workspace collapses to one column without horizontal overflow at 375px, and the direct relation sequence remains readable without relying on canvas or hover.
