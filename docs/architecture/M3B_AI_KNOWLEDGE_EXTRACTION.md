# LearnPilot V1 — M3-B AI Knowledge Extraction

## 1. Scope

M3-B extracts evidence-backed knowledge candidates from one successfully parsed Material at a time. It adds a
versioned structured prompt, bounded chunk batching, strict citation validation, candidate staging persistence,
run provenance, current-result semantics, synchronous material APIs, and real-provider verification.

M3-B does not create canonical KnowledgeNode rows. It implements no semantic or cross-material deduplication,
hierarchy, prerequisite inference, graph frontend, assessment, student state, mastery, recommendation, vector
infrastructure, Agent, or background queue.

## 2. Candidate vs canonical node

KnowledgeCandidate is raw, material-scoped extraction output. KnowledgeNode is the canonical course model.
They use separate tables and services:

~~~text
MaterialContent -> KnowledgeExtractionRun -> KnowledgeCandidate -> KnowledgeCandidateSource

KnowledgeCandidate -- M3-C only --> canonical KnowledgeNode
~~~

An M3-B success never inserts KnowledgeNode or KnowledgeEdge. Exact normalized-name cleanup within one material
is only transport-level duplicate removal. LRU Replacement and Least Recently Used Replacement remain separate
candidates, and the same name extracted from two materials remains two records.

## 3. ExtractionRun

KnowledgeExtractionRun records course, material, content hash, constrained status, provider, model, prompt
version, candidate count, safe error metadata, timestamps, and is_current.

Statuses are pending, running, success, and failed. The synchronous service creates a running attempt and
finishes it as success or failed. Pending remains available for explicit persistence/state-transition semantics
without introducing a queue.

Only a successful run can become current. A new successful run atomically clears the previous current flag. A
failed regeneration remains historical and cannot displace the prior valid current run.

## 4. KnowledgeCandidate

Each candidate belongs to exactly one run, course, and material. It stores name, M3-A-compatible deterministic
normalized name, a bounded description, the shared importance enum, the shared difficulty enum, and creation
time. A composite foreign key enforces that its course/material context equals its run context.

AI self-reported confidence is intentionally omitted. The current provider has no calibrated confidence signal,
so persisting a number would add misleading data rather than useful M3-C evidence.

## 5. Candidate source evidence

KnowledgeCandidateSource stores candidate, material, source reference, an excerpt up to 1000 characters, and
creation time. A composite foreign key enforces that the evidence material equals the candidate material.
Candidate/material/reference is unique.

The model returns source labels only. The service resolves a narrowly allowed bracket/spacing presentation
variant, validates the canonical label against the exact batch reference set, and builds the excerpt from the
actual MaterialContent chunk. Model-written quotation text is never persisted as evidence.

## 6. Prompt design

The centralized prompt is backend/app/ai/prompts/knowledge_extraction.py, version knowledge_extraction_v1. It
asks for independently learnable, stable domain concepts at useful granularity. It excludes filenames, page
numbers, section numbers, course introductions, summaries, authors, institutions, references, generic sentences,
and fragments.

Importance is scoped to the current material. Difficulty describes concept complexity, not a learner. The prompt
explicitly forbids cross-material merging, synonym resolution, hierarchy, prerequisites, and canonical creation.

## 7. Structured output

KnowledgeExtractionOutput is Pydantic-validated and contains zero to twenty KnowledgeCandidateDraft objects per
batch. Every non-empty candidate has bounded name/description, shared enum values, and one to six source
references. An empty list is valid for covers, contents pages, notices, and other material without learnable
concepts.

The provider adapter retains the M2 JSON/Pydantic retry boundary. There is no silent mock fallback.

## 8. Chunking strategy

The service reuses M2 MaterialContent.segments, LLM_CONTEXT_CHARS, LLM_CHUNK_CHARS, and
LLM_CHUNK_OVERLAP_CHARS. Small material normally forms one request. Large material is split into source-aware
chunks and packed into batches whose document context never exceeds LLM_CONTEXT_CHARS.

KNOWLEDGE_EXTRACTION_MAX_INPUT_CHARS is the one extraction-specific input safety bound because extraction may
make multiple paid requests. KNOWLEDGE_EXTRACTION_MAX_CANDIDATES is a configurable aggregate guard; exceeding it
fails the run instead of silently truncating evidence.

## 9. Source validation

Every returned reference must resolve to a label present in that exact batch. The shared narrow M2 resolver may
remove one outer bracket pair and accept a whitespace-only presentation variant only when it uniquely matches an
actual label. It does not infer page numbers or accept page-like strings.

An invalid reference triggers a bounded grounding retry. Exhaustion marks the run failed and persists no partial
candidate set.

## 10. Idempotency

The default extraction key is material ID, current MaterialContent hash, prompt version, and model. If the current
successful run matches this key, POST returns it without an LLM request or duplicate rows. regenerate=true
creates a new run.

GET serves the current success only when its content hash still matches MaterialContent. A content change makes
the old result stale and permits a new extraction.

## 11. Retry strategy

Provider JSON/Pydantic failures use the existing bounded M2 provider retry. Authentication and other nontransient
4xx failures are not retried. Citation correctness has a separate bounded retry using the configured attempt
limit and an explicit allowed-label correction. No retry is infinite and runtime failure never falls back to mock.

## 12. Failure safety

Candidates and sources are written only after all batches, schemas, citations, aggregate limits, and content-hash
checks pass. Persistence and current-run switching occur in one transaction. A failed run stores a stable safe
error code/message and zero candidates. Previous successful data remains intact.

## 13. Real provider verification

The accepted smoke used provider mode with the configured OpenAI-compatible DeepSeek service and model
deepseek-flash. One self-authored two-page Cache material produced five candidates: Cache, Temporal Locality,
Spatial Locality, Set-Associative Cache, and LRU Replacement. All accepted candidates referenced only the real
PDF Page 1 or PDF Page 2 segment and received stored excerpts from those segments.

No credential, endpoint, Authorization header, or complete source text was printed or recorded.

## 14. M3-C extension points

M3-C may read current successful candidates, deterministic names, run provenance, and source evidence to perform
explicit normalization, semantic deduplication, cross-material merge decisions, and canonical KnowledgeNode
creation. It must retain source lineage. Hierarchy and prerequisite generation remain later M3 work.
