# LearnPilot V1 — M1-B Frontend Architecture

## 1. Scope

M1-B replaces the active CampusAI native frontend with a Vue 3 product shell. It establishes navigation, shared UI states, a typed API boundary, a minimal Pinia store, and five learner-journey routes. It does not introduce course CRUD, material-upload UI, AI, diagnosis, knowledge graph, mastery, recommendation, tutor, or progress analytics.

## 2. Frontend Stack

- Vue 3 and TypeScript
- Vite 6
- Vue Router 4
- Pinia 3
- Element Plus (only the components used by the shell are registered)
- Axios
- ESLint 9, Prettier 3, Vitest 3, Vue Test Utils

The package manifest pins its dependency graph through `package-lock.json` and declares Node `>=22.12.0 <25`.

## 3. Directory Structure

```text
frontend/
├── legacy/                 # preserved native CampusAI reference, not runtime
├── src/
│   ├── components/         # navigation, common, feedback components
│   ├── layouts/            # AppLayout
│   ├── router/             # route definitions and title metadata
│   ├── services/           # Axios client and course API service
│   ├── stores/             # app and course state
│   ├── styles/             # tokens, base styles, utilities
│   ├── tests/              # Vitest component/router tests
│   ├── types/              # API and course contracts
│   └── views/              # product-level pages
├── .env.example
├── package.json
└── vite.config.ts
```

## 4. Routing

`/` redirects to `/dashboard`. The formal product routes are `/dashboard`, `/courses`, `/diagnose`, `/learn`, and `/progress`; a catch-all route renders `NotFoundView`. Every product route supplies `meta.title` and `meta.navLabel`; the router synchronizes `document.title` as `<title> · LearnPilot`.

The five pages are lazy loaded. Their navigation reflects the learner journey rather than AI implementation details.

## 5. State Management

`appStore` owns small UI concerns such as responsive sidebar state. `courseStore` is intentionally narrow: it de-duplicates an in-flight course-list request and models `idle`, `loading`, `success`, and `error` states. No future learning-domain state is pre-created.

## 6. API Layer

All application HTTP traffic is centralized in `src/services/http.ts`. The API client defaults to `VITE_API_BASE_URL` or `/api`, has a finite timeout, and normalizes network, timeout, structured-backend, and unknown failures into `ApiError`.

`src/services/courses.ts` contains the only current product request: `GET /courses`, which maps to `GET /api/courses`. The health request remains inside the same HTTP module and is invoked only as a development diagnostic; it is not shown as user-facing status.

Vite proxies `/api` and `/health` to `http://127.0.0.1:8000` by default. Product components do not hard-code a localhost URL.

## 7. Design Principles

The shell follows “Calm Academic Intelligence”: a cool neutral canvas, measured blue accents, high-contrast text, and a quiet academic hierarchy. Shared design tokens define spacing on a 4/8/12/16/24/32/40/48 scale, three controlled radii, typography tiers, focus treatment, and motion reduction behavior.

The UI deliberately avoids fabricated mastery, recommendations, progress figures, charts, AI claims, and feature-grid decoration. When the backend has no supporting data, it shows a clear empty state instead.

## 8. Responsive Strategy

The desktop layout uses a persistent sidebar and a 64px header. At smaller widths the sidebar compacts, then becomes a keyboard-accessible mobile drawer. The course grid uses responsive `minmax` sizing, and the main content gutter reduces from desktop to compact widths. The CSS targets 1440px, 1280px, 1024px, and 768px without requiring a separate mobile product implementation.

## 9. Error and Loading Strategy

`LoadingBlock` provides course-card skeletons rather than a blank screen. `ErrorState` has a human-readable message and retry action. `EmptyState` always gives a title, explanation, visual marker, and only an actionable next step that actually exists. Backend details, Axios stacks, and development health status are not exposed in product UI.

## 10. Testing Strategy

Vitest and Vue Test Utils cover:

1. primary router mapping and the Not Found route;
2. sidebar navigation configuration;
3. course data rendering from the API service;
4. course empty state; and
5. recoverable course error state.

Backend regression also covers the SPA static route boundary: public history fallback works while `/api/*` and `/health/*` are not converted to frontend HTML.

## 11. Backend Integration

After `npm run build`, FastAPI mounts `frontend/dist`, not frontend source. `SPAStaticFiles` only falls back to `index.html` for public GET/HEAD page routes. Existing API routers are registered first; `/api/*`, `/health`, `/docs`, `/redoc`, and `/openapi.json` retain backend behavior.

A build directory is intentionally not synthesized during backend startup. In development, run Vite separately; in a production-style local demo, build the frontend first.

## 12. M2 Extension Points

M2 can add a Course Detail route and material-oriented UI below the existing typed service boundary and shell. Future diagnosis, knowledge, mastery, learning, tutor, and progress capabilities can extend page-local or domain-specific stores only when their backend contracts exist. No speculative domain tables, mock learning intelligence, or chart dependencies were added in M1-B.
