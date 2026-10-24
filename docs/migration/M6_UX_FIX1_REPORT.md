# LearnPilot V1 — M6-UX-FIX-1 Report

## Status

This report supersedes the earlier unresolved long-document Summary follow-up decision.

- `SUMMARY_UI_RETIRED`: the standalone user-facing Summary feature is no longer exposed.
- `SUMMARY_BACKEND_RETAINED`: existing GET/POST Summary APIs and the MaterialAIService Summary implementation remain compatible.
- `SUMMARY_DATA_PRESERVED`: no table, model, migration, historical record, or upload was deleted.
- `SUMMARY_REAL_PROVIDER_LONG_DOC_NOT_RETESTED`: no further paid long-document Summary call was made after the product decision.

The prior long-document structured-output limitation is not reported as fixed. It is deliberately not pursued because V1 no longer exposes an independent Summary workflow to ordinary users.

## Dependency audit

- The retired frontend call sites were Material Detail's Summary tab and Summary API client methods.
- Knowledge Detail had one user-facing “资料摘要” link; it is removed.
- Course Detail had one Summary discovery phrase; it is revised.
- M3 knowledge building, M4 diagnosis, M5 Mastery/Evidence, and M6 recommendations/plans do not call the Summary API.
- Study Cards and Material Q&A continue to use the shared MaterialAIService, material parsing/content, LLM client, chunking, and source validation. These shared dependencies were retained.

## Frontend retirement

- Removed the Summary tab, display, generate/regenerate actions, loading/error/recovery states, and Summary GET request from `MaterialDetailView`.
- Removed the Summary-specific client methods and finite timeout constant from `ai-materials.ts`.
- Removed now-unused Summary styles and the retired Summary-only frontend test.
- Retained content display, parsing errors, Study Cards, FIX-1A card affordance, Material Q&A, and material deletion behavior.
- Opening or refreshing Material Detail now fetches only material details, parsed content when applicable, and cards. It does not call Summary GET or POST.
- No user-visible Summary entry remains in the frontend.

## Backend compatibility and data protection

The following are intentionally unchanged:

- `GET /api/materials/{material_id}/summary` and `POST /api/materials/{material_id}/summary`
- MaterialAIService Summary implementation and structured-output validation
- MaterialSummary model/table, historical rows, and database migrations
- Common parsing, chunking, Provider, persistence, and citation logic
- Cards and Q&A APIs

No database migration, cleanup, reset, or paid Summary smoke test was run.

## Tests and checks

Focused frontend retirement coverage verifies:

- no Summary UI or Summary operation appears in Material Detail;
- Card rendering, FIX-1A interaction, parse state, Q&A, and deletion behavior;
- Course and Knowledge pages no longer advertise or link to Summary.

Full regression results are recorded after this report update.

## Worktree safety

No Git commit, push, reset, clean, restore, stash, branch operation, database reset, or user-data deletion was performed. Pre-existing M4–M6/FIX worktree changes remain preserved.


## Final regression results

- Backend: 348 / 348 passed.
- Frontend: 123 / 123 passed.
- Ruff lint: passed.
- Ruff format check: 174 files already formatted.
- TypeScript: passed.
- ESLint: passed.
- Production build: passed (the existing non-blocking bundle-size warning remains).
- Diff check: passed.
- Historical-data read-only check: 1 MaterialSummary row and 1 material marked summary-generated remain in the current SQLite database.
