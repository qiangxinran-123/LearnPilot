# LearnPilot frontend

LearnPilot uses Vue 3, TypeScript, Vite, Vue Router, Pinia, Element Plus, and Axios. The application shell provides the five learner-journey pages: 首页、课程、诊断、学习、进展.

M2 connects the Course workspace to the backend: course creation/edit/deletion, material upload/detail/deletion, persisted parsed content, study cards, and current-material Q&A. The Summary API remains available for compatibility, but the standalone Summary UI has been retired.

M3-E adds a course learning workspace with overview, materials, a hierarchy-first knowledge structure and an auxiliary graph. It reads the persisted M3 model and exposes node sources and relationship evidence without persisting graph layout state.

M6 shows the persisted course learning plan on Dashboard and Learn, including recommendation reasons, prerequisite context, evidence level, and one to three ordered tasks. The Diagnose workspace supports bounded question-bank preparation, human review, interrupted-assessment recovery, and explicit synchronization after new materials.

M7 opens a recoverable Learning Session from the plan, with cited course content, an AI Tutor, adaptive practice and a completion summary. The summary displays saved practice results, evidence, mastery changes and recommendation refresh status.

## Runtime

Tested with Node.js `22.22.2` and npm `10.9.7`. Supported Node range: `>=22.12.0 <25`.

## Development

Start a configured FastAPI backend in one terminal. The commands below assume backend dependencies are installed in the repository-root `.venv`. The example `.env.example` sets an explicit local SQLite demo URL. `cp -n` creates the ignored private `.env` only if one does not already exist; preserve an existing configuration before applying Alembic. With no `DATABASE_URL`, startup fails explicitly.

```bash
# repository root
cp -n .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn backend.main:app --reload
```

If the legacy LearnPilot data has not yet been imported, run the explicit, idempotent importer before starting the server:

```bash
.venv/bin/python -m backend.scripts.import_legacy_json \
  --database-url "sqlite+pysqlite:///./learnpilot-demo.sqlite3" \
  --source backend/app/data/courses.json \
  --dry-run
```

Review the dry-run summary before removing `--dry-run` to import. If you configured MySQL or another database, pass the corresponding private URL to `--database-url`; the importer does not infer that argument from `.env`.

Start Vite in another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Vite proxies `/api/*` and `/health` to `http://127.0.0.1:8000` during development. `VITE_API_BASE_URL` defaults to `/api`; see [.env.example](.env.example). Do not put passwords, database URLs, or API keys in `VITE_*` variables.

M2 accepts TXT, MD, PDF, and DOCX files up to the configured upload limit (20 MiB by default). PPTX is not enabled. Parsed text is persisted; summary, cards, and Q&A require a parsed material. Imported M1 records with only truncated or missing extracted text are explicitly marked partial/unavailable and need their source file re-uploaded before AI generation. Existing M1 mock summaries and cards retain legacy provenance.

For real AI calls, configure `LLM_MODE=provider`, `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` in the ignored repository-root `.env`; `LLM_TIMEOUT_SECONDS` defaults to 45 and `LLM_MAX_ATTEMPTS` to 2. See the root `.env.example` for the complete example. An absent provider configuration produces `AI_NOT_CONFIGURED`. Explicit `LLM_MODE=mock` is for local verification only; it is not a silent production fallback. `LLM_SUMMARY_MAX_INPUT_CHARS` defaults to 200000; larger parsed documents receive `AI_INPUT_TOO_LARGE`, rather than a partial summary.

## Course knowledge structure

Open a course and select `课程知识结构`. The panel is mounted only while that tab is active. `@antv/g6` is dynamically imported into a separate `knowledge-graph-vendor` chunk, so the normal material workflow does not load the graph runtime.

The graph uses only persisted backend entities:

- `CONTAINS` is a solid directed parent-to-child edge and determines hierarchy layout;
- `PREREQUISITE` is a dashed directed prior-knowledge edge and does not affect hierarchy layout;
- multiple real roots and disconnected nodes remain visible without a synthetic course root;
- node drawers show material title, source reference and bounded excerpt;
- edge drawers distinguish model rationale from validated material evidence;
- pan, zoom, fit, reset and local relation filters do not write coordinates back to the API.

The build/update button calls `POST /api/courses/{course_id}/knowledge-model/build-jobs`. It is available only when the course has usable parsed material and relies on the backend's M3-B through M3-D idempotency and failure-preservation behavior.

## Quality checks

```bash
npm run typecheck
npm run lint
npm run test
npm run build
```

`npm run build` creates `dist/`. Once the production build exists, FastAPI serves it as a same-origin SPA while preserving `/api/*` and `/health` routes. The build currently reports a nonfatal size advisory for the main bundle and lazy G6 vendor chunk.

## Verification

The M7 final acceptance report records typecheck, lint, production build, and the full Vitest suite (`181/181`) passing, alongside an isolated Chromium learning flow. This release operation does not rerun those checks. See [M7 final acceptance](../docs/migration/M7_6_FINAL_ACCEPTANCE_REPORT.md) for the scope and limitations.

A real-provider browser E2E used two self-authored TXT materials and the course-level build flow. It produced a persisted model with 12 nodes, 3 `CONTAINS` edges and 13 `PREREQUISITE` edges, then verified node sources, edge evidence, filtering, pan/zoom/fit/reset and responsive behavior at 1440/1280/1024 px. No credential, provider endpoint or complete user material is recorded in the repository.

## Legacy migration

The former native LearnPilot UI is preserved in `legacy/` for reference only. It is not served by the Vue development server or the production static integration.
