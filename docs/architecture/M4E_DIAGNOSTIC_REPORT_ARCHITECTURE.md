# LearnPilot V1 — M4-E Diagnostic Report Architecture

## Scope

M4-E adds a read-only report for an already submitted initial diagnostic: overall persisted score, per-node performance,
evidence labels, question review, historical source references, and a safe link to the existing M3 knowledge map. It
does not create Mastery, Confidence, Learning Evidence, recommendations, trends, or an M4-F flow.

## Non-Negotiable M4 Architecture Decisions

- **ARCH-01 — Deterministic scoring:** reports consume `Response.is_correct` and `Response.points_awarded` persisted by
  M4-C. They neither invoke an LLM nor rerun the scorer.
- **ARCH-02 — Historical reproducibility:** report content comes from `AssessmentQuestion.question_snapshot`, including
  historical node name, answer key, explanation, source references, and policy. Current Question/KnowledgeNode content
  is never used to reconstruct it.
- **ARCH-03 — Structured protected responses:** the report is a GET-only projection. Submitted answers and scores have
  no report write path and remain protected by the M4-A/M4-C lifecycle.

## Historical Inputs and Versioning

`DiagnosticReportService` reads the submitted Assessment, immutable snapshots, and persisted responses in one read
transaction. `assessments.report_policy_version` is set during the existing atomic submit transition; legacy submitted
attempts safely resolve to `diagnostic_node_performance_v1`. Unknown versions are rejected rather than silently using
new thresholds. The report contains no stored analytics table and GET has no data mutation.

## Node Aggregation

Only the snapshot's exactly-one `PRIMARY` knowledge-node reference is counted. A question therefore contributes once
to formal node statistics; `SECONDARY` references remain explanatory metadata. For each node, M4-E returns question,
answered, correct, incorrect, unanswered counts and `correct_count / question_count`. Unanswered questions are in the
denominator but are separately visible. A zero-question node has `accuracy: null`, never a fabricated zero percent.

## Evidence and Preliminary Status

`diagnostic_node_performance_v1` is an explicit V1 heuristic:

| Associated questions | Evidence | Preliminary status |
|---|---|---|
| 0 | NOT_ASSESSED | NOT_ASSESSED |
| 1–2 | LIMITED_EVIDENCE | LIMITED_EVIDENCE |
| 3+, accuracy < 50% | BASIC_EVIDENCE | NEEDS_ATTENTION |
| 3+, 50%–<80% | BASIC_EVIDENCE | PARTIALLY_CORRECT |
| 3+, >=80% | BASIC_EVIDENCE | GOOD_PERFORMANCE |

These labels describe this diagnostic only, not permanent ability or mastery.

## API and Frontend

The existing `GET /api/diagnostics/assessments/{assessment_id}/result` response is extended rather than duplicated.
It returns review answers/explanations only after the assessment is submitted and only through existing owner scope.
`/diagnose/assessments/:assessmentId/result` renders the overview, performance cards, source-aware question review,
and history-safe report.

For each historical node, `map_available` is a current-course existence check by exact ID only. A true value navigates
to the existing M3 course knowledge map using `tab=knowledge-structure&nodeId=…`. A missing/rebuilt node retains its
historical name and result but cannot be guessed or name-matched to another node.

## Sources and Boundaries

Snapshot sources remain visible even if their Material is later absent. Availability is an optional present-day marker;
it does not change historical citations. M4-F may use this report as an integration surface. M5 may consume the
structured assessment, snapshot, response, and persisted score inputs, but no Evidence Engine is implemented here.
