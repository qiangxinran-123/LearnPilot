# LearnPilot V1 — M3-A Knowledge Model Foundation

## 1. Scope

M3-A establishes the relational backend foundation for a course knowledge model. It adds domain enums, SQLAlchemy entities, Alembic schema, Pydantic contracts, repositories, an integrity-focused service, two read APIs, real SQLite tests, and explicit provenance/cascade rules.

M3-A does not extract or generate knowledge. It makes no LLM request and adds no prompt, embedding, vector store, graph database, graph visualization, semantic deduplication, hierarchy inference, prerequisite inference, assessment, learner evidence, mastery, recommendation, Tutor, Agent, or frontend knowledge-map feature.

## 2. Domain definition

The M3-A aggregate is course-scoped:

~~~text
Course
  |-- N KnowledgeNode
  |       '-- N KnowledgeSource -- 1 Material
  '-- N KnowledgeEdge
          |-- source_node_id -> KnowledgeNode
          '-- target_node_id -> KnowledgeNode
~~~

SQLite and SQLAlchemy remain the persistence stack. KnowledgeNode plus directed KnowledgeEdge is sufficient for the competition version; no graph database is introduced.

## 3. Course Model vs Student Model

The Course Knowledge Model describes what the course contains and how its concepts relate. It is independent of any learner.

The Student Model will describe what a learner knows. It belongs to later milestones. M3-A therefore contains no mastery, confidence, progress, learned state, correct rate, recommendation, or student-specific status. It also persists no graph color, coordinate, icon, size, or UI state.

## 4. KnowledgeNode

KnowledgeNode fields are:

- id and course_id;
- display name and deterministic normalized_name;
- description;
- constrained importance: low, medium, or high;
- constrained difficulty: basic, intermediate, or advanced;
- created_at and updated_at.

Normalization is intentionally limited to whitespace trimming/collapse plus Unicode case folding. M3-A performs no synonym detection or semantic similarity. The repository exposes find_by_normalized_name for later M3-C work, but M3-A does not implement a deduplication policy.

## 5. KnowledgeEdge

KnowledgeEdge is directed and stores course_id, source_node_id, target_node_id, relation_type, and timestamps.

The schema rejects a self edge with a CHECK constraint. It rejects exact duplicates with a unique constraint over course_id, source_node_id, target_node_id, and relation_type. Composite foreign keys from the edge course/node pairs to KnowledgeNode enforce that both endpoints are in the declared course, while the service performs the same validation before persistence.

## 6. KnowledgeSource

KnowledgeSource links one KnowledgeNode to one Material and stores:

- knowledge_node_id;
- material_id;
- source_reference, up to 255 characters;
- an optional supporting excerpt, up to 1000 characters;
- created_at.

The combination of node, material, and source reference is unique. Foreign keys cascade on node or material deletion.

## 7. Relationship semantics

Relation types are explicit:

- contains: source is the parent concept and target is the child concept.
- prerequisite: source is required knowledge and target is the dependent knowledge.

M3-A persists these possible relation types but never generates either relation. Graph traversal and prerequisite reasoning are outside this milestone.

## 8. Provenance

Provenance is a first-class invariant. KnowledgeModelService accepts a source only when:

1. the caller owns the course through the existing bootstrap-user context;
2. the node belongs to that course;
3. the material exists and belongs to that same course;
4. the material has persisted MaterialContent;
5. source_reference exactly matches a reference in MaterialContent.segments.

This reuses M2 parser references such as PDF 第 12 页 and does not redesign parser provenance. Excerpts are bounded supporting context, never complete material content.

## 9. Delete/cascade policy

| Deletion | Result |
|---|---|
| Course | Its KnowledgeNode, KnowledgeEdge, KnowledgeSource, Material, and M2 artifacts are removed |
| KnowledgeNode | Its incoming/outgoing KnowledgeEdge rows and KnowledgeSource rows are removed |
| Material | Its KnowledgeSource rows and M2 artifacts are removed; KnowledgeNode rows remain |

An orphaned node is intentionally retained after its last source is deleted. Later knowledge-model rebuild behavior may decide how to handle it.

SQLite foreign keys are enabled by the application engine. Tests enable PRAGMA foreign_keys=ON explicitly and verify the real database cascades.

## 10. Repository architecture

The persistence boundary consists of:

- KnowledgeNodeRepository: create, get_by_id, list_by_course, update, delete, and find_by_normalized_name.
- KnowledgeEdgeRepository: create, list_by_course, list_for_node, delete, and exists.
- KnowledgeSourceRepository: create, list_for_node, delete_by_material, and exists.

Repositories only issue SQLAlchemy persistence operations. They contain no HTTP behavior, ownership policy, AI call, generation logic, or graph algorithm.

## 11. Service architecture

KnowledgeModelService coordinates transactions and enforces:

- bootstrap-user course ownership;
- node/course isolation;
- edge endpoint integrity;
- self-edge and duplicate-edge rejection;
- node/material course equality;
- exact M2 source-reference traceability;
- duplicate-source rejection.

Domain errors carry stable codes such as KNOWLEDGE_NODE_NOT_FOUND, KNOWLEDGE_EDGE_INVALID, KNOWLEDGE_SOURCE_INVALID, KNOWLEDGE_COURSE_MISMATCH, KNOWLEDGE_SELF_EDGE, and KNOWLEDGE_DUPLICATE_EDGE. SQLAlchemy exceptions are not returned to clients.

The service has no dependency on the M2 LLM adapter and makes no LLM request.

## 12. API contract

M3-A exposes read-only product APIs:

- GET /api/courses/{course_id}/knowledge-model
- GET /api/courses/{course_id}/knowledge-nodes/{node_id}

The first returns course_id, nodes, and edges. The second returns node, sources, and related_edges. Both validate ownership. A node outside the requested course is returned as not found so another course's data is not disclosed.

No temporary write API is exposed. Future extraction code and current tests use typed service write methods. API responses contain no student mastery or presentation state.

## 13. Test strategy

The M3-A suite uses migrated SQLite databases rather than mocked persistence. It covers:

- fresh 0001 -> 0002 -> 0003 migration;
- populated M2 -> M3-A upgrade without data loss;
- enum, CHECK, unique, composite foreign-key, and cascade constraints;
- node CRUD, listing, normalization, and normalized lookup;
- ownership and course isolation;
- valid, self, duplicate, and cross-course edges;
- valid, duplicate, cross-course, and unknown-reference sources;
- material, node, and course deletion behavior;
- repository source cleanup;
- knowledge-model and node-detail responses;
- 404 error mapping and absence of learner fields.

The complete M0-M3-A backend suite is also required to pass.

## 14. M3-B extension points

M3-B may read owned Course records and the existing MaterialContent plain text/segments, then call the approved provider to propose KnowledgeNode and KnowledgeSource inputs through KnowledgeModelService.

M3-B must preserve exact source references, bounded excerpts, ownership, and course isolation. It must not bypass repositories or write invalid candidates directly. Semantic deduplication, hierarchy generation, prerequisite inference, and frontend visualization remain reserved for their later M3 stages.
