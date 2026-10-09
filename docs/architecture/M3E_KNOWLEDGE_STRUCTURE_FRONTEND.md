# LearnPilot V1 — M3-E Course Knowledge Structure Frontend

## Scope

M3-E makes the persisted M3 course knowledge model inspectable in the existing Course Detail workspace. It adds a course-local knowledge-structure tab, a lazily loaded AntV G6 graph, node and edge inspection drawers, provenance presentation, local relationship filters, and a deliberately thin build entry point.

M3-E consumes the canonical `KnowledgeNode`, active `KnowledgeEdge`, `KnowledgeSource`, and current relationship evidence produced by M3-A through M3-D. It does not alter extraction, canonicalization, relationship inference, relation semantics, or current-run visibility rules.

It introduces no Student Model, mastery, learner progress, recommendation, learning path, assessment, graph editing, presentation-coordinate persistence, graph database, embedding, vector store, or additional LLM algorithm.

## Product Information Architecture

The feature belongs inside the existing course route rather than a new global graph product:

```text
/courses/:courseId
  ├── 课程资料
  └── 课程知识结构
        ├── overview / relation filters / legend
        ├── graph canvas
        ├── node-detail drawer
        └── edge-detail drawer
```

`CourseDetailView` resets course-local data and the active tab when the route course ID changes. `KnowledgeStructurePanel` is itself lazily imported, and the graph implementation is loaded only after the user opens the knowledge-structure tab. This keeps the normal course-material workflow and initial course workspace free of graph runtime work.

## Graph Library Decision

M3-E uses `@antv/g6` version `5.1.1` as the one graph-rendering library. G6 provides the real graph canvas, pan/zoom behavior, resize handling, and node/edge click events; it is not a static mockup or a hand-drawn DOM substitute.

The G6 module is dynamically imported through `g6Loader.ts` for `KnowledgeGraph.vue`. Vite additionally places AntV modules in the `knowledge-graph-vendor` manual chunk, so the visualization vendor payload is not part of the initial Course Detail bundle. The graph adapter remains library-neutral so API/domain contracts do not depend on G6 types.

## Backend API Mapping

The frontend uses the shared HTTP client and typed local contracts only:

| UI responsibility | API | Use |
|---|---|---|
| Load graph nodes and currently visible edges | `GET /api/courses/{course_id}/knowledge-model` | Authoritative graph model: `course_id`, nodes, edges |
| Load selected node provenance and related edges | `GET /api/courses/{course_id}/knowledge-nodes/{node_id}` | Drawer detail and `KnowledgeSource` records |
| Load active relationship evidence when available | `GET /api/courses/{course_id}/knowledge-relationships` | Edge evidence grouped by edge ID |
| Build or update the course model | `POST /api/courses/{course_id}/knowledge-model/build` | Thin orchestration response with material/node/edge counts and `reused` |

The relationship read may return `KNOWLEDGE_RELATIONSHIP_NOT_READY` while a canonical node model is still valid. That condition does not erase or invalidate a usable node-only graph; it simply leaves the edge-evidence map empty.

The typed frontend model deliberately contains no mastery, confidence, learner status, progress, recommendation, or graph coordinate field.

## Graph Adapter

`graphAdapter.ts` converts the API response into a small local rendering shape:

- real backend node and edge IDs are wrapped in deterministic graph IDs;
- only known relation types and endpoints present in the loaded node set are rendered;
- malformed self edges and unknown endpoints/types are ignored defensively rather than corrupting the canvas;
- G6-specific runtime types do not leak into domain models or HTTP contracts;
- nodes retain their actual course-model identity and are never replaced by synthetic category, course, or topic nodes.

The adapter does not infer, deduplicate, create, or delete course knowledge. It is a view transformation only.

## Hierarchy Layout

The stable layout is derived exclusively from `CONTAINS` edges. Nodes are sorted by persistent ID, arranged by depth, and sibling positions are derived from the positions of their real children. This makes equivalent API responses render consistently without persisting presentation coordinates.

`PREREQUISITE` is intentionally excluded from layout calculation. A learning dependency must not move a concept out of its course hierarchy or be misrepresented as parentage.

The adapter has defensive rendering behavior for malformed manual data, but M3-D remains the authority that validates the generated `CONTAINS` forest and prerequisite DAG before persistence.

## Multiple Root Strategy

Multiple `CONTAINS` roots are valid M3-D course-model output. M3-E lays each real root out as its own top-level tree and preserves disconnected real nodes as independent roots when no containment edge exists.

It never creates a virtual “course”, “domain”, or “other concepts” root. This preserves the semantic distinction between an absent hierarchy relation and a real broader concept. A malformed all-cycle manual data set is displayed defensively as disconnected real nodes rather than being hidden or repaired by the UI.

## CONTAINS Visualization

`source -> CONTAINS -> target` is rendered as a solid, muted directed line. Its direction is explicit in the legend and detail drawer:

```text
parent / broader concept  ->  child / more specific concept
```

These edges establish layout depth. Their visual presence is independently toggleable, but the underlying deterministic placement remains based on the authoritative containment forest.

## PREREQUISITE Visualization

`source -> PREREQUISITE -> target` is rendered as a blue dashed directed overlay:

```text
required prior knowledge  ->  dependent knowledge
```

It is visually distinct from containment, has its own filter, and does not change hierarchy layout. The edge-detail drawer states the same directed learning meaning in user-facing language. The frontend never infers a prerequisite relation from proximity, hierarchy, or a shared source.

## Node Detail

Clicking a rendered node calls the node-detail API and opens a right-side drawer. The drawer shows only course-model information:

- display name and concise description;
- constrained importance and difficulty labels;
- source count and the backing course material title;
- source reference and a bounded excerpt with an explicit expand/collapse control.

The drawer intentionally does not show raw database identifiers, candidate staging records, learner state, mastery, confidence, completion, or recommendation data.

## Edge Detail

Clicking an edge opens a dedicated relation drawer. It resolves both endpoint names from the current model and states the relation semantics in the direction that is actually stored.

When active relationship evidence exists, the drawer shows its short reason plus any validated material title, source reference, and bounded excerpt. `model_inference` and `structural` evidence are labelled as such; the UI does not invent a material citation where none exists. When evidence is absent, it plainly says that no displayable rationale is recorded.

## Provenance UX

M3 provenance remains traceable end-to-end:

```text
KnowledgeNode
  -> KnowledgeSource
  -> same-course Material
  -> MaterialContent source_reference / excerpt

KnowledgeEdge
  -> KnowledgeEdgeEvidence
  -> optional validated material source or model/structural rationale
```

The node drawer maps `material_id` to the already loaded course-material title. Source references and excerpts are shown as stored; the frontend does not fabricate page labels, quotation text, or evidence links. Edge evidence is fetched only from the active relationship run exposed by M3-D.

## Build / Update Flow

The build control is enabled only when at least one listed material reports the current `SUCCESS` or retained M2 `EXTRACTED` parsed status. It calls `POST /knowledge-model/build` with a bounded frontend timeout and then reloads the same course model.

The backend `CourseKnowledgeBuildService` is an orchestration boundary, not a new knowledge algorithm:

```text
ready, owned material(s)
  -> existing M3-B extraction service (idempotent)
  -> existing M3-C canonicalization service (idempotent)
  -> existing M3-D relationship service (idempotent)
  -> typed counts/reuse response
```

It validates bootstrap-owner course access and parsed same-course material content before work begins. It reuses existing stage idempotency with `regenerate=False`; it does not add a new prompt, model call format, extraction rule, deduplication policy, hierarchy inference, or prerequisite inference.

When the relationship stage fails after a new canonical result would otherwise be published, the orchestration service restores the previous active canonical run and managed-node activation state. The frontend preserves an already displayed model on update failure and reports that the current result remains available.

## Loading / Error / Empty State

The panel exposes separate truthful states:

- an initial skeleton while the knowledge model loads;
- a recoverable error result when the first model request fails;
- an empty state stating that no course knowledge structure has been built yet;
- a disabled build control with an explanation when there is no successfully parsed material;
- an in-progress build label without staged LLM-pipeline theatrics;
- a non-destructive update error that retains the current visible graph.

Relationship-read unavailability is handled as an evidence limitation, not as a false graph failure. A G6 runtime loading/render failure has a visible fallback message and does not make unsupported claims about a graph that was not rendered.

## Responsive Strategy

The graph canvas uses a bounded fluid height, a `ResizeObserver`, and G6 resize/fit behavior. The header, overview counters, legend, and relation switches wrap instead of forcing horizontal page layout. On narrow layouts the header actions become full-width and graph controls reduce spacing; the detail drawers cap their width at the viewport.

The visualization intentionally remains in the Course Detail content region at desktop and tablet widths. No separate mobile-only graph representation or persisted display layout is introduced in M3-E.

## Accessibility

The panel supplies labelled regions for the graph, graph controls, filters, legend, node provenance, and edge evidence. Controls use Element Plus buttons with visible tooltips and Chinese `aria-label` text. Build progress and recoverable errors use status/live-region semantics. Drawers present structured headings, descriptions, definition lists, and ordinary buttons for excerpt expansion.

The graph canvas is labelled with a count-based text summary. Pointer-based graph selection is supplemented by clear surrounding controls and drawers; full keyboard graph traversal is not represented as complete M3-E accessibility support and remains a future enhancement.

## Frontend Testing

Focused M3-E tests cover the view-model boundary rather than treating the graph library as the domain authority:

- `knowledge-graph-adapter.spec.ts` verifies multiple roots/no synthetic node, disconnected-node rendering, local relation filters, malformed-edge exclusion, and a deterministic 50-node/80-edge fixture;
- `knowledge-structure-panel.spec.ts` verifies truthful empty and initial-error states, build/reload behavior, M2 `EXTRACTED` compatibility, post-build refresh-failure preservation, node provenance presentation, and explicit `CONTAINS`/`PREREQUISITE` drawer semantics.

The repository-wide frontend typecheck, lint, Vitest, and production-build commands remain final quality gates. Dynamic G6 loading and vendor chunk splitting are validated by the production build rather than by a mocked unit-test import alone.

## Real Browser Verification

Real-browser validation used a real course with two parsed self-authored TXT materials and the configured provider through the thin build endpoint. The completed model contained 12 nodes, 3 `CONTAINS` edges, and 13 `PREREQUISITE` edges. The acceptance pass inspected persisted node-source provenance and prerequisite-edge evidence, exercised relation filtering, pan, zoom, fit, and reset, and visually checked the graph at 1440px, 1280px, and 1024px. All three widths remained legible without a clipped canvas.

## M3 Final Architecture

The completed M3 architecture has a strict course-model pipeline:

```text
M2 MaterialContent + segments
  -> M3-B candidate extraction + source evidence
  -> M3-C canonical KnowledgeNode + KnowledgeSource
  -> M3-D CONTAINS / PREREQUISITE + edge evidence
  -> M3-E course-local inspection and visualization
```

Every visible node and edge remains course-scoped, ownership-checked, current-run aware, and traceable to persisted source/evidence records. The frontend is a consumer of this model; it does not become a second source of knowledge truth.

## M4 Extension Boundary

M4 may add student-specific state only in a distinct Student Model. It must not add `mastery`, confidence, progress, learning state, or recommendation fields to `KnowledgeNode`, `KnowledgeEdge`, graph adapter data, or these M3 endpoints.

Potential future M4 work may compose M3 concepts with learner evidence, but it must preserve M3 node identity, course isolation, provenance, relation semantics, and the separation between course structure and learner state. Graph editing, adaptive paths, assessment, recommendation, and AI tutoring remain outside M3-E.
