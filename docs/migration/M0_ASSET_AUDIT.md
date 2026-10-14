# LearnPilot V1 — M0 Asset Audit

Audit date: 2026-09-21

Scope: LearnPilot baseline only. No business code, dependency version, database schema, Git history, tag, branch, commit, push, reset, clean, checkout, restore, or stash was changed.

## 1. Executive Summary

M0 is complete. LearnPilot is a runnable FastAPI prototype, not a production AI learning system. It serves one native browser workspace backed by JSON and implements seeded course/material reads, TXT/MD upload/extraction, keyword search, deterministic mock summaries, and deterministic mock cards.

Backend dependency installation, application import, server startup, static frontend delivery, live GET APIs, and all 23 existing HTTP integration tests passed in an isolated Python 3.14 environment. There is no frontend package/build/test system, database, ORM, migrations, authentication, real LLM, AI Chat, PDF/DOCX/PPTX parser, or LearnPilot Diagnose/Mastery/Progress domain.

M1 readiness is NOT READY. P0-001 requires an approved persistent data, ownership, and migration foundation before M1 code changes.

## 2. Repository Status

Initial commands executed:

    git status --short --branch
    git branch --show-current
    git log --oneline -10

| Item | Evidence |
|---|---|
| Repository | /home/qxrrr/projects/learnpilot |
| Branch | main |
| Upstream state | ahead of origin/main by 1 commit |
| Initial state | WORKTREE_DIRTY |
| User-modified tracked files | backend/app/data/courses.json; scripts/start_dev.sh |
| Initial untracked files | None |
| Whitespace check | PASS: git diff --check emitted no errors |
| HEAD | cf7e54b refactor frontend around learning workflow |

No Git state was altered and no tag/branch was created.

Recent history:

    cf7e54b refactor frontend around learning workflow
    946eacb add demo data and startup guide
    201ddd0 polish frontend demo experience
    3fa9953 add minimal frontend page
    205c005 polish Chinese-first project documentation
    a572caa polish Chinese-first project documentation
    6977c2c prepare LearnPilot v0.1 release
    d45373e add project documentation and demo materials
    5f62e8a add study card generation API
    ff9f36d add material search API

## 3. Current Architecture

    learnpilot/
    ├── frontend/                   Native HTML/CSS/JavaScript workspace
    ├── backend/
    │   ├── main.py                 FastAPI and static-file mount
    │   ├── app/api/                Course/material/system routers
    │   ├── app/core/               Application constants
    │   ├── app/data/courses.json   Demo persistence
    │   ├── app/schemas/            Pydantic API schemas
    │   ├── app/services/           JSON/upload/parser/mock-AI services
    │   └── tests/                  unittest HTTP integration suite
    ├── docs/
    ├── scripts/start_dev.sh
    ├── requirements.txt
    └── .gitignore

Runtime flow:

    native frontend -> same-origin fetch -> FastAPI router -> service
    -> courses.json and backend/app/uploads/

The frontend is mounted by FastAPI. There is no separate frontend server, framework, state/API library, cache, queue, Docker/deployment manifest, database, or LLM adapter.

## 4. Technology Stack

| Area | Confirmed technology | Version/status | Evidence |
|---|---|---|---|
| Backend | FastAPI | requirements >=0.100; audit install 0.141.1 | requirements.txt; backend/main.py |
| ASGI | Uvicorn | >=0.23; audit install 0.53.0 | requirements.txt; start_dev.sh |
| Validation | Pydantic | audit install 2.13.5 | schemas/course.py |
| Multipart | python-multipart | >=0.0.6; audit install 0.0.32 | requirements.txt |
| Frontend | Native HTML/CSS/JavaScript | No framework/build tool | frontend/ |
| Persistence | Local JSON and local files | No DB/ORM/migrations | course_service.py |
| AI | Local mock rules | No provider/key/prompt | summary_service.py; card_service.py |
| Tests | unittest | 23 integration tests | backend/tests/test_courses_api.py |
| Container/deploy | None | NOT CONFIGURED | repository scan |

requirements have open lower bounds and no lockfile. Resolved audit versions are environmental facts, not project pins.

## 5. Frontend Audit

| Check | Result | Evidence |
|---|---|---|
| Dependency Install | NOT AVAILABLE | No package.json or lockfile. |
| Lint | NOT AVAILABLE | No configuration/script. |
| Test | NOT AVAILABLE | No frontend test setup. |
| Production Build | NOT AVAILABLE | No build system/script. |
| Dev Server | PASS | FastAPI served root as 200 HTML and app.js/styles.css as 200 on 127.0.0.1:8011. |
| Browser E2E | NOT VERIFIED | No browser suite exists; M0 did not add one. |

The page provides course select, material read, TXT/MD upload, summary/card actions, and search. All fetches use one api helper in frontend/app.js:4. The UI accepts only TXT/MD while the backend allowlist is broader.

## 6. Backend Audit

| Check | Result | Evidence |
|---|---|---|
| Dependency Install | PASS | Existing requirements installed in isolated /tmp environment. |
| Application Import | PASS | backend.main:app imported as LearnPilot API 0.1.0; 7 top-level routes. |
| Server Startup | PASS | Uvicorn served static assets, health, API, docs and OpenAPI. |
| Tests | PASS WITH WARNING | 23 tests passed in 11.612 seconds; ResourceWarning for unclosed HTTPError paths. |

Router/service separation is reusable at prototype scale. course_service.py combines persistence, upload, ID allocation, lookup, update and search, so it must be split with the V1 data layer. GET /hello is not callable: StaticFiles mounted at slash is registered before it; live request returned 404. Recorded as TD-011, not fixed.

## 7. Database Audit

Database type: none. Persistence is backend/app/data/courses.json plus backend/app/uploads/. No connection configuration, ORM, repository, database dependency, migration directory, or migration tool exists.

DATABASE_CONNECTION_NOT_VERIFIED: no database is configured to connect.

| Model/Table | Purpose | Relations | Status |
|---|---|---|---|
| Course JSON object | Demo catalog | Course ID keys a material array | JSON only |
| Material JSON object | Metadata, file ref, preview, mock outputs | Nested in materials[course_id] | JSON only |
| StudyCard JSON object | Question/answer | Nested in material | JSON only |
| User | Ownership/identity | None | NOT IMPLEMENTED |
| Conversation/Message | Tutor history | None | NOT IMPLEMENTED |
| Summary artifact | Versioned output | Embedded material fields only | NOT IMPLEMENTED |

There are no constraints, indexes, transactions, concurrency controls, migrations, ownership, backup, or recovery policy.

## 8. AI / LLM Audit

| Capability | Status | Evidence |
|---|---|---|
| LLM base call | NOT_IMPLEMENTED | No provider SDK/import/configuration/secret variable. |
| Prompt/structured output/retry/timeout | NOT_IMPLEMENTED | No prompt store, output contract, retry, timeout or adapter. |
| AI Chat | NOT_IMPLEMENTED | No UI, API, service, model or message store. |
| Summary | PARTIAL | UI/API chain exists; summary_service.py creates Mock summary by truncating local text. |
| Learning Cards | PARTIAL | UI/API chain exists; card_service.py creates three fixed deterministic cards. |
| File AI analysis | PARTIAL | TXT/MD reaches local mock only; no content reaches an LLM. |

No real API key was read or output. No LLM secret is currently needed because no provider is integrated.

## 9. Document Processing Audit

| Type | Upload | Parse | Store | AI Usage | Verified |
|---|---|---|---|---|---|
| TXT | Implemented | UTF-8; first 300 chars preview | JSON metadata plus file | Local mock only | VERIFIED |
| MD | Implemented | Same as TXT | JSON metadata plus file | Local mock only | VERIFIED |
| PDF | Extension allowlist | NOT IMPLEMENTED | JSON metadata plus file | No usable text | Upload/storage verified; parse-negative verified |
| DOCX | IMPLEMENTED_NOT_VERIFIED allowlist | NOT IMPLEMENTED | IMPLEMENTED_NOT_VERIFIED | No usable text | No direct runtime test |
| PPTX | IMPLEMENTED_NOT_VERIFIED allowlist | NOT IMPLEMENTED | IMPLEMENTED_NOT_VERIFIED | No usable text | No direct runtime test |
| DOC/PPT | IMPLEMENTED_NOT_VERIFIED allowlist | NOT IMPLEMENTED | IMPLEMENTED_NOT_VERIFIED | No usable text | No direct runtime test |

text_extraction_service.py supports only TXT and MD. The PDF test explicitly asserts extracted false and text length 0. PDF, DOCX and PPTX are not parsable despite upload allowlisting.

Upload has extension allowlisting and basename sanitization, which mitigate basic path traversal. Missing controls: MIME/signature checks, byte/stream limits, quota, malware policy, collision handling, deletion lifecycle, temporary-file policy and Unicode-name preservation. Empty files are accepted; invalid UTF-8 returns extracted false without a reason.

## 10. API Inventory

| Method | Path | Handler | Service | Purpose | Verified |
|---|---|---|---|---|---|
| GET | / | StaticFiles mount | N/A | Serve frontend | VERIFIED: 200 |
| GET | /api | routes.root | N/A | API metadata | VERIFIED: 200 |
| GET | /health | routes.health_check | N/A | Health | VERIFIED: 200 |
| GET | /api/project/status | routes.project_status | N/A | Hard-coded demo status | VERIFIED: 200 |
| GET | /api/courses | courses.list_courses | list_courses | List courses | VERIFIED |
| GET | /api/courses/{course_id} | courses.get_course_detail | get_course | Read course | VERIFIED |
| GET | /api/courses/{course_id}/materials | courses.list_course_materials | list_materials | List materials | VERIFIED |
| POST | /api/courses/{course_id}/materials | courses.create_course_material | create_material | Create JSON material | VERIFIED |
| POST | /api/courses/{course_id}/materials/upload | courses.upload_course_material | create_uploaded_material | Upload/register | VERIFIED for TXT/MD/PDF |
| GET | /api/materials/search | materials.search_course_materials | search_materials | Keyword search | VERIFIED |
| POST | /api/materials/{material_id}/summary | materials.generate_material_summary | generate_mock_summary/update_material | Persist mock summary | VERIFIED |
| POST | /api/materials/{material_id}/cards | materials.generate_material_cards | generate_mock_cards/update_material | Persist mock cards | VERIFIED |
| GET | /hello | main.hello | N/A | Legacy greeting | FAIL: runtime 404 |

## 11. Existing Feature Inventory

| Feature | Decision | Current state | Reason, risk, recommendation |
|---|---|---|---|
| Health/API metadata | KEEP | Runtime verified | Valid operational asset; retain under V1 API convention. |
| Native workspace shell | REFACTOR | Static verified; browser E2E not verified | Useful workflow but one LearnPilot page cannot express five V1 modules. |
| Seeded course catalog | REFACTOR | Verified | Correct Course start but read-only demo JSON has no CRUD/ownership/lifecycle. |
| Materials | REFACTOR | Verified | JSON cannot support relations, revision, ownership, scale or concurrency. |
| File upload/storage | REFACTOR | Partial verified | Valuable Course asset but insecure/unbounded and parser coverage is inadequate. |
| TXT/MD extraction | REFACTOR | Verified | Reuse only as baseline; add normalized content, provenance/errors and production parsers. |
| Mock summary | REFACTOR | Mock verified | Correct destination but not AI; replace behind provider adapter. |
| Mock cards | REFACTOR | Mock verified | Fixed questions lack quality control, provenance and learner interaction. |
| Keyword search | REFACTOR | Verified | Useful precursor but linear JSON scan cannot scale or provide File QA. |
| Project status/hello | DEPRECATE | Status 200; hello 404 | Stale demo data and unreachable endpoint conflict with V1. |

## 12. End-to-End Verification

| Chain | Code integration | Runtime evidence | Verdict |
|---|---|---|---|
| Page load -> courses -> JSON | app.js:24 -> router -> service -> JSON | Static root/assets and live courses GET 200 | Backend/static VERIFIED; browser action NOT VERIFIED |
| Course select -> materials -> JSON | app.js:16/17 -> router -> service | HTTP integration tests | Code integrated; backend VERIFIED |
| TXT/MD upload -> extract -> JSON/file | app.js:20 -> router -> services | Upload/restart tests | Code integrated; backend VERIFIED |
| Learning pack -> summary/cards -> JSON | app.js:22 -> router -> mock services | Persistence/repeat tests | Code integrated; mock workflow VERIFIED |
| Search -> search service -> JSON | app.js:18 -> router -> service | Search tests | Code integrated; backend VERIFIED |
| AI Chat -> LLM -> UI | None | None | NOT IMPLEMENTED |

Integrated means source paths align and HTTP behavior was tested. It is not browser E2E or real-LLM verification.

## 13. Security Findings

| Finding | Status | Evidence |
|---|---|---|
| Tracked secret scan | No potential secret found | Sensitive-pattern scan had no file:line hits; no .env file found. Not a history/deployed audit. |
| Secret ignore | Acceptable now | .gitignore ignores .env and .env.*; no provider exists. |
| Runtime data ignore | Partial | .venv, bytecode, pytest cache/uploads ignored; node_modules/dist not ignored but absent. |
| Path traversal | Partially mitigated | Upload normalizes basename. |
| Content controls | High risk | Extension-only and unbounded; TD-002. |
| Server path disclosure | High risk | Material responses expose file_path; TD-006. |
| Authentication | Missing | Global numeric IDs with no identity/access control; TD-007. |
| CORS | Not configured | Same-origin now; production topology needs explicit allowlist. |

## 14. Test & Quality Status

| Area | Status | Evidence |
|---|---|---|
| Backend integration | PASS WITH WARNING | 23/23 unittest tests pass using isolated data/upload paths. |
| API shape validation | PARTIAL | Pydantic shapes only; no semantic limits/content constraints. |
| Frontend tests | NOT CONFIGURED | No setup found. |
| Browser E2E | NOT CONFIGURED | No automation configuration. |
| Lint/format/type check | NOT CONFIGURED | No ESLint/Prettier/Ruff/Black/mypy equivalent. |
| Dependency consistency | PASS | pip check found no broken audit requirements. |
| Reproducible resolution | FAIL | Lower bounds only; no lockfile. |
| Docker/deployment | NOT AVAILABLE | No related files. |

## 15. LearnPilot → LearnPilot Mapping

| LearnPilot Feature | Current Implementation | LearnPilot Destination | Decision |
|---|---|---|---|
| Health/API metadata | FastAPI lightweight endpoints | Platform/operations | KEEP |
| Native study workspace | One static LearnPilot page | Dashboard, Course, Learn | REFACTOR |
| Course list | Read-only seed JSON | Course | REFACTOR |
| Materials/upload | JSON metadata/local filesystem | Course / Materials | REFACTOR |
| TXT/MD extraction | UTF-8 preview extractor | Course / Materials processing | REFACTOR |
| Mock summary | Deterministic truncation | Course / Materials | REFACTOR |
| Mock cards | Three-card deterministic generator | Course / Materials then Learn | REFACTOR |
| Keyword search | Linear JSON substring scan | Course / Materials / File QA | REFACTOR |
| Project status/hello | Demo metadata; unreachable route | None | DEPRECATE |
| Real LLM/Tutor | Absent | Learn / Tutor | NEW |
| Diagnosis/evidence | Absent | Diagnose | NEW |
| Knowledge/mastery | Absent | Knowledge Model / Mastery | NEW |
| Adaptive Learn/Progress | Absent | Learn / Progress | NEW |

## 16. LearnPilot V1 Gap Analysis

| V1 Module | Status | Evidence/gap |
|---|---|---|
| Dashboard | Missing | No learner overview, metrics, tasks or alerts. |
| Course | Partial | Seed materials/upload/search/mock outputs; no CRUD, ownership, robust parsers or File QA. |
| Diagnose | Missing | No test, question, response, score or Learning Evidence. |
| Knowledge Model | Missing | No node, edge, prerequisite, extraction or graph persistence. |
| Mastery | Missing | No score, confidence, aggregation or snapshot. |
| Learn | Missing | No recommendation, session, adaptive exercise, tutor or real LLM. |
| Progress | Missing | No trends, weak areas, history or review risk. |
| Platform data/security | Missing | No database, migrations, users, authorization, storage abstraction, audit logs or observability. |

## 17. Blocking Issues

1. P0-001: no durable relational data model, ORM, migration path, user ownership, or concurrency control. V1 domains cannot safely share the JSON shape.
2. P1-002: extension-only/unbounded upload is unacceptable for untrusted V1 materials.
3. P1-003/P1-004: real LLM and production parser strategies are absent, so Course AI analysis cannot be validated.

## 18. Recommended M1 Entry Conditions

1. Preserve/review the two user modifications before any tag, branch or baseline commit.
2. Approve persistence, ownership, migrations, JSON import, backup and local configuration design.
3. Approve upload types, byte limits, content verification, storage, collision, malware, retention and path-redaction policy.
4. Define provider adapter, secret variable names only, timeout/retry/observability, prompt versioning and structured-output contracts.
5. Define Dashboard/Course/Diagnose/Learn/Progress domain and route boundaries.
6. Add locked dependencies, frontend checks, backend lint/format/type checks, browser E2E and CI.

When the worktree is clean and HEAD is intentionally selected, a future maintainer may consider:

    git tag campusai-v0
    git switch -c learnpilot-v1

This audit did not execute either command.

## 19. Final M0 Verdict

M0 baseline is COMPLETE: assets were inventoried, existing behavior was verified, unverified items are explicit, and no product implementation was changed.

| Acceptance question | Answer |
|---|---|
| Frontend start? | PASS as FastAPI-served static frontend; no standalone frontend process. |
| Frontend production build? | NOT AVAILABLE: no build system. |
| Backend start? | PASS. |
| Database connect? | DATABASE_CONNECTION_NOT_VERIFIED: no database configured. |
| LLM connected? | NOT IMPLEMENTED. |
| File upload usable? | PARTIAL: TXT/MD/PDF backend verified; DOCX/PPTX no direct test; controls insufficient. |
| PDF parse? | NOT IMPLEMENTED; upload-only behavior verified. |
| DOCX parse? | NOT IMPLEMENTED. |
| TXT parse? | VERIFIED. |
| AI summary? | PARTIAL: mock verified; AI/LLM not implemented. |
| Learning cards? | PARTIAL: mock verified; AI-generated cards not implemented. |
| AI Chat? | NOT IMPLEMENTED. |
| Integrated links? | Course/material reads, TXT/MD upload, mock summary/cards and search; backend verified. |
| Code-only/unverified? | DOCX/PPTX upload behavior and browser interaction. |
| Mock data? | Seed courses/materials and all summary/card artifacts. |
| Reusable assets? | Health/API docs, router/service split, Course/Materials intent, upload flow, TXT/MD baseline, search, test isolation. |
| Must refactor? | UI, data/AI features, JSON persistence, file handling and mock generators. |
| Deprecate? | Hard-coded status and unreachable hello route. |
| V1 gaps? | Dashboard, Course CRUD, Diagnose, Evidence, Knowledge, Mastery, Learn/Tutor, Progress, DB/auth/LLM/parsers/File QA. |
| P0 blocking M1? | YES: durable data/migration/ownership foundation. |

LearnPilot V1 project progress after completed M0: 5%.
