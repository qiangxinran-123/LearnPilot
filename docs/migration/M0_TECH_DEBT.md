# LearnPilot V1 — M0 Technical Debt Register

## TD-001

Priority: P0

Area: Data architecture

Description: The application has no database, ORM, migrations, user ownership, relation constraints, transaction boundary, or concurrent-write control. Courses, materials, mock summaries, and cards are nested in one JSON document.

Evidence: requirements.txt contains only FastAPI, Uvicorn and python-multipart. backend/app/services/course_service.py:11-14 defines JSON/file paths; load/save replaces the whole JSON file. No database or migration directory exists.

Impact: LearnPilot Course, Material, Knowledge Node, Evidence, Mastery, Session, and Progress cannot be safely related, evolved, queried, or isolated by learner. Concurrent writes can lose data. This blocks the M1 data contract.

Recommended Resolution Stage: M1 entry gate — approve persistent store, ownership, migration, backup, and JSON-import design before refactoring.

## TD-002

Priority: P1

Area: File upload security

Description: Upload checks only filename extension. There is no byte-size limit, MIME/signature inspection, stream limit, quota, malware policy, content-type enforcement, collision strategy, or retention/deletion flow.

Evidence: backend/app/services/course_service.py:15 and :88-103 allow extensions then copy the incoming stream directly to local disk.

Impact: A V1 deployment accepting untrusted material can suffer disk exhaustion, deceptive content, filename collision/overwrite, and ungoverned retained data.

Recommended Resolution Stage: M1 foundation, before opening material upload beyond controlled development.

## TD-003

Priority: P1

Area: AI/LLM

Description: Summary and card outputs are deterministic mock rules, not LLM calls. There is no provider adapter, prompt versioning, structured output, timeout, retry, safety handling, tracing, cost control, or secret configuration.

Evidence: backend/app/services/summary_service.py:7 and :30-41 use SUMMARY_METHOD mock and truncate text. backend/app/services/card_service.py:5-56 uses fixed questions and CARD_METHOD mock. No provider SDK/import/configuration exists.

Impact: The product cannot deliver or evaluate AI summaries, cards, File AI analysis, Tutor, or learning evidence. UI must remain transparently labeled mock.

Recommended Resolution Stage: M1 architecture; M2 implementation after provider, secret, observability, and output-contract approval.

## TD-004

Priority: P1

Area: Document processing

Description: Text extraction supports only UTF-8 TXT and MD. PDF, DOC, DOCX, PPT, and PPTX are accepted by upload but deliberately return no text.

Evidence: backend/app/services/text_extraction_service.py:4 lists only TXT/MD. The broader upload set is in course_service.py:15. test_upload_pdf_file_succeeds_without_text_extraction asserts extracted false.

Impact: Standard university materials cannot feed summary, cards, content search, File QA, knowledge extraction, or diagnostic generation.

Recommended Resolution Stage: M1 parser/storage interface; M2 parser implementation with corrupt/Unicode/empty/malicious-file tests.

## TD-005

Priority: P1

Area: Dependency reproducibility

Description: Dependencies have open lower bounds with no lockfile and there is no declared Python compatibility range.

Evidence: requirements.txt has fastapi >=0.100, uvicorn >=0.23, and python-multipart >=0.0.6 only. M0 used Python 3.14.4 successfully, which is not a project compatibility guarantee.

Impact: Future installs can resolve different incompatible dependency sets, preventing reproducible builds and baseline comparison.

Recommended Resolution Stage: M1 engineering foundation and CI.

## TD-006

Priority: P1

Area: API data exposure

Description: Material responses include file_path, which persists and returns a server filesystem path.

Evidence: backend/app/schemas/course.py:25-26 declares file_path. backend/app/services/course_service.py:110-112 stores str(destination); course routes return the Material schema.

Impact: Clients can learn internal filesystem layout and become coupled to local storage implementation.

Recommended Resolution Stage: M1 API contract refactor.

## TD-007

Priority: P1

Area: Authentication and authorization

Description: There is no user identity, session, authorization check, tenant ownership, or access policy.

Evidence: No authentication dependency, schema, router, service, or configuration exists. Course/material APIs operate against global JSON by numeric IDs.

Impact: A multi-user LearnPilot cannot protect materials, diagnosis, Tutor history, evidence, or mastery data.

Recommended Resolution Stage: M1 domain/security design before multi-user features.

## TD-008

Priority: P2

Area: Frontend maintainability

Description: Interactive state, rendering, networking, event registration, and workflow behavior reside in one 24-line minified app.js. styles.css is also minified into one physical line.

Evidence: frontend/app.js is 12,071 bytes over 24 lines; frontend/styles.css is 9,714 bytes with no trailing newline.

Impact: Review, debugging, testing, and migration into Dashboard/Course/Diagnose/Learn/Progress modules are unnecessarily difficult.

Recommended Resolution Stage: M1 frontend shell refactor; preserve verified behavior first.

## TD-009

Priority: P2

Area: Observability and error handling

Description: There is no application logging, request correlation, global exception handling, structured error model, or extractor failure reason. The extractor suppresses OSError and UnicodeError.

Evidence: backend/app/services/text_extraction_service.py:15-22 catches errors and returns extracted false without logging. No logging or exception-handler configuration was found.

Impact: Operations cannot diagnose upload, persistence, parser, or future LLM failures.

Recommended Resolution Stage: M1 platform foundation.

## TD-010

Priority: P2

Area: Input validation and data quality

Description: MaterialCreate validates only field shape; it has no semantic length/type allowlist, whitespace normalization, duplicate rule, content constraints, or schema version. Card IDs derive from material_id multiplied by 100 plus index.

Evidence: backend/app/schemas/course.py:40-43; backend/app/services/course_service.py:68-85; backend/app/services/card_service.py:40-49.

Impact: Invalid or oversized metadata, future ID collisions, and incompatible records become harder to migrate and validate.

Recommended Resolution Stage: M1 domain model design.

## TD-011

Priority: P2

Area: Routing

Description: The root StaticFiles mount is registered before GET /hello, so the static mount catches the request and the declared route is unreachable.

Evidence: backend/main.py:18 mounts slash and backend/main.py:21 declares hello. M0 live request to 127.0.0.1:8012/hello returned 404 JSON.

Impact: Source API inventory differs from callable inventory; future routes after a catch-all mount can silently fail.

Recommended Resolution Stage: M1 routing consolidation.

## TD-012

Priority: P2

Area: Test quality

Description: The 23-test suite passes but emits ResourceWarning messages for implicitly cleaned HTTPError objects. It lacks DOCX/PPTX upload, file-size/content, browser, concurrent-write, database, authorization, real LLM, and parser-quality coverage.

Evidence: M0 command python -m unittest backend.tests.test_courses_api -v completed 23 tests with ResourceWarning. backend/tests/test_courses_api.py has no DOCX/PPTX test.

Impact: Passing tests can give false confidence outside the narrow prototype flow.

Recommended Resolution Stage: M1 test foundation; M2 feature-specific suites.

## TD-013

Priority: P2

Area: Documentation/version coherence

Description: User-facing version/status values disagree: config says 0.1.0, README says V0.3, and project status hard-codes backend-basic-structure and 18%.

Evidence: backend/app/core/config.py:1-3; README.md:21; backend/app/api/routes.py:29-41.

Impact: Stakeholders and automation cannot rely on a single version/progress source.

Recommended Resolution Stage: M1 release/documentation process.

## TD-014

Priority: P3

Area: Cross-origin deployment readiness

Description: No explicit CORS policy exists.

Evidence: No CORSMiddleware usage was found. The current frontend and API are same-origin under FastAPI, and M0 observed no active CORS failure.

Impact: A later separated frontend/API deployment needs an explicit origin allowlist and credential policy.

Recommended Resolution Stage: When deployment topology is selected.
