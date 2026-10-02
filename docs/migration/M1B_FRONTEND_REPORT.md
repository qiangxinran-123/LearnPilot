# LearnPilot V1 — M1-B Frontend Foundation Report

## Status

**M1-B is not formally complete.** Engineering, API, build, and regression criteria are verified, but the required browser visual verification remains **NOT AVAILABLE** in this environment. Consequently, responsive visual acceptance is **NOT VERIFIED**, M2 readiness is **NOT READY**, and project progress must remain at **10%** until that check is completed.

## Actual Changes

- Replaced the active native CampusAI frontend with a Vue 3 + TypeScript + Vite application.
- Added Vue Router, Pinia, Element Plus, Axios, ESLint, Prettier, Vitest, and Vue Test Utils with an npm lockfile.
- Added the learner-journey shell: 首页, 课程, 诊断, 学习, 进展, plus a Not Found route.
- Added shared layout, sidebar, header, page-header, loading, error, empty-state, and course-card components.
- Added typed API client and typed `GET /api/courses` integration.
- Added truthful loading, empty, and retry states; no mastery, recommendation, progress, diagnostic, or AI data was fabricated.
- Added FastAPI build-directory static integration with public SPA history fallback and API/health route protection.
- Added backend static-route regression tests.
- Preserved the legacy native files under `frontend/legacy/`; they are not in active runtime.

## Legacy Frontend Migration

The original `frontend/index.html`, `frontend/app.js`, and `frontend/styles.css` were native CampusAI UI files with no user modifications at the start of M1-B. They were moved into `frontend/legacy/` after the Vue build was established. FastAPI now serves `frontend/dist/` only when a production build exists; development uses Vite.

## Frontend Skill Usage

- `frontend-design`: **NOT AVAILABLE** in the current Codex skill catalog.
- `frontend-app-builder`: **USED** as a visual-quality guide. It informed the restrained cold-neutral canvas, clear sidebar/header hierarchy, spaced academic composition, and avoidance of fabricated dashboards. Its recommendations did not expand M1-B scope.
- `computer-use`: attempted for browser validation but the helper failed to initialize due to a local sandbox setup error.
- `playwright`: used as the browser-validation fallback. The CLI and Chromium download completed, but the browser could not launch because the environment lacks `libnspr4.so`; a system-level install attempt was canceled at the password prompt and no credentials were entered.

## Dependencies

`frontend/package.json` and `frontend/package-lock.json` declare Vue 3, TypeScript, Vite, Vue Router, Pinia, Element Plus, Axios, ESLint, Prettier, Vitest, and Vue Test Utils. Element Plus is registered and styled on demand for the small component subset used in M1-B.

Node `24.21.0` and npm `11.19.0` were used. `npm ci` passed.

## Routes

| Route | Purpose | Runtime data |
| --- | --- | --- |
| `/dashboard` | learning-space entry | real course count/list only |
| `/courses` | course structure and data integration | `GET /api/courses` |
| `/diagnose` | future diagnostic introduction | truthful empty state |
| `/learn` | future personalized path introduction | truthful empty state |
| `/progress` | future evidence/progress introduction | truthful empty state |
| catch-all | Not Found | none |

## API Integration

Verified against a migrated, imported temporary SQLite runtime:

- `GET /health`: **PASS** — 200 JSON response.
- `GET /api/courses`: **PASS** — 200 JSON response with three imported courses.
- Vite `/health` proxy: **PASS**.
- Vite `/api/courses` proxy: **PASS**.
- FastAPI production-static `/dashboard`: **PASS** — 200 HTML after `npm run build`.
- FastAPI `/api/not-real`: **PASS** — remains 404, not SPA HTML.

## Tests

| Check | Result |
| --- | --- |
| `npm ci --include=dev --no-audit --no-fund` | PASS |
| `npm run typecheck` | PASS |
| `npm run lint` | PASS |
| `npm run test` | PASS — 6/6 |
| `npm run build` | PASS |
| `ruff check backend` | PASS |
| `pytest backend/tests -q` | PASS — 35/35 |
| static-route focused regression | PASS — 2/2 (included in 35) |

## Build Verification

`npm run build` completed successfully. The final production main bundle is approximately 267 KB before gzip and 100 KB gzip, with Element Plus loaded on demand rather than as the entire library.

## Lint and Typecheck Verification

ESLint, Prettier, TypeScript, and Vue compilation were configured without using `any` to evade project type errors or `skipLibCheck` to mask third-party type issues. A build-time type issue was discovered and fixed through the correct Vite environment declaration, DOM typings for Vite config, and correct Vue component typing.

## Browser and Responsive Verification

- Browser Visual Check: **NOT AVAILABLE**.
- Responsive Baseline (1440/1280/1024/768): **NOT VERIFIED**.

The Vite server and all target routes responded during runtime verification, but screenshot capture could not launch in this host because Chromium lacks `libnspr4.so`. No screenshot is reported as inspected.

## Known Limitations

- M1-B intentionally does not provide course CRUD, course detail, material upload UI, parsing UI, real LLM functionality, diagnostic workflow, knowledge model, mastery, learning recommendation, tutor, or progress charts.
- FastAPI requires `frontend/dist/` to exist before it can host the production SPA. Vite remains the development runtime.
- Browser visual verification must be rerun on a host with a functional browser runtime before formal acceptance.

## M2 Entry Conditions

1. Restore a working browser runtime (or perform equivalent visual review in a supported browser).
2. Verify Dashboard, Course, Diagnose, Learn, and Progress at 1440px, 1280px, 1024px, and 768px for overflow, spacing, wrapping, active navigation, loading, empty, and error states.
3. Record the result in this report and rerun final diff/secrets review.
4. Only then mark M1-B complete, move project progress from 10% to 12%, and begin M2 Course Detail/material work after user approval.
