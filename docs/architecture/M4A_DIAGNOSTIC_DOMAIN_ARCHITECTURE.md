# LearnPilot V1 — M4-A Diagnostic Domain Architecture

## 1. M4-A Scope

M4-A adds only the diagnostic data and domain foundation: constrained enums, SQLAlchemy mappings, a SQLite/MySQL-compatible Alembic migration, validated question/snapshot/answer contracts, owner-scoped repositories, a minimal lifecycle service, and persistence tests.

It exposes no student-facing diagnostic API or UI. It contains no LLM question generation, paper assembly, scoring implementation, weakness analysis, report generation, Learning Evidence, mastery, confidence, recommendation, or adaptive learning logic.

## 2. Non-Negotiable M4 Architecture Decisions

These decisions apply to M4-A through M4-F and must not be weakened by later work.

### ARCH-01 — Deterministic scoring

Objective scoring will be performed by a deterministic M4-C scorer. M4-A stores normalized correct-answer arrays, normalized submitted-answer arrays, and an immutable `objective_exact_match_v1` scoring-policy snapshot. It never calls an LLM or calculates correctness or points. `Response.is_correct` and `Response.points_awarded` remain NULL until the future deterministic scorer writes them.

### ARCH-02 — Reproducible historical diagnostics

Every fixed `AssessmentQuestion` contains a self-contained, versioned JSON snapshot. Historical rendering and future score recomputation read this snapshot plus the stored response, never mutable `Question` or `KnowledgeNode` rows. Updating or deleting the source question and renaming, deleting, or rebuilding a knowledge node cannot alter the snapshot.

### ARCH-03 — Structured and protected responses

Answers use the versioned `objective_answer_v1` contract. One current `Response` is permitted per `AssessmentQuestion`. Drafts may be overwritten only while the assessment is `IN_PROGRESS`; submission atomically locks every answer and moves the assessment to `SUBMITTED`. Normal domain operations cannot modify submitted answers.

## 3. Existing M3 Contract

The implemented M3 foundation uses integer primary keys for User, Course, Material, and KnowledgeNode. Course ownership is `Course.owner_id`; repositories use SQLAlchemy 2.x typed mappings and flush without committing; services define `session.begin()` transaction boundaries. Pydantic is v2.13.5. SQLite foreign keys are enabled on connection.

KnowledgeNode has the composite uniqueness contract `(course_id, id)`, can be deactivated, and may be deleted through graph rebuild/cascade behavior. M3 provenance is `KnowledgeSource(material_id, source_reference, excerpt)`. Canonicalization runs provide a possible graph version, but no stable required graph-version identifier exists for every node. M4-A therefore permits an optional `knowledge_model_version` snapshot value while remaining fully reconstructable without it.

## 4. Diagnostic Domain Model

```text
User 1 ── N Course
Course 1 ── N Question
Question 1 ── N QuestionKnowledgeNode N ── 1 KnowledgeNode
Course 1 ── N Assessment N ── 1 User(owner)
Assessment 1 ── N AssessmentQuestion
AssessmentQuestion 1 ── 0..1 Response
```

Core entities are `Question`, `QuestionKnowledgeNode`, `Assessment`, `AssessmentQuestion`, and `Response`. `DiagnosticResultContract` and `DiagnosticNodeResultContract` are future, non-persisted output contracts only.

## 5. Entity Relationship and deletion behavior

- Course deletion cascades its questions and assessments, matching existing course ownership semantics.
- KnowledgeNode deletion cascades only the live `QuestionKnowledgeNode` association, so M3 rebuild is never blocked.
- Question deletion sets `AssessmentQuestion.question_id` to NULL and preserves the historical snapshot.
- Assessment deletion cascades snapshots and responses.
- Response uses a composite foreign key `(assessment_id, assessment_question_id)` to prevent cross-assessment attachment.

No M0–M3 model or migration was rewritten.

## 6. Question Schema

Supported types are exactly `single_choice`, `true_false`, and `multiple_choice`. Options are ordered `{key, text}` records. Correct answers are ordered key arrays; free-text answer keys are not accepted. Single-choice and true/false questions require one correct key; multiple-choice requires at least two; true/false options are exactly `TRUE`, then `FALSE`.

`QuestionContentSchema` validates nonblank stem/explanation, unique option keys, answer membership, and source-reference shape. `QuestionCreateSchema` requires unique knowledge bindings and exactly one PRIMARY node. `CandidateQuestionSchema` excludes correct answers, explanations, and scoring internals.

## 7. Assessment Lifecycle

The only allowed path is:

```text
DRAFT -> READY -> IN_PROGRESS -> SUBMITTED
```

- `create_assessment_draft` creates `DRAFT`.
- `fix_question_snapshots` validates and inserts the whole ordered paper in one transaction, then sets `READY`.
- `start_assessment` performs a compare-and-set transition to `IN_PROGRESS` and records `started_at`.
- `submit_assessment` validates complete answers, performs a compare-and-set transition, stamps responses and assessment with one submission time, and commits atomically.

No generic status setter exists. Backward or skipped transitions are rejected.

## 8. Historical Snapshot Contract

`assessment_question_v1` stores:

- source question ID and content version;
- question type, stem, ordered options, normalized correct answer, explanation, and difficulty;
- historical knowledge-node ID, name, and PRIMARY/SECONDARY role;
- structured source references;
- optional knowledge-model version;
- ordered position;
- `objective_exact_match_v1` and max points.

Pydantic validates every snapshot before persistence. There is no repository update method for snapshot JSON or order. After READY, the service rejects replacement or refreezing.

## 9. Response Data Contract

`objective_answer_v1` stores `selected_options` as unique normalized keys. The domain service checks keys against the stored snapshot and enforces single-selection semantics where applicable. `answered_at`, `submitted_at`, created/updated timestamps, and nullable future scoring fields are persisted. Submission means answer lock only, not scoring.

## 10. Ownership Strategy

Every domain operation receives an owner ID and resolves Course, Question, and Assessment through owner-scoped queries. Other-owner resources are returned as not found. Question/node bindings require an active node in the same course. Snapshot fixation requires each Question in the Assessment course. Composite database foreign keys additionally enforce live question/node course equality and response/assessment equality.

This reuses the current ownership foundation and introduces no authentication or tenancy framework.

## 11. Transaction Boundaries

Each service operation owns one `session.begin()` block. Snapshot fixation and final submission are atomic. Submission uses a database compare-and-set from `IN_PROGRESS` to `SUBMITTED`; the response unique constraint prevents duplicate current answers. Repeating an identical submitted payload is idempotent, including from a new Session. A different payload after submission is rejected. Any invalid final answer rolls back all answer changes and the status transition.

## 12. Database Constraints

The database enforces enum checks; non-null required content; positive question versions; nonnegative order; foreign keys; `(question_id, knowledge_node_id)` uniqueness; `(assessment_id, order_index)` uniqueness; one source Question per Assessment; one Response per AssessmentQuestion; and composite course/assessment boundaries. Pydantic plus the domain write path enforce JSON content, exactly one PRIMARY node, option/answer agreement, and lifecycle rules that are not portable SQL CHECK constraints.

## 13. Migration Strategy

Migration `0008_m4a_diagnostic_domain` follows `0007_m3e_workspace_build_state`. It only creates new tables, indexes, foreign keys, checks, and enums. It is compatible with SQLite and uses portable SQLAlchemy types. Fresh upgrade and populated M3-to-head upgrade are tested on isolated SQLite files; existing Course, Material, and KnowledgeNode rows are asserted unchanged.

## 14. M4-B–M4-F Extension Contracts

- M4-B may create validated `QuestionCreateSchema` payloads but must not bypass the domain validator or place secrets in generation metadata.
- M4-C may select questions and read snapshot correct answers/scoring policy to implement the deterministic scorer. It must write only scoring outputs and never use an LLM for final judgment.
- M4-D may expose lifecycle APIs and candidate-safe DTOs, never internal Question or snapshot answer fields before allowed disclosure.
- M4-E may derive the non-persisted result contracts from submitted responses and deterministic scores.
- M4-F may perform end-to-end acceptance without changing historical reconstruction or answer-lock rules.

None of these features is implemented in M4-A.

## 15. M5 Evidence Input Contract

Future M5 may read the Assessment identity/owner/course, immutable AssessmentQuestion snapshot, locked Response, deterministic M4-C correctness/points, and historical knowledge references. These records are raw evidence inputs. M4-A creates no `LearningEvidence`, `MasteryScore`, `MasteryConfidence`, history, weighting, or aggregation model.

## 16. Known Limitations

- There is no student-facing API or UI.
- There is no question generator, automatic paper assembly, or scorer.
- JSON integrity is guaranteed through the M4-A service path; direct administrator SQL is outside the threat model.
- The optional knowledge-model version is present only when the Question metadata supplies one; snapshot content never depends on resolving that version.
- SQLite compare-and-set and uniqueness provide competition-grade local concurrency behavior; no distributed lock is introduced.
