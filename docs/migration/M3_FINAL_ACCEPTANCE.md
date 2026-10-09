# LearnPilot V1 — M3 Final Acceptance

## 1. Purpose and acceptance boundary

M3 establishes the **Course Knowledge Model**: the course-scoped concepts that
need to be learned, their validated source provenance, and the directed
relationships between them. It is deliberately not a Student Model.

The implemented M3 pipeline is:

```text
M2 MaterialContent + parser segments
  -> M3-B material-scoped KnowledgeCandidate + candidate evidence
  -> M3-C canonical KnowledgeNode + KnowledgeSource
  -> M3-D CONTAINS / PREREQUISITE + KnowledgeEdgeEvidence
  -> M3-E course-local inspection and visualization
```

The pipeline remains relational: SQLite and SQLAlchemy persist the model, and
the frontend reads it through typed HTTP contracts. No graph database,
embedding store, vector database, or separate graph service is part of M3.

This report consolidates the implemented architecture and the stage-level
acceptance evidence recorded in the M3-A through M3-D reports. Final
validation observed for this milestone includes fresh and M2-to-head Alembic
upgrades, the backend suite, Ruff checks, the frontend quality gate, and a
real-provider browser E2E run. Exact evidence is recorded below without
exposing credentials or user material.

## 2. M3-A — Knowledge Model Foundation

M3-A introduced the course-scoped persistence and service boundary:

- `KnowledgeNode` stores only course concepts: display and normalized names,
  description, constrained importance and difficulty, and timestamps.
- `KnowledgeEdge` stores directed `CONTAINS` and `PREREQUISITE` relations.
  `source -> CONTAINS -> target` means parent/broader concept to direct child;
  `source -> PREREQUISITE -> target` means required prior knowledge to
  dependent knowledge.
- `KnowledgeSource` links a node to same-course `Material` and an existing M2
  segment reference plus a bounded supporting excerpt.

The `0003_m3a_knowledge_model` migration added real foreign keys, composite
course-context constraints, self-edge protection, duplicate-edge/source
uniqueness, and cascades. Dedicated repositories and
`KnowledgeModelService` enforce bootstrap-owner access, course isolation,
node/edge/source integrity, and stable domain errors. The read surface is
`GET /api/courses/{course_id}/knowledge-model` and
`GET /api/courses/{course_id}/knowledge-nodes/{node_id}`.

The M3-A implementation report records fresh and upgrade migration checks,
15/15 dedicated SQLite tests, and a 93/93 historical backend regression at
that stage. These are stage evidence, not a substitute for the final suite.

## 3. M3-B — AI knowledge extraction

M3-B added the material-scoped staging layer without prematurely creating
canonical nodes:

```text
MaterialContent
  -> KnowledgeExtractionRun
  -> KnowledgeCandidate
  -> KnowledgeCandidateSource
```

`0004_m3b_knowledge_extraction` adds run lifecycle records, candidates, and
candidate source evidence. Extraction uses the versioned
`knowledge_extraction_v1` structured prompt, bounded source-aware batches,
Pydantic output validation, exact batch-reference checks, source-derived
excerpts, idempotency, and failure-safe current-run publication.

An extraction result is deliberately not a `KnowledgeNode`. It neither
semantically merges concepts across materials nor infers hierarchy or
prerequisites. M3-B's historical report records a provider-mode smoke with
the configured OpenAI-compatible DeepSeek service and `deepseek-flash`, with
five source-backed candidates from self-authored material. No secret,
provider endpoint, authorization header, or complete material was recorded.

## 4. M3-C — normalization, deduplication, and canonicalization

M3-C turns current successful candidates into a stable canonical node model.
`0005_m3c_canonicalization` adds canonicalization runs, candidate-to-node
resolutions, lifecycle flags for canonicalization-managed nodes, and
course-context constraints.

The processing order is intentionally conservative:

1. deterministic Unicode/whitespace/case/dash normalization;
2. exact grouping with no provider call when all identities are exact;
3. bounded lexical blocking of possible semantic matches;
4. structured provider identity judgement only inside those bounded groups;
5. atomic node/source/resolution publication after revalidating the snapshot.

False merges are treated as more harmful than false splits. The canonical
model preserves candidate lineage and carries forward the original material,
source reference, and bounded excerpt into `KnowledgeSource`; it does not ask
the model to invent citations or rewrite evidence. M3-C adds no edges.

The stage report records 15/15 dedicated integration tests and a 125/125
historical backend regression, plus a DeepSeek provider smoke across two
self-authored materials. Its documented result retained cross-material
evidence while keeping a related but distinct concept separate.

## 5. M3-D — hierarchy and prerequisite modelling

M3-D adds the explicit course-structure layer through
`0006_m3d_relationships`:

- `KnowledgeRelationshipRun` stores a current, source-snapshot-bound,
  versioned relationship inference attempt.
- `KnowledgeEdgeEvidence` stores a bounded model rationale and, when present,
  only validated material evidence attached to an endpoint.
- generated `KnowledgeEdge` rows reference the relationship run while manual
  or fixture edges remain distinguishable.

`CONTAINS` is validated as an acyclic forest: multiple real roots are allowed,
each target has at most one direct parent, and no artificial course root is
introduced. `PREREQUISITE` is independently validated as a directed acyclic
graph. Neither relation type is derived from the other.

The relationship prompt is versioned as `knowledge_relationships_v1`. Input
is the active canonical node/source snapshot; output is rejected on unknown
nodes, duplicate/self edges, cycles, invalid citations, or fabricated
material evidence. Relationship generation is idempotent by snapshot,
prompt, and model, and a failed regeneration retains the prior published
model.

The M3-D report records real SQLite test coverage for forest/DAG validation,
provenance, ownership, idempotency, failure preservation, and cascades, plus
a bounded provider-mode DeepSeek smoke using self-authored concepts. It did
not add a graph UI, learner state, or recommendation logic.

## 6. M3-E — course knowledge structure visualization

M3-E makes the persisted course model inspectable within the existing Course
Detail route. It does not create a top-level graph product, change the M3-B
through M3-D algorithms, or persist presentation state.

### Product surface

```text
/courses/:courseId
  |- 课程资料
  `- 课程知识结构
       |- overview, legend, and local relation filters
       |- interactive graph canvas
       |- node source-provenance drawer
       `- edge rationale/evidence drawer
```

`@antv/g6` 5.1.1 is the sole graph-rendering dependency. It is dynamically
loaded only when the course-local structure tab is opened, and its vendor code
is split from the initial Course Detail bundle. The library-neutral graph
adapter accepts only real backend nodes and valid relation endpoints; it adds
no synthetic course/domain/category node and never writes UI coordinates back
to the domain model.

### Graph semantics and interaction

- The deterministic layout uses only `CONTAINS` edges. Real multiple roots
  and disconnected concepts remain separate top-level components.
- `CONTAINS` is a solid directed parent-to-child line and establishes
  hierarchy depth.
- `PREREQUISITE` is a visually distinct dashed directed overlay from required
  prior knowledge to dependent knowledge. It never changes hierarchy layout.
- Users can pan, zoom, fit, reset, and locally filter either relation type.
- Node selection fetches the existing node-detail contract and displays
  name, description, importance, difficulty, material title, source reference,
  and bounded excerpt.
- Edge selection displays the actual directed semantics and current
  relationship evidence. It clearly distinguishes a stored model/structural
  rationale from a validated material citation and never fabricates one.

The UI has truthful loading, empty, disabled-build, build-progress, and
recoverable error states. It is responsive through graph resize/fit handling
and wrapping controls, while its accessible labels and text summary ensure the
canvas does not conceal the underlying course-model meaning.

### Thin build orchestration

`POST /api/courses/{course_id}/knowledge-model/build` is a course-level
orchestration boundary, not a fourth inference algorithm. It validates
ownership and successfully parsed same-course material, then invokes the
existing M3-B extraction, M3-C canonicalization, and M3-D relationship
services with their established idempotency behavior. Its response contains
only course/material/node/edge counts and whether all stages were reused.

If a newly published canonical result cannot obtain a valid relationship
result, the service restores the previous active canonical publication state.
The frontend likewise retains a visible, already valid model if an update
fails. M3-E has no new database migration because it adds no new persisted
domain concept.

## 7. Provenance, isolation, and data ownership

M3 keeps traceability as a first-class property:

```text
visible KnowledgeNode
  -> KnowledgeSource
  -> same-course Material
  -> MaterialContent source_reference + bounded excerpt

visible KnowledgeEdge
  -> KnowledgeEdgeEvidence
  -> optional validated material evidence or stored rationale
```

Every layer is course-scoped and guarded by the existing bootstrap-user
ownership context. Database composite foreign keys, service validation, and
API resource scoping together prevent cross-course nodes, material sources,
and edge endpoints. Deleting a node removes its sources and incident edges;
deleting a material removes its sources but intentionally leaves possibly
shared concepts; deleting a course cascades the complete course knowledge
model.

## 8. Real-provider and browser E2E evidence

The M3-B, M3-C, and M3-D stage reports each record bounded provider-mode
verification against the configured OpenAI-compatible DeepSeek adapter and
the `deepseek-flash` model, using self-authored disposable material. Their
reports record structured, source-validated results without exposing a
credential, endpoint, authorization header, or complete source document.

The M3-E final E2E acceptance flow was intentionally narrower than an
unbounded production crawl:

```text
create course
  -> upload/parse self-authored material
  -> build through POST /knowledge-model/build
  -> read GET /knowledge-model
  -> inspect a node source and edge evidence
  -> verify pan/zoom/filter/drawer behavior at 1440, 1280, and 1024 px
```

The observed real-provider E2E used two self-authored TXT materials in an
isolated course. The thin build endpoint produced a course model with
12 nodes, 3 `CONTAINS` edges, and 13 `PREREQUISITE` edges. The browser run
opened a node drawer with stored source provenance and an edge drawer with
stored relation evidence, then exercised pan, zoom, fit/reset, and relation
filters. The knowledge structure remained usable at 1440 px, 1280 px, and
1024 px widths.

Final quality evidence for the milestone:

- fresh SQLite `alembic upgrade head`: **PASS**;
- populated M2-schema database upgrade to current head: **PASS**;
- backend `pytest`: **139/139 passed** in 102.18 seconds;
- `ruff check backend` and `ruff format --check backend`: **PASS**;
- final frontend quality gate: **PASS** (the exact aggregate count is omitted
  here because the final audit included late focused-test changes).

## 9. Explicit M3 exclusions

M3 intentionally does not add:

- a Student Model, mastery score, confidence, progress, completion state,
  learner evidence, diagnostic assessment, or recommendation;
- learning paths, adaptive practice, AI tutor, agents, or multi-agent logic;
- graph editing, persisted visual coordinates, synthetic topic roots, or a
  graph database;
- embeddings, vector search, semantic edge deduplication, or an unbounded
  graph traversal engine;
- a new parser/provenance system, hidden mock fallback, or a background queue.

These omissions preserve the distinction between a stable course structure
and later learner-specific product behavior.

## 10. Known limitations

- Provider judgements remain bounded, source-validated proposals rather than
  a claim of complete curricular truth.
- Canonicalization favors safe false splits over unsafe false merges.
- Relationship generation favors sparse direct edges and may legitimately
  return multiple roots or no relation for related concepts.
- Build orchestration is synchronous for the competition version; it exposes
  accurate loading/failure states rather than simulating background progress.
- The graph is an inspection surface, not an editing environment. Full
  keyboard graph traversal and a mobile-specific visualization remain future
  enhancement areas.

None of these limitations introduces student-state fields into the Course
Knowledge Model or weakens source provenance requirements.

## 11. M4 entry boundary

M4 may introduce learner-specific evidence and state only in a separate
Student Model keyed to the learner and the existing course knowledge identity.
It must not add `mastery`, confidence, progress, learned state, recommendation,
or UI layout fields to `KnowledgeNode`, `KnowledgeEdge`, `KnowledgeSource`,
or the M3 graph API contracts.

Any M4 feature should consume the stable M3 node identity, course isolation,
directed relation semantics, and provenance without changing the meaning of
the course model. Assessment, learning paths, recommendations, and adaptive
experiences therefore remain a subsequent, explicitly approved scope.

## 12. Supporting records

- `docs/architecture/M3A_KNOWLEDGE_MODEL_FOUNDATION.md`
- `docs/architecture/M3B_AI_KNOWLEDGE_EXTRACTION.md`
- `docs/architecture/M3C_KNOWLEDGE_CANONICALIZATION.md`
- `docs/architecture/M3D_KNOWLEDGE_RELATIONSHIPS.md`
- `docs/architecture/M3E_KNOWLEDGE_STRUCTURE_FRONTEND.md`
- `docs/migration/M3A_IMPLEMENTATION_REPORT.md`
- `docs/migration/M3B_IMPLEMENTATION_REPORT.md`
- `docs/migration/M3C_IMPLEMENTATION_REPORT.md`
- `docs/migration/M3D_IMPLEMENTATION_REPORT.md`
- `docs/migration/M3E_IMPLEMENTATION_REPORT.md`

The M3-E implementation report and final terminal report should be read
alongside this consolidation for the detailed command-level acceptance record.
