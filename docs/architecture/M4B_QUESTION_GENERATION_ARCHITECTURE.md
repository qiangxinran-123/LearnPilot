# LearnPilot V1 — M4-B Question Generation Architecture

## Scope

M4-B creates a validated, source-grounded question bank for a caller-selected course knowledge node. It supports
`single_choice`, `true_false`, and `multiple_choice`, uses the existing OpenAI-compatible provider, and persists only
candidates that pass the complete automatic gate. It does not assemble assessments, score responses, expose a
student diagnostic API, or calculate learning evidence.

## Non-Negotiable M4 Architecture Decisions

- **ARCH-01 — Deterministic Scoring:** M4-B may generate and validate answer keys, but it contains no scorer and never
  asks an LLM to judge a student answer. Deterministic scoring remains M4-C work.
- **ARCH-02 — Historical Reproducibility:** question-bank evolution never updates `AssessmentQuestion.question_snapshot`.
  A frozen snapshot remains the source of historical stems, options, answers, explanations, knowledge references,
  sources, scoring policy, order, and versions.
- **ARCH-03 — Structured Protected Responses:** M4-B neither reads nor mutates student responses. M4-A submission locks
  remain unchanged; no M5 evidence, mastery, confidence, or aggregation model is introduced.

These decisions bind all later M4-B through M4-F work.

## M4-A Data Contract

Validated candidates are converted to the existing `QuestionContentSchema` before persistence. They are written to
the existing `Question` JSON fields (`options`, `correct_answer`, `source_refs`, `generation_metadata`) and linked by
`QuestionKnowledgeNode`. `validation_status=validated` means **automatic gates passed**; it does not mean human review
or educational-measurement validation. No M4-A table or migration was changed.

## M3 Knowledge Context

The service requires an owned course, an active node in that course, and a `CourseKnowledgeBuildState` whose status is
`success`. The target node ID is supplied by the caller and must be the sole node ID returned by the provider. This
prevents the model from inventing associations. Question links use the real M3 integer key and one `primary` role.

## M2 Material Context

Context is resolved through `KnowledgeSource -> Material -> MaterialContent.segments`. A source is eligible only when:

- the material belongs to the requested course;
- its parsed segment exists and has non-empty text;
- the M3 source reference resolves to that actual segment reference; and
- it fits within the configured bounded context.

Only sources actually rendered into the provider request form the allowed citation set. PDF pages and TXT/MD/DOCX
segment labels are data, not trusted commands. Missing trustworthy context returns `QUESTION_SOURCE_INSUFFICIENT`.

## Generation Flow

```text
Owned Course + successful M3 model + active target node
  -> verified, bounded M2/M3 source segments
  -> diagnostic_questions_v1 prompt
  -> existing LLMClient.generate_structured
  -> DiagnosticQuestionGenerationOutput
  -> M4-A QuestionContentSchema
  -> answer / alignment / source / quality / duplicate gates
  -> one transaction: Question + primary QuestionKnowledgeNode
```

`count` is limited by `diagnostic_question_max_count` (default 4, hard schema maximum 8). It prepares candidates for
one node only and is not an assessment assembly algorithm.

## Prompt Version

The centralized prompt is `backend/app/ai/prompts/diagnostic_questions.py` with
`PROMPT_VERSION = "diagnostic_questions_v1"`. Course text appears only inside an explicitly delimited untrusted user
context. The system instruction prohibits executing document instructions, outside knowledge, invented citations, and
invented node IDs. No prompt or secret is stored in the question row.

## Structured Output

The provider boundary validates `DiagnosticQuestionGenerationOutput` and `DiagnosticQuestionDraft`. A second boundary
converts every accepted draft to M4-A `QuestionContentSchema`. Missing fields, malformed JSON, unsupported enums,
duplicate keys, unknown answer keys, blank explanations, and incorrect true/false or multiple-choice cardinality are
rejected; fields are never silently dropped.

## Objective Answer Rules

- Single choice has exactly one declared answer key.
- True/false has ordered `TRUE`, `FALSE` options and exactly one answer.
- Multiple choice has at least two unique declared answer keys, normalized to option order.
- Option keys and option texts are unique; questions and explanations must be non-trivial.

The stored answer key is input for the future deterministic M4-C scorer, not an M4-B score.

## Knowledge Alignment

The target node must exist, be active, belong to the course, and match the provider’s sole `knowledge_node_ids` value.
At least one citation must resolve through a `KnowledgeSource` owned by that node. These structural and evidence gates
make alignment auditable but cannot prove semantic correctness; automatic validation is not a human subject-matter
review.

## Source Validation

Each returned `(material_id, source_reference)` must match the exact allowed context pair after only the existing safe
single-bracket/whitespace normalization. Material ownership, parsed segment existence, and supplied-context membership
are checked. Invented pages, cross-course materials, references absent from the prompt, unresolved labels, and repeated
citations are rejected. Stored source data comes from the database, not model-provided titles or excerpts.

## Duplicate Detection

Stems are normalized with Unicode NFKC, case folding, and removal of non-alphanumeric separators. Exact normalized
duplicates are rejected across the course. `SequenceMatcher` near-duplicate checks are limited to the same primary
knowledge node and the current response, with a configurable default threshold of 0.90. Existing rows are never
deleted or overwritten, and other courses remain independent.

## Validation Status

Only complete batches that pass every gate are stored, with `QuestionValidationStatus.VALIDATED`. Failed candidates
are returned with a categorized error and are not inserted into the usable bank. No review UI or `APPROVED` workflow
is implemented.

## Persistence Transaction

Provider calls and validation occur before database writes. The final transaction rechecks course ownership, the
active target node, and the source facts used by the prompt, then inserts every `Question` and primary
`QuestionKnowledgeNode`. Any association or constraint failure rolls back the whole batch. Existing questions and
historical snapshots are never updated.

## Provider Failure Handling

M4-B uses the existing `LLMClient`, timeout, structured-output parsing, sanitized errors, and retry limit. Recoverable
invalid output or post-output validation may retry only up to `llm_max_attempts`; authentication and other non-retryable
errors stop immediately. Categories include `AI_NOT_CONFIGURED`, `AI_TIMEOUT`, `AI_RATE_LIMITED`,
`AI_AUTHENTICATION_FAILED`, `AI_PROVIDER_ERROR`, `QUESTION_INVALID_OUTPUT`, `QUESTION_SOURCE_INVALID`,
`QUESTION_ALIGNMENT_INVALID`, `QUESTION_QUALITY_INVALID`, and `QUESTION_DUPLICATE`. Logs contain IDs, counts,
provider/model/prompt version, and latency—not keys, complete materials, prompts, or headers.

## Testing Strategy

Automated tests use a scripted LLM adapter and migrated temporary SQLite databases. They cover input boundaries, all
three objective types, structural errors, actual PDF/TXT/MD/DOCX segments, cross-course rejection, prompt-injection
isolation, provider classifications, bounded retries, duplicate scopes, rollback, provenance, and historical snapshot
protection. The separate smoke command uses the real configured provider and an isolated temporary course.

## M4-C Extension Contract

M4-C may select `validated` questions, assemble an assessment, freeze M4-A snapshots, and deterministically compare a
submitted `ObjectiveAnswerSchema` with the snapshot’s answer key and scoring policy. It must not reconstruct history
from current question-bank rows. M4-B does not implement selection ratios, coverage optimization, assessment state
changes, response handling, or scoring.

## Known Limitations

- Automatic gates cannot guarantee factual or pedagogical correctness; human review was not performed in M4-B.
- Similarity is lightweight character-sequence comparison, not semantic embeddings.
- Alignment is established by target IDs and verified M3 evidence, not an independent expert model.
- Source context uses existing M3 links and bounded excerpts; no vector retrieval or internet augmentation is added.
- `validated` is an automatic status only; empirical item difficulty and discrimination remain unknown.

