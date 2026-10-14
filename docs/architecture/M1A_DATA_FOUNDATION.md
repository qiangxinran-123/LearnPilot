# LearnPilot V1 — M1-A Data Foundation

## Scope

M1-A establishes relational persistence, ownership, migrations, legacy import, storage abstraction, upload policy, error/logging foundations, locked dependencies, and tests. It does not add Vue, Dashboard, Diagnose, Knowledge Graph, Mastery, Tutor, RAG, LLM, or non-TXT/MD parsing.

## Layering

    FastAPI Router
        -> CourseService
            -> CourseRepository / MaterialRepository / UserRepository
                -> SQLAlchemy Session
                    -> MySQL 8 target database

Routers contain HTTP mapping only. Services receive a request-scoped SQLAlchemy session and never create engines or connections. Repositories contain persistence queries and no HTTP behavior. Schema creation is Alembic-only; application startup does not call create_all.

## Entity Relationships

    User
      1
      |
      N
    Course
      1
      |
      N
    Material

User.email is unique. Course.owner_id is a required foreign key to users.id with RESTRICT delete behavior. Material.course_id is a required foreign key to courses.id with CASCADE delete behavior. Material stores metadata, safe storage state, extraction state, and legacy mock summary/card compatibility fields.

Future KnowledgeNode, KnowledgeEdge, Question, Assessment, Response, LearningEvidence, MasterySnapshot, LearningSession, LearningTask, Conversation, and Message can attach through Course and User. They are intentionally not created in M1-A.

## Database Strategy

Production target is MySQL 8 through SQLAlchemy 2.x and the mysql+pymysql dialect. DATABASE_URL is mandatory at application startup. The application logs a connection failure without logging credentials and exits rather than silently falling back to JSON or SQLite.

M1-A automated tests use isolated SQLite files only to verify schema portability, migrations, repositories, importer behavior, and API regression. A MySQL 8 server and non-secret DATABASE_URL were not available in this environment, so live MySQL connectivity remains BLOCKED and must be verified before release.

## Migration Strategy

Alembic configuration is in alembic.ini. The initial migration is:

    backend/alembic/versions/0001_m1a_foundation.py

From an empty configured database:

    DATABASE_URL=<safe-url> alembic upgrade head

The migration creates users, courses, and materials with foreign keys and indexes. Startup never creates schema automatically.

## Ownership Model

Every Course requires owner_id. Legacy LearnPilot records are assigned to an explicit bootstrap user selected by LEGACY_BOOTSTRAP_USER and LEGACY_BOOTSTRAP_USER_DISPLAY_NAME. The importer finds this user by email or creates it, never relies on a magic numeric ID. Authentication APIs are deliberately out of scope; future authentication will resolve the authenticated user to this ownership model.

## Legacy JSON Import

The source backend/app/data/courses.json remains an immutable input. Use the module command:

    python -m backend.scripts.import_legacy_json --database-url <safe-url> --dry-run
    python -m backend.scripts.import_legacy_json --database-url <safe-url> --backup-dir <safe-directory>

The importer checks source existence and JSON structure, supports dry-run, optionally copies a timestamped source backup, reports users_created, courses_created, courses_skipped, materials_created, materials_skipped, and errors. Legacy keys make repeats idempotent. It does not modify source JSON and does not import historical absolute paths. Legacy file metadata is labeled LEGACY_FILE_UNMIGRATED until a separately approved file migration is performed.

## Storage Strategy

FileStorage defines save, delete, exists, and open_read. LocalFileStorage is the M1-A implementation. It uses a UUID internal storage key, never the client filename, and stores only the key internally. Material public responses expose original_filename and storage_status, never storage_key or an absolute server path.

## Upload Policy

Default MAX_UPLOAD_BYTES is 20 MiB. Allowed extensions are TXT, MD, PDF, DOCX, and PPTX. Upload validation checks filename, path components, extension, declared media type, bounded streaming size, empty input, and basic PDF/Office signatures. TXT/MD retain UTF-8 extraction. PDF/DOCX/PPTX are securely stored but return UNSUPPORTED_FORMAT extraction status until parser work is approved.

## Error and Logging Contract

Error responses include:

    {
      "error": {
        "code": "UPLOAD_TOO_LARGE",
        "message": "Uploaded file exceeds the allowed size."
      }
    }

For compatibility, legacy detail is retained for HTTP error consumers. Logging records startup, database connection lifecycle failures, upload rejection/storage failure, extraction failures, import failures, and unhandled exceptions. It does not log database credentials, passwords, keys, or document contents.

## API Compatibility

Existing Course/Material endpoints and mock summary/card behavior are preserved. Public Material responses remove file_path and add safe original_filename, storage_status, extraction_status, extraction_error_code, and extraction_error_message.

Intentional breaking changes:

1. GET /hello was removed because it was unreachable behind the static catch-all and was deprecated in M0.
2. Error responses now include error.code and error.message. Existing detail remains for compatibility.
3. file_path is no longer a public field.

## Known Limitations

MySQL 8 live migration/connection is NOT VERIFIED because no MySQL service or safe DATABASE_URL is available. Auth is not implemented. Existing legacy files are not copied by the JSON importer. PDF/DOCX/PPTX text parsing, real LLM, and all M1-B/M2 product features remain out of scope.
