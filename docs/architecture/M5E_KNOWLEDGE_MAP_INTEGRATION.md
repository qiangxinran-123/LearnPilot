# M5-E Dynamic Knowledge Map Integration

## Scope and reused M3 capability

M5-E extends the existing `KnowledgeStructurePanel` and its single `KnowledgeFocusGraph`. It does not create another map, layout algorithm, route, state store, or graph dependency. Existing tree navigation, direct-relation layout, zoom, pan, node focus, and `nodeId` URL synchronization remain authoritative.

The map now has two URL-backed modes:

- `课程结构` is the unchanged default.
- `我的掌握状态` adds `mode=mastery` to the existing course route and decorates the same nodes.

Changing mode preserves the focused node and map route. The knowledge-detail link carries the mode and returns to the same focused map state.

## M5-D mapping

`frontend/src/services/mastery.ts` consumes the existing read-only endpoints:

- `GET /courses/{course_id}/mastery`
- `GET /courses/{course_id}/knowledge/{node_id}/mastery`
- `GET /courses/{course_id}/knowledge/{node_id}/evidence`

Frontend types mirror the M5-D response, including nullable decimal-string scores, mastery status, confidence, counts, model/algorithm versions, timestamps, availability, and whitelisted evidence fields.

Course state is joined to the current map by numeric `knowledge_node_id` only. Unknown historical IDs are discarded; names are never compared. A score is usable only when M5-D returns `calculation_state: calculated`. `not_calculated` and `stale` are shown as waiting for assessment, never as 0% or the prior estimate. M5-D remains responsible for validating the knowledge-model/evidence version contract; the frontend displays its version metadata without inventing a migration.

## Presentation

The existing graph nodes receive low-saturation status borders and a text line containing the backend status and confidence. Confidence is separate from mastery. A good-performance result with low or insufficient confidence uses a cautious rather than success treatment. Thresholds are not recalculated in the browser.

The existing knowledge-detail page conditionally adds `KnowledgeMasteryDetail` when entered from mastery mode. It displays persisted mastery/confidence/counts and the bounded M5-D evidence whitelist: diagnostic ID, historical question reference, difficulty, normalized performance, and occurrence time. It does not expose answers, correct options, snapshots, or generate recommendations.

## Async and error handling

Course and node requests use monotonically increasing request identities plus requested course/node checks. Old responses cannot overwrite a newer course or node. Changing course/model clears cached mastery. Successful data is reused while the course/model is unchanged. A failed mastery request leaves the M3 map intact and exposes an explicit retry.

Empty knowledge models retain the original M3 empty state. Missing diagnostics, insufficient evidence, null mastery, stale state, and missing current-node records all render as waiting for assessment.

## Verification

- Affected component tests: 29/29 passed.
- Complete frontend tests: 104/104 passed in time-bounded groups.
- Complete backend regression: 298/298 passed; M5-E changed no backend production code.
- TypeScript: passed.
- ESLint: passed.
- Production build: passed; the pre-existing Vite chunk-size warning remains non-blocking.
- Browser visual check: passed against an isolated SQLite database at 1024 px and 1440 px. The same graph displayed one calculated node and one unassessed node, mode switching preserved the focused-node URL, and the detail view displayed the bounded evidence explanation.

`DATABASE_MIGRATION = NOT REQUIRED`. No backend model, migration, scoring, evidence, or immutable diagnostic record changed.

## Known limitations and M5-F handoff

The detail endpoint currently returns at most the requested bounded evidence page; M5-E displays that page and does not add infinite scrolling. Read requests deliberately do not refresh stale mastery. M5-F may consume the same state for its approved scope, but this stage adds no recommendation, progress analytics, practice, or learning-path behavior.
