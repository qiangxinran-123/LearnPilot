# LearnPilot V1 — M6 Recommendation Architecture

## 1. Implemented scope

This document records the implemented M6-1 input foundation, M6-2 deterministic recommendation engine, and M6-3
learning-plan persistence. M6-3 converts an M6-2 result into a small ordered plan without recalculating the score or
weakening prerequisite decisions. No frontend, learning session, task execution, mastery update, or LLM generation is
implemented.

## 2. Data source and field mapping

| Recommendation input | Real source | Type and range | Nullable / missing behavior | Existing access path | M6-1 use |
| --- | --- | --- | --- | --- | --- |
| User ID | User.id; caller's existing user context | positive integer primary key | non-null on persisted records | UserRepository; current APIs resolve the configured bootstrap user | explicit user_id; course ownership is checked with it |
| Course ID | Course.id, Course.owner_id | positive integer primary/foreign keys | non-null | CourseRepository.get_for_owner; course services/APIs | explicit course_id; a foreign course is hidden as COURSE_NOT_FOUND |
| Knowledge node | KnowledgeNode | positive ID; non-null course, name, importance, difficulty; is_active boolean | active-node query can return an empty list | KnowledgeNodeRepository.list_by_course; M3 knowledge service/API | typed node snapshot; only active nodes from the requested course |
| Knowledge edge | KnowledgeEdge | positive source/target IDs; relation is contains or prerequisite | relationship run can be absent; manual edges are allowed | KnowledgeEdgeRepository.list_current_by_course; M3 relationship service/API | current/manual visible edges are read in one batch |
| Prerequisite | M3 KnowledgeRelationType.PREREQUISITE | directed source -> target; source is required knowledge and target is dependent knowledge | zero edges is valid | same edge repository and M3 structural validator | only this relation type enters the prerequisite contract |
| Knowledge importance | KnowledgeNode.importance | non-null low, medium, or high | not nullable | M3 node repository/API | AVAILABLE; retained as source data, not scored |
| Course importance | no M3-M5 field | UNAVAILABLE | always explicitly unavailable | none | no fabricated value |
| Mastery score | StudentKnowledgeState.mastery_score | nullable decimal in [0, 100] | null for not assessed; stale/unverified state is suppressed to null | StudentKnowledgeStateRepository; M5-D mastery API/read service | source state only; no recalculation or default zero |
| Mastery status | StudentKnowledgeState.mastery_status | M5 enum: not_assessed, good_performance, needs_reinforcement, possibly_weak, needs_attention | synthesized as not_assessed only when state is absent/stale | same M5 repository/API | preserved without redefining M5 semantics |
| Mastery confidence | StudentKnowledgeState.confidence_level and reason codes | insufficient, low, medium, high | absent/stale state is explicitly insufficient | same M5 repository/API | used only for eligibility classification |
| Learning Evidence | source-verified LearningEvidence joined to submitted Assessment/Response | score [0,1], weight (0,1], source/difficulty enums, timestamps and positive source IDs | may be empty; current node mapping is nullable in storage | LearningEvidenceRepository.list_submitted_for_current_nodes; M5-D evidence API | exposes aggregate metadata only; raw answers and question snapshots are excluded |
| Latest valid assessment time | LearningEvidence.occurred_at for source-verified submitted diagnostic evidence | timezone-capable datetime | null when no valid evidence exists | same batch evidence query | latest occurrence across the course; no review-risk calculation |
| Review risk | no M3-M5 field or algorithm | UNAVAILABLE | always explicitly unavailable | none | no fabricated value |

The database also contains Assessment.submitted_at. M6-1 deliberately uses the timestamp on already authorized,
submitted LearningEvidence; it does not add another assessment query or treat a draft assessment as recommendation
evidence.

## 3. Domain contracts

backend/app/schemas/recommendation.py defines the M6 boundary:

- RecommendationContext aligns one user/course with typed node snapshots, validated prerequisite edges, one mastery
  state and evidence summary per active node, candidate classifications, explicit availability flags, and
  initial-diagnostic state.
- CandidateNode carries M5 mastery and confidence separately, direct prerequisite IDs, eligibility status, and a
  required exclusion reason for every non-eligible state.
- PriorityBreakdown reserves the five M6-2 output components. Every component defaults to None; M6-1 never uses zero
  to mean “not computed.”
- RecommendationResult fixes the future result envelope. M6-1 defines but never instantiates a production result.

Pydantic validators reject misaligned context collections, cross-course nodes/candidates, a score on unavailable
mastery, and candidate status/reason contradictions. No unconstrained dict[str, Any] is used.

## 4. Context assembly

RecommendationContextService.build_recommendation_context(user_id=..., course_id=...):

1. resolves the course through CourseRepository.get_for_owner;
2. loads active course nodes in one query and fails with KNOWLEDGE_MODEL_NOT_FOUND when none exist;
3. loads current/manual M3 edges in one query, filters and validates prerequisites;
4. batch-loads the user's course mastery states;
5. batch-loads only source-verified submitted diagnostic Evidence for all current nodes;
6. verifies each persisted state against the same M5 fingerprint/version contract used by MasteryReadService;
7. builds typed mastery, evidence, candidate, and availability records.

The service owns no commit, calls no write repository method, creates no user, does not refresh mastery, and invokes
no LLM. Query count is course-level rather than node-level, avoiding an obvious N+1 pattern.

## 5. Candidate eligibility

Eligibility is deterministic and does not assign priority:

| Status | Rule |
| --- | --- |
| UNASSESSED | persisted state is absent, stale, not calculated, or M5 reports not_assessed; mastery remains null |
| LOW_CONFIDENCE | a calculated score exists but M5 confidence is insufficient or low |
| MASTERED | M5 status is good_performance and confidence is at least medium |
| ELIGIBLE | calculated non-mastered state with medium or high confidence |
| INVALID | node/course/state identities conflict or the state contract is internally invalid |

Low confidence takes precedence over MASTERED eligibility, but the original M5 mastery status remains visible on the
candidate. This prevents an uncertain estimate from becoming a definitive exclusion while preserving M5's
classification. MASTERED means excluded from the present new-learning candidate pool only; it is not a permanent
no-review assertion. M6-1 implements no review recommendation.

## 6. Prerequisite validation

M3 defines prerequisite direction as required knowledge source -> target dependent knowledge. M6-1:

- ignores contains edges;
- deduplicates identical prerequisite pairs deterministically;
- rejects an edge from another course;
- rejects unknown/inactive node references and self references;
- reuses M3's DAG cycle detector;
- blocks context construction on any invalid prerequisite graph.

It does not evaluate whether a prerequisite is mastered, recursively search dependencies, repair the graph, or
select a recommendation.

## 7. Missing and boundary data

- Foreign and absent courses share the existing ownership-hiding COURSE_NOT_FOUND behavior.
- A course with no active node reports KNOWLEDGE_MODEL_NOT_FOUND.
- No diagnostic evidence sets needs_initial_diagnostic=true.
- Missing mastery is null/not_assessed, never zero.
- Stale state is reported as unavailable and never used as a score.
- Node importance is available; course importance and review risk are unavailable.
- Invalid graph input stops assembly with a typed error code and optional edge details.
- SQLAlchemy failures propagate through the existing exception boundary; no default context is fabricated.

## 8. M6-2 deterministic recommendation engine

RecommendationEngine is a pure, read-only consumer of RecommendationContext. Versioned configuration is centralized
in RecommendationAlgorithmConfig as recommendation_v1:

P = 0.50 G + 0.25 D + 0.15 I + 0.10 R

- G is 1 - mastery_score / 100 and is calculated only for a calculated state with medium/high confidence.
- D is the number of unique downstream prerequisite dependents divided by max(active node count - 1, 1).
- I is a real normalized course-importance input when supplied. The current M3-M5 adapter has no such field, so the
  engine uses the explicit neutral fallback 0.5 and emits NEUTRAL_COURSE_IMPORTANCE.
- R is a real per-node normalized review-risk input when supplied. The current adapter has no review-risk producer,
  so the engine uses 0.5 and emits NEUTRAL_REVIEW_RISK.

Every component is validated in [0,1], Decimal arithmetic is used, and published values are rounded half-up to four
decimal places. Missing data never becomes maximum risk. Actual M3 node importance is not mislabeled as course
importance; it is used only as the stable secondary ordering key.

## 9. Prerequisite hard constraint and frontier selection

The default prerequisite threshold is 60 and is centralized with the weights. A prerequisite is satisfied only when
its state is calculated, its confidence is medium/high, and its mastery reaches the threshold.

For each otherwise eligible target, the engine recursively resolves unsatisfied prerequisites until it reaches a
currently learnable frontier. Single, parallel, and multi-level dependencies are supported. The target cannot enter
the scoring pool while any known prerequisite is unsatisfied. Missing/low-confidence prerequisite state produces
NEEDS_PREREQUISITE_ASSESSMENT rather than a false zero mastery claim.

Before traversal, deterministic topological validation identifies cycles and graph portions that depend on them.
Unknown references and self edges are marked explicitly. A damaged branch is excluded without allowing the hard
constraint to be bypassed and without suppressing unrelated valid candidates.

## 10. Candidate selection and stable ordering

Normal scoring accepts only M6-1 ELIGIBLE candidates. MASTERED nodes are excluded unless a real available review-risk
value reaches the configured review threshold; this is the only review-candidate rule. UNASSESSED and LOW_CONFIDENCE
nodes are never assigned a knowledge-gap score.

Candidates are ordered by:

1. total priority descending;
2. actual M3 node importance descending;
3. stable knowledge-node ID ascending.

No random value, unordered set iteration, database incidental order, LLM, or current wall-clock value affects the
result.

## 11. Result and explanation contract

RecommendationResult now supports both an available recommendation and explicit no-result states:

- NEEDS_INITIAL_DIAGNOSTIC;
- NEEDS_PREREQUISITE_ASSESSMENT;
- NO_ELIGIBLE_CANDIDATE;
- ALL_MASTERED;
- INVALID_CONTEXT.

Available results include a complete PriorityBreakdown, typed reason codes, prerequisite evidence statuses,
blocked downstream targets, required assessment nodes, invalid excluded nodes, and the confidence-limitation flag.
Reasons are generated solely from score components and graph/state decisions.

## 12. Learning plan and task persistence

M6-3 adds `LearningPlan` and `LearningTask` tables through revision `0013_m6_learning_plans`.

- A plan belongs to one user and course, has exactly one M6-2 target node, and stores the real reason codes, total
  priority, component breakdown, prerequisite evidence, and blocked downstream targets used to create it.
- A plan status is either `AVAILABLE` or `SUPERSEDED`. `NOT_AVAILABLE` and `STALE` are response states, not fabricated
  database plans.
- Each task belongs to a plan and its target node. Database constraints limit its zero-based order to 0-2 and make
  each order unique within the plan.
- The only task types are `CONCEPT_REVIEW`, `EXAMPLE_WALKTHROUGH`, and `TARGETED_PRACTICE`.
- Plans and tasks are written in one transaction. Task deletion cascades with plan deletion; user, course, and target
  node references use database foreign keys.

The database uses a nullable `active_slot`: an available plan holds slot 1, while superseded rows hold null. A unique
constraint on `(user_id, course_id, active_slot)` prevents concurrent requests from creating two active plans while
still permitting plan history.

## 13. Recommendation-to-plan conversion

`LearningPlanService` always calls `RecommendationContextService` and `RecommendationEngine`; it does not duplicate
M6-2 scoring. An available result is accepted only when user/course identity, target node, and complete score are
consistent. The default deterministic templates are:

1. concept review (15-minute template estimate);
2. example walkthrough (20-minute template estimate);
3. targeted practice (20-minute template estimate).

A real `REVIEW_NEEDED` result uses only targeted practice. Descriptions explicitly direct the learner to existing
materials when available and never invent exercises, page numbers, examples, or sources. Estimates are fixed template
values, not predictions of an individual learner's actual time.

## 14. Reuse and invalidation

The context fingerprint is SHA-256 over canonical JSON containing the complete typed M6-1 context, the complete M6-2
result, the plan schema version, and the task-template version. It contains no request time. This means changes to
verified mastery/evidence, active knowledge nodes, prerequisite edges, importance/review inputs, recommendation target,
score, or reasons invalidate the plan. Course fields outside the recommendation context, such as description, do not.

- POST with the same fingerprint returns the existing plan.
- POST with a changed available fingerprint marks the previous plan `SUPERSEDED` and atomically creates a replacement.
- POST when M6-2 returns no recommendation supersedes an old current plan and returns `NOT_AVAILABLE` without saving a
  fake plan.
- GET performs the same lightweight comparison but never writes. It returns `STALE` when a stored plan no longer
  matches current inputs and never creates a replacement implicitly.

An ownership-scoped lookup remains mandatory. A database uniqueness conflict caused by concurrent generation is
resolved by returning the winning plan when it has the same fingerprint; otherwise the caller receives an explicit
conflict and may retry.

## 15. API contract

- `GET /api/courses/{course_id}/learning-plan` reads and validates the current plan without creating or superseding it.
- `POST /api/courses/{course_id}/learning-plan/generate` creates, reuses, supersedes, or returns a no-plan state.

Responses expose availability, the M6-2 recommendation availability, reuse status, plan/target IDs, reason codes,
score breakdown, prerequisite evidence, ordered tasks, and template estimates. The internal fingerprint and active-slot
implementation are intentionally not exposed. The current API uses the same configured bootstrap-user identity bridge
as existing M3-M5 endpoints.

## 16. M7 boundary

Learning tasks are descriptions only. M6-3 does not introduce completion/pass/fail states, learning sessions, task
execution, generated questions, adaptive practice, evidence writes, or mastery refresh. Those require real M7 execution
evidence and remain outside this module.

## 17. Known constraints

- The current API identity mechanism remains the existing configured bootstrap user. The M6-1 domain service accepts
  an explicit user ID so a later authorized API layer can supply the real request identity without changing the
  contract.
- M3 has no independent current graph-version field. M6-1 inherits M5's stable-ID, Evidence mapping, version, and
  fingerprint safeguards.
- Current persisted M3-M5 data has no course-importance or review-risk producer. Neutral fallbacks remain explicit
  until an authorized stage supplies real normalized values.
- M6-4 consumes the minimum learning-plan API through the existing frontend Axios client. Dashboard and Learn share
  the same typed plan state machine; the frontend does not reproduce M6-2 scoring or M6-3 plan generation.
- SQLite ignores row locks, so concurrency safety ultimately relies on the database active-slot unique constraint and
  same-fingerprint conflict recovery. Databases with row locking additionally serialize the current-plan lookup.

## 18. M6-4 presentation boundary

The frontend treats `AVAILABLE`, `STALE`, `NOT_AVAILABLE`, and technical failure as separate view states.
`STALE` is a valid read result and only shows a user-triggered regeneration action; rendering, mounting, refreshing,
or course switching never performs an implicit POST. Both Dashboard and Learn display the persisted target, reason
codes, prerequisite evidence, and ordered task descriptions from M6-3. Tasks deliberately have no completion,
check-in, evidence-write, mastery-update, or Learning Session behavior. Knowledge-map navigation reuses the existing
course detail route and passes the exact M6 target node ID.

## 19. M6 final acceptance handoff

M6 is a read/plan/presentation boundary. Its stable outputs for M7 are the typed recommendation result, persisted
learning plan, ordered read-only task descriptions, reason codes, score breakdown, prerequisite evidence, and node
identity. M7 must obtain real execution evidence before recording task completion, creating LearningEvidence, or
refreshing Mastery. It must not infer completion from a displayed M6 task.
