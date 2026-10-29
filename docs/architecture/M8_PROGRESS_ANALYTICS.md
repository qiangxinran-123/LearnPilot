# M8 Progress analytics

## Status

M8-1 and M8-2 are implemented. See the implementation report for verification and limitations.

## Data and semantics

The authority for a node's current score, status, confidence and effective evidence count is M5's `MasteryReadService.course_mastery`. It scopes reads to the existing bootstrap owner and course, verifies the persisted evidence fingerprint, and suppresses stale or uncalculated scores. A calculated state with insufficient independent evidence also has a null score. M7 settlement supplies submitted practice evidence to the same M5 path; Progress neither calculates mastery nor writes business state.

M3 active nodes and current `contains` edges define the hierarchy; prerequisite edges are ignored. A leaf has no active child through a current contains edge. Isolated active nodes are leaves; nodes with multiple parents appear once. Edges to inactive nodes are excluded. A cycle returns HTTP 409 `INVALID_KNOWLEDGE_HIERARCHY`, rather than publishing a misleading denominator.

Overall mastery is the equal-weight arithmetic mean of non-null M5 scores on unique leaves, rounded half-up to two decimal places. Coverage is scored leaves divided by all leaves; it is null when there are no leaves. An unavailable score is never zero. This describes only the evaluated portion of the course, not the entire course. Counts by M5 status use the same leaf population. The weak list includes the existing M5 `possibly_weak` and `needs_attention` statuses only, and only when a score is available. Confidence and evidence counts are passed through unchanged; stale or uncalculated states follow M5's suppressed values.

## API

`GET /api/courses/{course_id}/progress/overview` returns course ID, nullable overall mastery, evaluated and evaluable leaf counts, nullable coverage ratio, counts by M5 status and weak leaf records.

`GET /api/courses/{course_id}/progress/knowledge` returns leaf records with node ID, name, direct parent IDs, nullable score, M5 status, confidence, evidence count and calculation state. Decimal values use Pydantic's JSON serialization. Both endpoints hide missing or foreign courses using the existing 404 error model and reject cyclic current hierarchies with 409. They are read-only and do not invoke an LLM or create sessions.

## Limitations

The hierarchy and mastery are read in separate operations; concurrent changes can require a subsequent request. Recommendation calculation remains outside Progress; M8-4 review reminders are defined below. See the implementation report for the validation results.


## M8-3: history and trend

### Source audit and write boundary

M5 stores one current `StudentKnowledgeState` per user/course/node, not a versioned history. Learning Evidence is a source fact, not a mastery snapshot. M7 completion_summary contains before/after values but lacks the evidence fingerprint and cannot establish a general historical series. M7 settlement creates practice evidence and calls M5 refresh inside its transaction. The repository's diagnostic submission path does not automatically call M5 refresh; a submitted diagnostic is a completed activity but is not necessarily a mastery update.

Migration `0019_m8_mastery_history` adds future-only history. No prior score or date is backfilled. On a changed M5 state with evidence, the write path verifies the state against M5's submitted-evidence fingerprint boundary and inserts its score, status, confidence, fingerprint, algorithm version, current graph fingerprint and M5 calculation time in the same transaction. No snapshot is created by a GET or an unchanged refresh. The unique user/course/node/algorithm/evidence-fingerprint key prevents duplicate versions. Failure rolls back the enclosing state and session transaction. Current mastery continues to be read through M5; history is never used as a current value.

### Trend contract and comparability

`GET /api/courses/{course_id}/progress/trend?range=7d|30d|all` returns real event timestamps, scores, assessed/evaluable counts, coverage and a segment identifier. Windows are rolling 7 or 30 times 24 hours in UTC; frontend dates display in the browser's local timezone. At each actual snapshot timestamp the last previously recorded compatible state for each current M8 leaf is used; no node is filled from a future snapshot and no extra dates are generated. Prior compatible snapshots can supply already-known states for an event inside a requested window. Null values are excluded; a point exists only when at least one score is available. Equal weighting and the leaf denominator come from M8-1.

Each snapshot captures a hash of active node IDs and current active contains edges. Only records matching the current structure and current M5 algorithm are eligible. An intervening recorded incompatible version clears carried state and starts a new segment; the frontend does not join segments. This avoids comparing recorded incompatible structures. There is no graph lifecycle history: a structure that changes and returns to identical IDs/edges without any intervening mastery snapshot cannot be detected. Node semantic edits without graph identity changes likewise are not versioned. The trend is an observed-state display, not proof of causal improvement; coverage changes are shown and warned about.

### Learning history contract

`GET /api/courses/{course_id}/progress/history?limit=20&cursor=...` returns owned, completed learning sessions and submitted initial diagnostic assessments, sorted descending by completion time, event type and source ID. The cursor uses those same keys. Unfinished sessions and unsubmitted assessments are excluded. Practice and individual evidence are not emitted separately from a session, avoiding duplicate events. Session target node identity and name are taken from the existing model; diagnostic events have no invented node. The endpoint performs no writes.

The frontend uses the existing Progress page and a small SVG time-scaled line chart, showing points and coverage explicitly. Fewer than two comparable points do not form a line. The timeline presents only the supported activity types, and range and course changes invalidate older requests.


## M8-4: review reminders

Review risk is a deterministic explanation of existing evidence, not mastery, a forgetting forecast, or M6 next-action priority. M5 has no time-decay rule. M6 has an optional review-risk component, but its current context reports that input unavailable; M8 does not feed or change M6. M7 settlement creates practice evidence from submitted responses. M8-3 snapshots have calculation times and algorithm versions, but do not establish a new current score or replace M5 freshness checks.

`GET /api/courses/{course_id}/progress/review-risk?limit=100` (limit 1–500) returns `assessed_at` UTC, total leaf count, counts for all four levels, and bounded, stable results (review_due, watch, insufficient_data, low_risk; then node ID). Every item carries M5 status, score and confidence when valid, evidence count, calculation state, level, reason code/text, and optional latest practice time and whole elapsed days. Ownership and leaf selection reuse M8/M5. It reads source-verified M5 submitted diagnostic/practice Evidence in batches and rechecks the current persisted state and evidence fingerprint. Latest practice is the maximum associated submitted `Response.submitted_at` for verified practice evidence, never an upload or diagnostic timestamp. Comparisons use UTC and server time; frontend displays local time. A missing or future practice timestamp is not converted to a negative age or a low-risk claim.

Rule order is explicit:

1. Uncalculated, stale, unavailable or insufficient-confidence mastery: insufficient_data; a concurrently inconsistent reread is also unavailable.
2. Future or missing submitted-practice time: insufficient_data.
3. M5 possibly_weak or needs_attention: review_due, reason weak mastery.
4. M5 needs_reinforcement: watch.
5. No valid practice: watch, no practice.
6. Low confidence: watch.
7. With medium/high confidence and valid practice, an elapsed interval of at least 30 days: review_due; at least 14 days: watch. Within 14 days, fewer than three distinct submitted practice responses is watch; otherwise low_risk.

The 14- and 30-day intervals and three recent practice facts are deliberately coarse V1 heuristic reminders in code constants; the count is not a confidence calculation. The minimum of three echoes M5's minimum independent-evidence scale but is a separate reminder condition; there is no existing M5/M6 interval, no empirical forgetting model, and no claim that mastery fell. Weakness uses M5 classifications, not a new score threshold. No evidence is never low risk. A low-risk result means no present reminder, not complete mastery. GET performs no write, snapshot, recommendation, session creation or LLM call. No M8-4 database migration is required.

The Progress page combines M8-2 weak points with risk reminders in one region, deduplicated by node ID. The independent risk request has its own loading, error and retry states; existing weak points remain visible if it fails. The counts include all leaf nodes even if the bounded list is truncated, and the UI reports truncation. Overview and risk are separate reads and may briefly differ if learning state changes concurrently; a retry refreshes the reminder, while a full course reload refreshes both.
