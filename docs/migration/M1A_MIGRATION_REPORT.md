# LearnPilot V1 — M1-A Migration Report

## Actual Changes

- Added Pydantic Settings configuration and .env.example.
- Added pinned requirements.in and fully pinned requirements.txt for Python 3.14.
- Added SQLAlchemy 2.x Base, session dependency, User/Course/Material models, repositories, and Alembic.
- Added migration 0001_m1a_foundation.
- Added request-scoped database connection lifecycle and logging/error handlers.
- Replaced JSON-backed CourseService persistence with Repository plus SQLAlchemy transactions.
- Added FileStorage and LocalFileStorage using UUID storage keys.
- Added secure upload validation, bounded streaming, basic signatures, and structured extraction statuses.
- Removed public Material file_path exposure.
- Removed deprecated unreachable GET /hello.
- Added idempotent legacy JSON importer with dry-run and optional backup.
- Migrated the 23 legacy HTTP tests to isolated relational persistence and added 10 M1-A foundation tests.
- Added Ruff and pytest configuration.

## Migration Files

| File | Purpose |
|---|---|
| alembic.ini | Alembic configuration |
| backend/alembic/env.py | Environment URL and metadata binding |
| backend/alembic/versions/0001_m1a_foundation.py | Users, courses, materials schema |

## Legacy Import Verification

A fresh temporary SQLite database was upgraded to head. The current legacy JSON then produced:

| Run | Users created | Courses created | Courses skipped | Materials created | Materials skipped | Errors |
|---|---:|---:|---:|---:|---:|---:|
| Dry run | 1 | 3 | 0 | 6 | 0 | 0 |
| Actual import | 1 | 3 | 0 | 6 | 0 | 0 |
| Repeat import | 0 | 0 | 3 | 0 | 6 | 0 |

The importer read the source without changing it and wrote the optional backup only to a temporary backup directory. No project JSON was replaced.

## Verification

| Check | Result |
|---|---|
| Alembic upgrade head on empty SQLite | PASS |
| SQLAlchemy repository persistence | PASS |
| Ownership foreign key schema | PASS |
| Legacy import dry-run | PASS |
| Legacy import actual run | PASS |
| Legacy import idempotency | PASS |
| Storage UUID collision protection | PASS |
| Upload size and path validation | PASS |
| TXT/MD extraction statuses | PASS |
| PDF secure storage with unsupported status | PASS |
| Public path redaction | PASS |
| Legacy HTTP regression tests | PASS: 23/23 |
| M1-A foundation tests | PASS: 10/10 |
| Ruff check | PASS |
| MySQL 8 live connection/migration | BLOCKED: no MySQL service or safe DATABASE_URL in environment |

## Breaking Changes

- Public Material no longer exposes file_path. This is a required security correction.
- GET /hello is removed because it was already unreachable and deprecated.
- Errors add error.code/error.message while retaining legacy detail where applicable.

## User Worktree Preservation

Initial user modifications remained untouched:

- backend/app/data/courses.json
- scripts/start_dev.sh

M1-A also preserves the prior untracked M0 reports. No destructive Git operation, commit, tag, branch switch, push, or source JSON overwrite occurred.

## Remaining Risks

1. Production MySQL 8 has not been live-verified.
2. Authentication and authorization are not yet implemented; bootstrap ownership is a data invariant only.
3. Legacy uploaded binary files are not copied by JSON import.
4. PDF/DOCX/PPTX parsing remains intentionally unsupported.
5. Browser E2E and CI are not configured.

## M1-B Entry Conditions

1. Provide and validate a safe MySQL 8 development DATABASE_URL, then run Alembic upgrade head and importer against it.
2. Approve authentication and tenant access design before exposing multi-user data.
3. Decide legacy binary-file migration policy.
4. Preserve M1-A API contracts while planning the frontend-specific M1-B work.
5. Do not begin Dashboard, Vue, Diagnose, LLM, Knowledge, Mastery, or Tutor work until M1-B scope is explicitly approved.
