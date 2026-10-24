# LearnPilot V1  FIX-1 Diagnostic Question Bank Report

## Scope

FIX-1 restores the backend question-bank workflow required before a real initial
diagnostic can run. It does not generate production questions, call a paid LLM,
change the assessment threshold, modify M5/M6 behavior, or add frontend UI.

## Existing components reused

- `DiagnosticQuestionGenerationService` remains the only LLM question generator.
- `DiagnosticQuestionQualityValidator` remains the only deterministic quality and duplicate validator.
- Existing source-reference resolution and verified material-context loading are reused.
- `QuestionRepository` remains the persistence boundary.
- `DiagnosticDomainService.build_question_snapshot` is reused for publication-time schema validation.
- `AssessmentAssemblyService` remains the only readiness and core-coverage policy.

## Backend changes

- Added an internal `initial_status` argument to the existing generator. Its
  default remains `VALIDATED` for compatibility with previously verified
  internal callers. The public FIX-1 workflow always supplies `PENDING`.
- Added `DiagnosticQuestionBankService` for ownership-scoped listing,
  generation orchestration, publication validation, approval, rejection, and
  readiness presentation.
- Added conditional repository status transitions to prevent stale concurrent
  approval/rejection from overwriting another transition.
- Added status filtering and eager knowledge-node loading to the question repository.
- Exposed the required core nodes from the existing assembly preview so the
  management API does not duplicate ranking or coverage policy.
- Added strict Pydantic request and response contracts.
- No database models, tables, or migrations were added.

## Lifecycle

```text
Explicit POST generation
  -> existing structured LLM generator and deterministic validation
  -> PENDING
  -> explicit approve -> VALIDATED
  -> explicit reject  -> REJECTED
```

Only `VALIDATED` questions enter the existing assessment assembly query.
`PENDING` and `REJECTED` questions remain excluded.

Only `PENDING -> VALIDATED` and `PENDING -> REJECTED` are supported.
Every transition uses a conditional database update and returns
`QUESTION_INVALID_STATE` when the expected state no longer matches.

## API contract

All routes use the existing `/api/diagnostics` namespace.

- `GET /api/diagnostics/courses/{course_id}/question-bank`
  - Read-only.
  - Returns state counts, readiness, the current required question count, and
    required core nodes derived from the assembly policy.
  - Never calls an LLM or changes state.
- `GET /api/diagnostics/courses/{course_id}/questions?status=...`
  - Lists only the bootstrap user's owned course.
  - Optional status: `pending`, `validated`, or `rejected`.
  - This is a management response and intentionally contains answers and explanations.
- `POST /api/diagnostics/courses/{course_id}/questions/generate`
  - Accepts only `knowledge_node_id` and the literal `count=1`.
  - The client cannot supply status, source text, source references, answers,
    provider configuration, or model configuration.
  - Creates only `PENDING` questions.
- `POST /api/diagnostics/courses/{course_id}/questions/{question_id}/approve`
  - Revalidates current course ownership, model readiness, question schema,
    deterministic quality, current source references and excerpts, exactly one
    active same-course PRIMARY node, and duplicates against validated questions.
- `POST /api/diagnostics/courses/{course_id}/questions/{question_id}/reject`
  - Preserves the question and its provenance while changing only
    `PENDING -> REJECTED`.

Student assessment responses are unchanged and continue to omit correct answers,
explanations, scoring policy, and source references before submission.

## Readiness consistency

The question-bank response calls
`AssessmentAssemblyService.preview_question_bank`. This is the same policy used
by the existing readiness endpoint:

- minimum eight eligible validated questions;
- required high/medium core-node ordering remains importance then stable ID;
- source refs, a single active PRIMARY node, valid schema, and unique normalized
  stems remain mandatory;
- when nine eligible questions exist, the first nine required nodes must be covered.

No new readiness formula or lower threshold was introduced.

## Duplicate and concurrency boundary

- A node with an existing `PENDING` question must be reviewed before another
  generation request.
- A node already covered by a `VALIDATED` question is not generated again by
  default.
- Existing exact and near-duplicate content checks remain active.
- Generation for the same course/node is serialized within one application
  process. This prevents duplicate clicks in the current single-process V1
  deployment.
- Conditional database transitions protect approve/reject races.
- This is not a network-level exactly-once guarantee across multiple application
  processes. No distributed lock or queue was added.

## Tests

### New FIX-1 tests

Command:

```bash
pytest -q backend/tests/test_fix1_diagnostic_question_bank.py
```

Result: `12 passed`.

Coverage includes:

- public generation creates `PENDING`;
- duplicate pending generation is blocked before another provider call;
- provider-not-configured and invalid output leave no question;
- listing and status filters;
- management response includes answers;
- approve/reject transitions and illegal repeat transitions;
- current source revalidation;
- missing PRIMARY rejection;
- cross-course generation/list/review isolation;
- eight-node readiness, pending exclusion, and ninth-node coverage;
- OpenAPI route registration.

All generation tests use `ScriptedLLMClient`; paid provider calls: zero.

### M4M6 targeted regression

Result: `155 passed`.

### Backend regression

Command:

```bash
pytest -q
```

Result: `347 passed`.

### Quality and migration

- `ruff check backend`: PASS
- `ruff format --check backend`: PASS
- Empty temporary SQLite `alembic upgrade head`: PASS, head
  `0013_m6_learning_plans`
- New FIX-1 migration: not required

## Known limitations

- FIX-1 does not provide frontend controls; that is FIX-2.
- The public generation endpoint intentionally fixes generation to one
  single-choice question per request. Difficulty is derived from the knowledge
  node. Internal generator capabilities remain unchanged.
- The process-local generation lock matches the current V1 deployment boundary;
  it is not a distributed exactly-once mechanism.
- Automated validation is not an academic correctness oracle. A human must
  approve each pending question before it can enter diagnosis.

## FIX-2 integration notes

FIX-2 should:

1. load the question-bank GET endpoint without side effects;
2. show required nodes and pending/validated state;
3. call generation only after an explicit user action and confirmation;
4. disable duplicate submissions while POST is pending;
5. display pending question content, answers, explanations, and provenance;
6. expose explicit approve/reject actions;
7. refresh readiness after each review;
8. stop generation when readiness reports `can_start=true`.

## Acceptance

FIX-1 is complete. The backend provides a review-gated, ownership-scoped,
source-grounded question-bank workflow and remains compatible with M4M6.
FIX-2 may add the user interface without changing generator or readiness rules.
