# LearnPilot V1 — M3-B Implementation Report

## Actual changes

- Added KnowledgeExtractionRun, KnowledgeCandidate, and KnowledgeCandidateSource.
- Added constrained statuses, shared importance/difficulty enums, deterministic normalized names, composite
  context foreign keys, exact duplicate constraints, indexes, and cascades.
- Added three repositories and KnowledgeExtractionService.
- Added knowledge_extraction_v1, Pydantic structured output, bounded chunk batching, exact citation validation,
  source-derived excerpts, exact duplicate cleanup, idempotency, current successful run semantics, and failure
  recording.
- Added material-level POST/GET extraction APIs.
- Added extraction-specific input and aggregate candidate safety limits to Settings and .env.example.
- Refactored the already verified M2 reference normalization into a shared helper while retaining the M2 private
  compatibility exports and behavior.

No frontend, canonical KnowledgeNode creation, edge generation, semantic deduplication, or M3-C+ capability was
added.

## Database migration

Migration 0004_m3b_knowledge_extraction is based on 0003_m3a_knowledge_model and creates:

- knowledge_extraction_runs;
- knowledge_candidates;
- knowledge_candidate_sources;
- enum/check/unique constraints, composite context foreign keys, provenance indexes, and delete cascades.

Verified:

- fresh SQLite 0001 -> 0002 -> 0003 -> 0004: PASS;
- populated M3-A database -> 0004 with existing Course retained: PASS;
- Alembic current head: 0004_m3b_knowledge_extraction.

No previous migration was edited.

## Extraction pipeline

~~~text
owned Course + same-course ready Material
  -> MaterialContent hash/segments
  -> bounded source-aware batches
  -> structured provider calls
  -> exact batch-reference validation
  -> exact normalized-name cleanup
  -> atomic Candidate + Source persistence
  -> successful current-run switch
~~~

The pipeline is synchronous. Invalid or empty/unparsed materials fail before the provider call. The content hash
is checked again before persistence so a concurrent content change cannot attach candidates to the wrong version.

## Prompt version

Prompt: knowledge_extraction_v1.

The exact version is persisted on every run. Historical runs are never relabeled when a future prompt changes.

## Provider

M3-B reuses the M2 OpenAI-compatible provider adapter. The accepted real smoke used DeepSeek model
deepseek-flash. LLM_MODE=mock remains explicit test/development behavior only; no runtime failure can silently
switch to mock.

## Structured output

KnowledgeExtractionOutput accepts zero to twenty candidates per batch. Candidate name, bounded description,
shared enums, and one-to-six source labels are Pydantic validated. Provider JSON/Pydantic failures use the
existing bounded retry behavior. Invalid citations use a bounded correction retry and then fail closed.

AI confidence is not stored because the current self-score is not calibrated and would not be reliable M3-C
evidence.

## Tests

New M3-B coverage: 17/17 PASS (16 dedicated M3-B tests plus one provider structured-output retry regression).

Coverage includes:

- fresh and M3-A upgrade migrations;
- run creation/status transitions and repository persistence;
- candidate/source persistence and database cascades;
- course/material isolation and not-ready short-circuiting;
- valid, bracket-normalized, retried, and exhausted source references;
- real-segment excerpts and no partial persistence;
- small, large/batched, empty, duplicate, and over-limit outputs;
- content-hash invalidation, idempotency, regeneration, and failure safety;
- cross-material separation and absence of canonical KnowledgeNode creation;
- POST/GET API contracts.

Full backend regression: 110/110 PASS. Ruff lint and format checks pass.

## Real DeepSeek smoke test

Result: PASS.

- provider: OpenAI-compatible DeepSeek;
- model: deepseek-flash;
- candidate count: 5;
- candidate quality: PASS;
- candidate provenance: PASS;
- calls: one successful small-material extraction flow; no repeated regeneration.

## Candidate examples

The self-authored Cache smoke produced:

- Cache — PDF Page 1;
- Temporal Locality — PDF Page 1;
- Spatial Locality — PDF Page 1;
- Set-Associative Cache — PDF Page 2;
- LRU Replacement — PDF Page 2.

It did not return a filename, page label as a concept, author, institution, section number, or generic sentence.

## Source validation

The model may identify labels but cannot supply persisted excerpt text. Accepted labels must exist in the exact
batch sent to the provider. Persisted excerpts are copied from actual MaterialContent chunks and bounded to 1000
characters. Unknown references fail the whole run.

## Known limitations

- No semantic deduplication.
- No cross-material merge.
- No canonical node generation.
- No hierarchy generation.
- No prerequisite inference.
- No graph frontend.

These are expected later milestone responsibilities, not M3-B defects.

## M3-C entry conditions

M3-C may consume only current successful, content-hash-matching runs and their evidence. It can add semantic
normalization, cross-material decisions, and canonical KnowledgeNode creation while preserving run/source
provenance. M3-C must not reinterpret extraction confidence because M3-B intentionally stores none.
