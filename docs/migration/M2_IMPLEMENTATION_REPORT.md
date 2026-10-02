# LearnPilot V1 — M2 Implementation Report

## Actual changes

- Added owner-scoped Course create, read, edit, and delete while preserving bootstrap-user ownership.
- Added MaterialContent, MaterialSummary, and StudyCard persistence through `0002_m2_course_material_ai.py`.
- Added TXT/MD/PDF/DOCX parsing with parser provenance and source-referenced segments.
- Added safe upload validation and UUID-backed storage for TXT, MD, PDF, and DOCX; PPTX remains outside M2.
- Added an OpenAI-compatible LLM adapter with bounded timeout, bounded retry, explicit mock mode, centralized versioned prompts, Pydantic structured-output validation, and safe logging.
- Replaced legacy mock summary/card behavior with persisted, traceable M2 artifacts. Mock output is available only when `LLM_MODE=mock` is selected explicitly.
- Added material-scoped lexical grounding for Q&A, including insufficient-evidence behavior and strict citation validation.
- Added the Vue Course CRUD, Course Detail, upload, Material Detail, summary, cards, and material-Q&A workflow through the typed API client.
- Completed backend formatting cleanup and the final real-provider correctness fixes without introducing M3 entities or infrastructure.

## Database migration

| Migration | Purpose |
|---|---|
| `0001_m1a_foundation.py` | Existing User/Course/Material ownership foundation |
| `0002_m2_course_material_ai.py` | Parsed content, persisted summary/cards, and recoverable M1 artifact backfill |

M2 uses SQLite as the accepted competition/demo database. Migration 0002 and the importer carry recoverable legacy extracted text, summary, and cards into M2 tables. Old mock artifacts retain `legacy-mock` provenance. A truncated saved excerpt becomes `LEGACY_CONTENT_PARTIAL`; missing saved text becomes `LEGACY_CONTENT_UNAVAILABLE`. Neither state permits new AI generation until the source is re-uploaded.

Final post-provider fresh Alembic rerun: **PASS**. A fresh isolated SQLite database applied `0001` and then `0002`; Alembic reported `0002_m2_course_material_ai` as head.

## Parser verification

| Format | Upload policy | Parser | Final result |
|---|---|---|---|
| TXT | Allowed | UTF-8 normalized text | PASS |
| MD | Allowed | UTF-8 normalized text | PASS |
| PDF | Allowed | PyMuPDF, page-aware segments | PASS |
| DOCX | Allowed | python-docx paragraphs and tables | PASS |
| PPTX | Not enabled | Not implemented | OUT OF SCOPE |

The real-provider acceptance fixture was a short, self-authored two-page PDF. Upload validation, local storage, PDF parsing, persisted text, two page-aware segments, and `page_count = 2` all passed. No copyrighted textbook or large test artifact was added to Git.

## AI configuration

Runtime configuration was read in real provider mode:

| Setting | Status |
|---|---|
| `LLM_MODE` | `provider` |
| Provider | OpenAI-compatible (DeepSeek endpoint) |
| Model | `deepseek-flash` |
| API key | CONFIGURED — VALUE NEVER RECORDED |
| Timeout | CONFIGURED and bounded |
| Attempts | Configured bounded retry |

The API key, Authorization header, Base URL, and `.env` contents were never printed, copied into documentation, logged, or added to Git. No silent mock fallback was used in final acceptance.

## Real Provider Final Acceptance

A temporary course named `M2 Real Provider Acceptance` and the self-authored two-page cache PDF were used to validate the complete real-provider path. The second page contained the only LRU eviction statement, allowing page-grounding to be checked without relying on model world knowledge.

| Acceptance item | Result | Evidence |
|---|---|---|
| Provider mode and non-mock provenance | PASS | Runtime mode was `provider`; persisted provider/model provenance was non-mock |
| Real structured summary | PASS | POST succeeded after the bounded-retry compatibility fix and retest; Pydantic validation passed |
| Summary persistence | PASS | GET returned persisted `summary_v1`; refresh and backend restart did not regenerate |
| Real structured study cards | PASS | POST succeeded; ordered, non-empty cards passed Pydantic validation |
| Card persistence and provenance | PASS | Cards persisted with non-mock provider/model and `cards_v3` |
| Card source validation | PASS | Canonical references matched actual selected PDF page labels; unknown references remain rejected |
| Grounded supported Q&A | PASS | The LRU question was answered from selected material context |
| PDF page citation | PASS | The supported answer cited the actual `PDF 第 2 页` segment |
| Insufficient evidence | PASS | The Transformer question returned insufficient evidence rather than general model knowledge |
| Browser real-provider flow | PASS | Course → Material Detail → Summary → Cards → Q&A rendered correctly in provider mode |
| Browser refresh behavior | PASS | Refresh performed GET-only artifact loading and did not repeat paid generation calls |
| Browser stability | PASS | No console errors; 1024 px inspection showed no horizontal overflow |
| Backend restart persistence | PASS | Course, material, content, summary, and cards remained available after restart |
| Cleanup behavior | PASS | Temporary material/course deletion and storage-file cleanup passed |

The browser flow used the same real-provider artifacts. Summary and cards remained visible after refresh, Q&A displayed the grounded answer and citation, long-running buttons prevented duplicate submission, and provider errors did not crash Vue.

### Sanitized failure and retest record

#### Failure 1 — transient structured-output variance

- **Operation:** Summary generation
- **Failure category:** `STRUCTURED_OUTPUT`
- **Sanitized error:** HTTP 400 / `AI_INVALID_OUTPUT`: provider result did not match the expected structure.
- **Diagnosis:** A direct diagnostic using the same schema produced a raw JSON object containing all five expected summary keys and passed Pydantic validation. The initial failure was therefore classified as transient provider structured-output variance, not a schema redesign requirement.
- **Minimal fix:** Only a Pydantic `ValidationError` raised while validating `message.content` is retryable inside the existing `LLM_MAX_ATTEMPTS` boundary. Invalid outer HTTP-200 envelopes/bodies and 4xx responses remain nonretryable.
- **Retest result:** PASS. A real summary was validated and persisted with `summary_v1` provenance.

#### Failure 2 — bracketed card references

- **Operation:** Study-card generation
- **Failure category:** `STRUCTURED_OUTPUT` / citation compatibility
- **Sanitized error:** The provider returned valid page labels wrapped as `[PDF 第 1 页]` or `[PDF 第 2 页]`, which did not exactly match the canonical stored labels.
- **Diagnosis:** The source page existed; only one presentation bracket pair differed.
- **Minimal fix:** The prompt now requests bare label text and is versioned `cards_v3`. The validator removes at most one outer bracket pair. Exact matches are preserved; a whitespace-only presentation variant such as `[PDF 第2页]` resolves only when it uniquely matches an actual selected segment label, and the canonical label is then exact-validated. Unknown labels, nested/malformed labels, and nonexistent pages still return `AI_INVALID_OUTPUT`; there is no regex fallback.
- **Retest result:** PASS. Real cards were validated, persisted, and retained only real page references.

No vector database, embeddings, reranker, LangChain, Agent framework, Tutor, or M3 knowledge model was introduced.

## Course, materials, AI, and frontend outcome

| Area | Implemented path | Verification |
|---|---|---|
| Course CRUD | Owner-scoped create/list/detail/edit/delete through API and Vue workspace | PASS, including temporary acceptance-course cleanup |
| Materials | TXT/MD/PDF/DOCX upload, parse state, content persistence, detail, and delete | PASS |
| Summary | Structured, versioned, persisted artifact with bounded full-input processing | PASS with real provider |
| Cards | Multiple validated, ordered, persisted cards using actual source labels | PASS with real provider |
| Material Q&A | Current-material lexical context, insufficient-evidence response, and exact source validation | PASS with real provider |
| Frontend | Typed Course/Material/AI workflow, truthful loading/empty/error states | Browser provider flow PASS |

## Current verification

| Check | Status |
|---|---|
| Complete backend pytest suite, including legacy regression | PASS: 75/75 |
| `ruff check backend` | PASS |
| `ruff format --check backend` | PASS |
| Real-provider summary/cards/Q&A smoke flow | PASS |
| Real-provider browser flow, refresh, 1024 px layout, console | PASS |
| Backend restart persistence | PASS |
| Fresh isolated SQLite Alembic 0001→0002 after final fixes | PASS; head = `0002_m2_course_material_ai` |
| Frontend Vitest after final fixes | PASS: 17/17 across 6 files |
| Frontend typecheck / lint / production build after final fixes | PASS / PASS / PASS (Vite 6.4.3) |
| Frontend bundle warning | PRESENT; nonblocking main-chunk size warning |
| MySQL live connection/migration | DEFERRED by current project policy |

## M2 Post-Acceptance Quality Audit

The post-acceptance audit retained the original 75/75 backend and 17/17 frontend M2 acceptance records above, then added focused regression coverage without entering M3 scope.

| Audit item | Result | Evidence |
|---|---|---|
| `cards_v3` consistency | PASS | `cards_v3` remains the sole active Study Card prompt/provenance version; database, API, and frontend card fields remain aligned |
| Structured-output retry | PASS | Invalid JSON and Pydantic/schema mismatches retry only inside the bounded provider-content path; 400/401/403 remain nonretryable |
| Schema mismatch recovery | PASS | A valid-JSON but invalid-schema first response followed by a valid second response succeeds |
| PDF citation normalization | PASS | `[PDF 第2页]` resolves only through a unique actual-reference match; `[PDF 第99页]` and nested forms are rejected |
| Citation validation boundary | PASS | Canonicalization does not use regex or bypass exact membership in the selected source set |
| Complete backend regression after audit | PASS: 78/78 | Includes the new retry and citation cases |
| Complete frontend regression after audit | PASS: 17/17 across 6 files | No frontend behavior regressed |
| M3 scope | NOT ENTERED | Audit was limited to consistency, documentation, and minimal regression correctness |

## Breaking changes

- PDF/DOCX files use parser-derived explicit statuses; corrupt files return parse-specific states rather than a broad unsupported status.
- Summary and cards POST endpoints generate validated, persisted M2 artifacts; explicit mock output remains labeled mock.
- Invalid card and Q&A citations are rejected instead of silently accepted. A single presentation-only outer bracket pair is canonicalized before exact validation.
- PPTX is not accepted because M2 has no PPTX parser.
- Legacy partial/unavailable text remains explicit and requires re-upload for new AI generation.

## User worktree and secret preservation

The known user assets remain untouched:

- `backend/app/data/courses.json`
- `scripts/start_dev.sh`

No Git reset, clean, restore, checkout, stash, commit, tag, branch switch, or push was used. The local `.env` remains ignored. No API key, provider secret, database secret, uploaded acceptance PDF, generated database, or temporary upload was added to the repository.

## Known limitations

1. Material Q&A remains lightweight, single-material lexical grounding. It is intentionally not vector RAG, course-wide search, or AI Tutor behavior.
2. MySQL live verification is **DEFERRED**. SQLite is the accepted competition/demo database for the current milestone.
3. PPTX, OCR, macros, embedded media, and image extraction are out of scope.
4. Authentication remains out of scope; current demo data uses the bootstrap ownership model.
5. The production frontend build retains a nonblocking main-chunk warning above 500 kB.
6. Legacy material with partial or unavailable saved text requires re-upload for new AI operations.
7. Summary input beyond `LLM_SUMMARY_MAX_INPUT_CHARS` fails explicitly with `AI_INPUT_TOO_LARGE`.


## Final M2 decision

- M2 status: **COMPLETE**
- LearnPilot V1 project progress: **25%**
- M3 readiness: **READY**
- Scope violation: **NO**

No M3 implementation was started.

## M3 entry conditions

1. Preserve the verified Course, Material, parsed-content, AI-artifact, and source-reference contracts.
2. Obtain explicit user approval before introducing KnowledgeNode, KnowledgeEdge, prerequisites, diagnosis, mastery, or any other M3+ capability.
