# LearnPilot frontend

LearnPilot uses Vue 3, TypeScript, Vite, Vue Router, Pinia, Element Plus, and Axios. The application shell provides the five learner-journey pages: 首页、课程、诊断、学习、进展.

M2 connects the Course workspace to the backend: course creation/edit/deletion, material upload/detail/deletion, persisted parsed content, structured summary, study cards, and current-material Q&A. The other product areas retain truthful empty states; no mastery or progress figures are fabricated.

## Runtime

Tested with Node.js `24.21.0` and npm `11.19.0`. Supported Node range: `>=22.12.0 <25`.

## Development

Start a configured FastAPI backend in one terminal. The commands below assume backend dependencies are installed in the repository-root `.venv`. The example `.env.example` sets an explicit local SQLite demo URL. `cp -n` creates the ignored private `.env` only if one does not already exist; preserve an existing configuration before applying Alembic. With no `DATABASE_URL`, startup fails explicitly.

~~~bash
# repository root
cp -n .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn backend.main:app --reload
~~~

If the legacy CampusAI data has not yet been imported, run the explicit, idempotent importer before starting the server:

~~~bash
.venv/bin/python -m backend.scripts.import_legacy_json \
  --database-url "sqlite+pysqlite:///./learnpilot-demo.sqlite3" \
  --source backend/app/data/courses.json \
  --dry-run
~~~

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

## Quality checks

```bash
npm run typecheck
npm run lint
npm run test
npm run build
```

`npm run build` creates `dist/`. Once the production build exists, FastAPI serves it as a same-origin SPA while preserving `/api/*` and `/health` routes.

## Verification

Typecheck, lint, production build, and Vitest (17/17) passed. The build reports a nonfatal main-chunk warning above 500 kB. A real browser flow against FastAPI used explicit `LLM_MODE=mock` to create a course, upload and parse a self-created two-page PDF, generate summary/cards, and answer a page-2 question with a `PDF 第2页` reference. Refresh did not repeat generation, and server restart retained artifacts. Material Q&A screenshots were visually inspected at 1440/1280/1024 px and Course at 1280 px without overflow. This flow does not establish a live provider call; real LLM smoke remains blocked by absent configuration.

## Legacy migration

The former native CampusAI UI is preserved in `legacy/` for reference only. It is not served by the Vue development server or the production static integration.
