# LearnPilot V1 — M4-B Implementation Report

## Outcome

M4-B is complete. The repository now produces a source-grounded, automatically validated question bank for a selected
real M3 knowledge node while preserving all M4-A historical and response invariants. LearnPilot V1 progress is 45%.

## Reused Contracts

- M2: `LLMClient`, OpenAI-compatible DeepSeek provider, JSON structured output, timeout/retry policy, sanitized errors,
  logging, `normalize_source_reference`, and `resolve_source_reference`.
- M3: owned `Course`, active `KnowledgeNode`, successful `CourseKnowledgeBuildState`, `KnowledgeSource`, `Material`, and
  parsed `MaterialContent.segments`.
- M4-A: `Question`, `QuestionKnowledgeNode`, validation enums, `QuestionContentSchema`, repository persistence,
  immutable `AssessmentQuestion` snapshots, and protected `Response` lifecycle.

No second provider/client, agent framework, vector store, scoring service, assessment assembly, or frontend diagnostic
feature was introduced.

## Modified Files

- `backend/app/ai/client.py` — distinguishes non-retryable provider authentication failures.
- `backend/app/ai/models.py` — structured provider output contracts for objective questions.
- `backend/app/ai/prompts/__init__.py`
- `backend/app/ai/prompts/diagnostic_questions.py` — centralized `diagnostic_questions_v1` prompt.
- `backend/app/core/settings.py` — bounded per-node count and similarity threshold.
- `backend/app/repositories/question_repository.py` — primary-node duplicate query.
- `backend/app/schemas/question_generation.py` — internal generation request contract.
- `backend/app/services/diagnostic_question_generation.py` — context resolution, provider orchestration, validation,
  provenance, and atomic persistence.
- `backend/app/services/diagnostic_question_quality.py` — deterministic basic-quality and duplicate gates.
- `backend/scripts/m4b_provider_smoke.py` — isolated real-provider smoke runner.
- `backend/tests/test_m2_llm_client.py` — authentication classification regression.
- `backend/tests/test_m4b_question_generation.py` — 37 M4-B tests.
- `docs/architecture/M4B_QUESTION_GENERATION_ARCHITECTURE.md`
- `docs/migration/M4B_IMPLEMENTATION_REPORT.md`

M4-A files remain present as the uncommitted prior-stage baseline and were not redesigned by M4-B.

## Validation Pipeline

1. Validate course/node/type/difficulty/count input.
2. Require owned course, successful knowledge model, and active in-course node.
3. Resolve only real node-linked material segments and bound context size.
4. Call the existing provider with structured output and a versioned injection-resistant prompt.
5. Validate provider shape and objective answer rules.
6. Require the exact target node and citations from the supplied context.
7. Apply basic deterministic quality rules and scoped duplicate detection.
8. Recheck ownership/node/sources and atomically insert Question plus primary link as `validated`.

`validated` means automated validation passed, not human approval or guaranteed educational validity.

## Provider and Smoke Test

- Mode: `provider`
- Provider: existing `openai-compatible`
- Safe model name: `deepseek-flash`
- Prompt: `diagnostic_questions_v1`
- Isolated real smoke sample: 4 questions (2 single choice, 1 true/false, 1 multiple choice)
- Structured output: PASS
- Objective answer formats: PASS
- Knowledge-node alignment: PASS
- Source-reference validation: PASS
- Atomic persistence and real provenance: PASS
- Result: **PASS**

The smoke runner used a temporary migrated SQLite database and did not touch user courses, uploads, or the configured
application database. No key, Authorization header, full prompt, or complete source document was printed or stored.

## Small Quality Evaluation

- Deterministic fixture set: 24/24 structurally valid candidates passed the automatic base-quality gate.
- Focused end-to-end M4-B suite: 37/37 passed.
- Real-provider smoke: 4/4 generated questions passed all automatic gates.
- `HUMAN_REVIEW = NOT PERFORMED`.

The automatic results must not be interpreted as a claim that all AI-generated questions are 100% factually or
pedagogically correct.

## Persistence and Historical Protection

Question and primary-node association writes share one transaction; the rollback test confirms no orphan Question is
left when association writing fails. Regeneration creates new rows and never updates an existing question or an M4-A
snapshot. A persisted regression creates snapshot V1, generates a new question, reopens the database, and confirms V1
stem, options, correct answer, node name, source, and scoring policy are unchanged.

## Migration Status

M4-A already provided every required field, so M4-B intentionally adds no schema migration. Alembic remains a single
healthy head: `0008_m4a_diagnostic_domain`. The full backend suite includes fresh migration and historical upgrade
coverage and passed.

## Verification Results

- Backend full suite: **203/203 passed** in 198.40 seconds (final post-logging run).
- Focused M4-B suite: **37/37 passed**.
- Ruff lint (`ruff check backend`): **PASS**.
- Ruff format (`ruff format --check backend`): **PASS**, 123 files checked.
- Alembic head: **PASS**, `0008_m4a_diagnostic_domain`.
- Frontend typecheck: **PASS**.
- Frontend lint: **PASS**.
- Frontend tests: **87/87 passed**.
- Frontend build: **PASS** (existing Vite chunk-size warning only).
- Git diff check: **PASS**.
- Secret scan of tracked/untracked M4-B source and docs: **PASS**.

The first direct frontend run was blocked by Windows npm rejecting a UNC working directory. The same source was copied
to the existing local validation directory (without altering repository frontend files), where all four checks passed.

## Non-Negotiable M4 Architecture Decisions

- **ARCH-01 Deterministic Scoring:** preserved. M4-B stores answer keys but implements no scoring.
- **ARCH-02 Historical Reproducibility:** preserved. Question-bank changes do not mutate snapshots.
- **ARCH-03 Structured Protected Responses:** preserved. No response mutation or M5 evidence model was added.

## Known Risks and M4-C Preconditions

- Human subject-matter review and empirical question-quality measurement remain outstanding product processes.
- M4-C must consume only `validated` questions, freeze snapshots before use, and implement deterministic exact-match
  scoring from snapshot data.
- M4-C must define assembly coverage/type/difficulty policy without moving those decisions back into M4-B.
- The lightweight duplicate detector intentionally does not provide semantic embedding similarity.

## Scope Confirmation

- M4-C assembly and deterministic scorer: not implemented.
- M4-D/E/F APIs, UI, reporting, and end-to-end diagnostic: not implemented.
- M5 learning evidence, mastery, confidence, recommendations, and learning paths: not implemented.

