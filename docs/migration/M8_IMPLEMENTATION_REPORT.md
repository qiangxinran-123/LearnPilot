# M8-1 + M8-2 implementation report

## Status

M8-1: COMPLETE. M8-2: COMPLETE. Project progress: 87% under the requested milestone rules. No M8-3 or M8-4 functionality was added.

## Environment

The restricted Windows process could not launch WSL. Approved WSL execution worked: repository root and clean initial main branch were verified, Python 3.14.4 and the existing nvm Node 24.22.0/npm 11.19.1 were used, and a temporary workspace write check was removed. No user database was deleted or rebuilt. No migration or project dependency was added.

## Implementation

The M8 service calls M5 MasteryReadService for fingerprint-verified current score, status, confidence and evidence counts. It combines that result with current active M3 nodes and contains edges. Unique active leaves, including isolated nodes, form the denominator. Multi-parent nodes count once, parents do not count with children, and cycles produce a 409 error. The equal-weight average excludes null scores; coverage is null for an empty denominator. Weak points use M5's possibly_weak and needs_attention statuses, never unassessed nodes. See the architecture document for the complete contract and caveats. M7 practice evidence uses the existing M5 read and settlement chain.

The overview and knowledge endpoints expose Pydantic DTOs with existing ownership checks. Progress performs no business writes, LLM calls, recommendation updates or session creation. The Vue page reuses the course store, shared HTTP client and knowledge-map route. It provides a leaf-only horizontal comparison, direct-parent module filter, status counts, coverage, confidence, evidence counts, and loading, empty, partial, stale and error states. A request generation guard prevents old course requests overwriting a newer selection. Score display preserves two decimals.

## Validation

- Backend full regression: 415 passed (run started with five M8 tests); the subsequently expanded M8 isolated suite: 8 passed. No paid LLM call.
- Full frontend Vitest: 188 passed in 30 files. TypeScript, ESLint and production build: PASS. Existing synthetic event warnings and the Vite large-chunk advisory remain.
- Ruff check and format check: PASS. Git diff check: PASS at the M8-1 gate and after final implementation.
- Isolated browser fixture: 1440, 1280 and 1024 widths inspected; long Chinese names, weak list, partial data, empty course, course switching and navigation to the existing knowledge-map route checked. The synthetic fixture lacked a confirmed knowledge structure, so exact node focus in the map is NOT VERIFIED. Screenshots were taken before the final small score-precision and status-text adjustments; those changes were checked by tests and build.
- Existing frontend-design skill was used; no skill was installed. Playwright guidance and the existing browser control were used for browser verification.

## Limitations and next stage

The M5 result and hierarchy are read in separate operations; a concurrent change can require another request. Direct-parent module filters may show a multi-parent leaf in multiple filtered views, but the overall population counts it once. Cyclic contains graphs are rejected rather than partially summarized. Before M8-3, confirm a reliable historical snapshot source and its identity/version semantics; history and trend visualization were NOT IMPLEMENTED at M8-2 acceptance.


## M8-3 implementation and verification

- Historical source audit: current M5 state is not history. M7 settlement summaries lack fingerprint/version proof; no historical backfill was performed. Migration `0019_m8_mastery_history` records future evidence-backed, M5-verified changes in the same transaction, deduplicated by source fingerprint and algorithm version.
- The trend endpoint reuses M8's active leaf definition and owner check. Graph and algorithm fingerprints partition comparisons; incompatible recorded states break the line. Historical points use actual snapshot times and report coverage. Current stale mastery remains separate from history.
- Learning history includes submitted initial diagnoses and completed sessions. It excludes unfinished work, individual evidence, and separately duplicated practice events. Pagination uses a stable time/type/ID cursor.
- Frontend: a time-scaled SVG trend, point details and coverage, real 7-day/30-day/all filters, history list, and loading/empty/error states. The installed frontend-design skill and existing design system were used; no skill or chart dependency was installed.
- Verification: final full backend regression 425 passed; the subsequently expanded mastery-history suite passed all 8 tests. Targeted M5/M7/M8 history tests also passed. Full frontend Vitest 193 passed, TypeScript and ESLint passed, and production build passed. The existing Vite chunk warning remains.
- Migration: empty-database migration was exercised by isolated fixtures; upgrade from populated revision 0018 preserved data and created an empty history table.
- Browser: isolated data checked at 1440, 1280 and 1024 widths, including graph, timeline, course switch, empty history and range selection. Point tooltip text is tested in the component; its native hover rendering was NOT VERIFIED in the browser.
- Known limits: diagnostic submission does not automatically refresh M5; history starts only on a subsequent evidence-backed update. Graph lifecycle and semantic node versions are not persisted; changes that revert between recorded snapshots cannot be detected. Current graph fingerprints and recorded incompatible events limit, but cannot eliminate, that uncertainty. Historical data is not a causal attribution.
- M8-4 precondition: confirm M8-3 acceptance before considering review-risk semantics. M8-4 was NOT IMPLEMENTED at M8-3 acceptance.

M8-3 status: COMPLETE. Final project progress: 88.5%. Ruff check, Ruff format check, TypeScript, ESLint, production build and final git diff check: PASS. Browser tooltip hover rendering: NOT VERIFIED.


## M8-4 review risk and integration

- Source audit: M5 current state and confidence are authoritative; M5 has no time decay. M6's review input currently remains unavailable and was not connected to this display. M7 submitted practice responses provide the last reliable practice time. M8-3 history records timestamp and algorithm but is not treated as current mastery.
- The read-only risk API and service use M5's freshness and submitted-evidence verification, current leaf nodes and owned-course scope. They provide deterministic reason codes and levels; 14/30-day intervals and three recent practice facts are V1 heuristics, not a validated forgetting model. No new migration, service infrastructure, LLM call or recommendation calculation was added.
- One Progress region merges weak nodes and reminders, preserves weak entries when risk loading fails, and supports independent error/retry and course request isolation. Existing overview, trend and learning history remain in place.
- Risk isolated suite: 15 tests passed; final full backend regression: 442 passed. Full frontend Vitest: 199 passed; TypeScript, ESLint and build passed. Existing Vite large-chunk advisory remains.
- Browser: isolated fixture checked at 1440, 1280 and 1024 pixels; long names, partial data, empty state, course switching, an injected risk-only failure and retry, and the knowledge-map route were checked. The fixture has no confirmed map structure, so precise node focus is NOT VERIFIED.
- Environment note: an initial test server was stopped immediately when its startup log showed default configuration; its startup performed the application's connection validation SELECT only, and no browser request was made to it. A second server explicitly pointed to the temporary test database for all browser checks. No user database was modified or rebuilt.
- Known limits: timestamps are submitted-response times, not proof of retention or independent study. Review signals are not recommendations; insufficient/stale cases are not low risk. Separate overview and risk reads may observe changes at different times. M8-5 is NOT IMPLEMENTED.

M8-4 status: COMPLETE. Final project progress: 89.5%. Ruff check and format check, TypeScript, ESLint, production build and git diff check: PASS. No M8-4 migration or new dependency. The final layout was rechecked at all three requested widths after the status-label change. Exact map-node focus remains NOT VERIFIED in the unconfirmed synthetic fixture.
