# LearnPilot V1 — M2 Course & Materials Architecture

## 1. Scope

M2 turns the course list into a real course and learning-material workspace. It includes Course CRUD, secure TXT/MD/PDF/DOCX upload, durable parsed content, structured material summaries, study cards, and question answering grounded in one material.

M2 does not implement KnowledgeNode, KnowledgeEdge, a knowledge graph, diagnosis, mastery, recommendation, learning sessions, AI Tutor, vector RAG, progress analytics, authentication, MySQL live deployment, or PPTX parsing.

## 2. Course and material domain

~~~text
User
  1
  |
  N
Course
  1
  |
  N
Material
  |-- 1 MaterialContent
  |-- 0..1 MaterialSummary
  '-- N StudyCard
~~~

The existing `owner_id` invariant remains mandatory. API access uses the explicit legacy bootstrap user until authentication is introduced.

`MaterialContent` persists normalized text, SHA-256 content hash, parser provenance, page count, and source-referenced segments. `MaterialSummary` stores a structured one-to-one learning summary and provider/model/prompt provenance. `StudyCard` persists a validated, ordered card set per material with source references and AI provenance.

Migration 0002 and the JSON importer backfill recoverable M1 extracted text, summaries, and cards with `m1-legacy` or `legacy-mock` provenance. A truncated old excerpt is `LEGACY_CONTENT_PARTIAL`; absent old extracted text is `LEGACY_CONTENT_UNAVAILABLE`. Both require re-upload before new AI generation. M3+ entities are intentionally absent.

## 3. Boundaries and API

~~~text
Vue view -> typed service -> FastAPI router -> domain service -> repository -> SQLAlchemy
                                        |                         |
                                        |                         +-> LocalFileStorage
                                        +-> MaterialAIService -> LLM adapter
~~~

Routers map HTTP only. `CourseService` owns course/material lifecycle and transaction coordination. Repositories own SQLAlchemy persistence. `MaterialAIService` owns summary, cards, and material Q&A. Provider-specific HTTP is isolated in `backend/app/ai/client.py`.

M2 endpoints include:

- `POST /api/courses`, `PATCH /api/courses/{course_id}`, `DELETE /api/courses/{course_id}`
- `GET /api/materials/{material_id}`, `DELETE /api/materials/{material_id}`
- `GET /api/materials/{material_id}/content`
- `GET` and `POST /api/materials/{material_id}/summary`
- `GET` and `POST /api/materials/{material_id}/cards`
- `POST /api/materials/{material_id}/qa`

Existing course/material list, detail, and upload paths remain compatible. Public responses never expose `storage_key`, storage roots, or absolute filesystem paths.

## 4. Parsing and storage

~~~text
Upload -> filename/type/signature/size validation -> UUID storage key
       -> parse once -> normalize -> persist Material + MaterialContent
       -> reuse parsed content for preview, summary, cards, and Q&A
~~~

TXT and MD require UTF-8 and normalize line endings. PyMuPDF extracts page-aware PDF text, retaining canonical labels such as `PDF 第 2 页`. python-docx reads paragraphs and tables without executing macros. Empty, decode, corrupt, and unsupported files receive explicit extraction states. PPTX is intentionally not accepted in M2.

`LocalFileStorage` streams uploads under the configured size limit and prevents original filenames from controlling destinations. Course/material deletion coordinates stored-file removal with metadata deletion; failures are logged and surfaced. The final acceptance used an isolated, self-authored two-page PDF and verified two persisted page segments. SQLite foreign keys remain enabled for the accepted demo database; MySQL live validation is deferred.

## 5. LLM adapter and provenance

`LLMClient.generate_structured()` is the single business-facing structured generation interface. The provider implementation is OpenAI-compatible and requires `LLM_MODE=provider` plus locally configured key, endpoint, model, timeout, and bounded attempt settings.

The adapter:

- applies a configured bounded timeout;
- retries only transient transport, rate-limit, 5xx, and the narrowly defined Pydantic validation failure raised while validating `message.content`;
- keeps outer HTTP-200 envelope/body failures and 4xx responses nonretryable;
- logs operation, safe provider/model identifiers, latency, and outcome;
- never logs credentials, Authorization headers, full prompts, or full document content;
- maps malformed or invalid final output to `AI_INVALID_OUTPUT` without persisting it.

No silent mock fallback exists. `LLM_MODE=mock` is an explicit deterministic test/development mode only. Missing provider configuration returns `AI_NOT_CONFIGURED`.

Prompt versions are:

- `summary_v1`
- `cards_v3`
- `material_qa_v1`

Summary, cards, and Q&A use Pydantic-validated structured output. Persisted summary/cards record provider, model, prompt version, and generation time. Final acceptance used provider mode with an OpenAI-compatible DeepSeek endpoint and model `deepseek-flash`; persisted provenance was confirmed non-mock. Credential values and the endpoint URL are not recorded.

## 6. AI workflows

### Summary

Short materials use normalized text directly. Longer materials use bounded map/reduce processing across all chunks up to `LLM_SUMMARY_MAX_INPUT_CHARS`. `LLM_SUMMARY_MAX_CHUNKS` limits one request batch rather than truncating the document. Larger input fails explicitly with `AI_INPUT_TOO_LARGE`.

The structured result contains overview, key concepts, important points, common mistakes, and review suggestions. It is persisted after successful validation and regenerated only after an explicit POST. In final provider acceptance, the first Summary POST exposed transient structured-output variance. The compatibility fix made only `message.content` Pydantic validation retryable within the existing attempt boundary; retest passed and persisted `summary_v1`.

### Study cards

The service selects bounded parsed chunks and requests an ordered structured card set. Each non-null `source_reference` must resolve to an actual selected segment.

The provider initially returned otherwise valid labels with one presentation bracket pair, for example `[PDF 第 2 页]`. `cards_v3` asks for bare label text. The validator removes at most one outer bracket pair. Exact matches are preserved; a presentation-only spacing variant such as `[PDF 第2页]` is resolved only when its whitespace-compacted value uniquely matches a reference in the actual selected set. The resolved canonical label must still pass exact membership validation. This is intentionally narrow:

- `[PDF 第 2 页]` and `[PDF 第2页]` resolve to the actual canonical label `PDF 第 2 页` only when that label was selected;
- `[PDF 第99页]` remains invalid when page 99 is not in the selected references;
- nested or malformed bracket forms are not repeatedly stripped;
- invalid references raise `AI_INVALID_OUTPUT`;
- no regular-expression fallback invents or bypasses a page reference;
- no invalid reference is silently converted to an absent citation.

The entire ordered replacement set is persisted atomically with provider/model/`cards_v3` provenance. Final real-provider retest passed.

### Material Q&A

M2 Q&A is material-scoped, not course-scoped and not Tutor behavior. It selects lexical matches from normalized source text. If no relevant segment exists, the service returns an insufficient-evidence response without relying on provider world knowledge.

For a grounded response, the model must cite at least one reference present in the selected context. Unknown references produce `AI_INVALID_OUTPUT`; the service never appends every retrieved source as though the model used it. PDF references remain page-aware.

The final provider acceptance asked about LRU, whose evidence existed only on page 2. The answer cited the real `PDF 第 2 页` segment. A Transformer/Multi-Head Attention question returned insufficient evidence instead of a generic explanation. This verifies the M2 grounded-product boundary without introducing vectors, embeddings, reranking, or Tutor behavior.

## 7. Frontend information architecture

- `/courses`: real course list plus loading, empty, error, and creation states.
- `/courses/:courseId`: course edit/delete and material management.
- `/courses/:courseId/materials/:materialId`: parsed content, structured summary, study cards, and current-material Q&A.

All calls pass through `src/services/http.ts` and typed domain services; Vue components do not call Axios directly. The UI uses truthful generation/loading/error states and does not display fabricated mastery, recommendation, knowledge count, or progress.

The final browser acceptance ran in real provider mode. Summary, cards, and Q&A rendered correctly; generation actions prevented duplicate submission; refresh loaded persisted artifacts with GET requests only; the console had no errors; and the 1024 px view had no horizontal overflow.

## 8. Error, security, and verification

Key API errors include `MATERIAL_NOT_PARSED`, `AI_NOT_CONFIGURED`, `AI_TIMEOUT`, `AI_RATE_LIMITED`, `AI_PROVIDER_ERROR`, `AI_INVALID_OUTPUT`, and `AI_INPUT_TOO_LARGE`. Python stack traces, credentials, storage paths, and uploaded document contents are not returned to clients.

Security invariants include filename sanitization, extension/MIME/signature checks, bounded streaming uploads, UUID storage keys, no path exposure, no macro execution, ignored local `.env`, and no client-side secret configuration.

Verified final evidence:

- real provider mode and non-mock provenance: **PASS**;
- real structured summary, persistence, and restart recovery: **PASS**;
- real study cards, `cards_v3`, strict source validation, and persistence: **PASS**;
- grounded supported Q&A, `PDF 第 2 页` citation, and insufficient-evidence behavior: **PASS**;
- temporary Course/Material deletion and storage cleanup: **PASS**;
- complete backend pytest: **75/75 PASS**;
- `ruff check backend`: **PASS**;
- `ruff format --check backend`: **PASS**;
- final real-provider browser flow: **PASS**;
- final fresh isolated SQLite Alembic 0001→0002 rerun: **PASS**; head = `0002_m2_course_material_ai`;
- final frontend Vitest **17/17 PASS** across 6 files; typecheck **PASS**; lint **PASS**; Vite 6.4.3 production build **PASS**.

The frontend production bundle warning above 500 kB is nonblocking and intentionally deferred. MySQL live verification is deferred by project policy. PPTX, OCR, authentication, vector RAG, Tutor, and M3 capabilities remain out of scope.

## 9. M3 extension point

After M2 receives formal acceptance, M3 may read Course, Material, `MaterialContent.plain_text`, source-referenced segments, parser provenance, and content hash to build a course knowledge model. M2 intentionally leaves KnowledgeNode, KnowledgeEdge, prerequisites, diagnosis, learner evidence, mastery, recommendation, and learning-session entities unimplemented.
