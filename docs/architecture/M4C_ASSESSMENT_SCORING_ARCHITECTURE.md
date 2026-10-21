# LearnPilot V1 — M4-C Assessment Assembly & Deterministic Scoring Architecture

## Scope

M4-C consumes the M4-B validated question bank, assembles an immutable initial diagnostic, exposes an answer-safe
candidate representation, scores locked structured answers with deterministic exact-match rules, persists per-response
scores, and returns basic attempt statistics. It adds no LLM call, student API, Vue experience, diagnostic report,
weakness analysis, mastery, confidence, evidence engine, or recommendation behavior.

## Non-Negotiable M4 Architecture Decisions

- **ARCH-01 — Deterministic Scoring:** `DeterministicObjectiveScorer` is pure application logic. It reads only an
  immutable `AssessmentQuestion` snapshot and a structured submitted answer. It never imports or invokes an LLM, reads
  the live Question answer, trusts client score fields, or performs text-semantic matching.
- **ARCH-02 — Historical Reproducibility:** assembly freezes ordered M4-A snapshots. Scoring and summary reads use those
  snapshots and persisted Response scores. Question-bank changes and KnowledgeNode rebuilds cannot change the paper or
  its result.
- **ARCH-03 — Structured Protected Responses:** each paper item has one structured Response. An empty
  `selected_options` array explicitly represents unanswered. Submission, score persistence, answer locking, and the
  `SUBMITTED` transition share one transaction. Repeated identical submission is read-only and idempotent.

These decisions remain binding for M4-D through M4-F.

## Assembly Input and Eligibility

`AssessmentAssemblyService` accepts `owner_id` and `course_id`. It queries only the course’s
`QuestionValidationStatus.VALIDATED` rows. A question remains eligible only when:

- M4-A can reconstruct a complete validated snapshot from it;
- it has non-empty M4-B source references;
- it has exactly one active PRIMARY KnowledgeNode in the target course;
- that node is in the current core-node scope; and
- its normalized stem is not an obvious duplicate already admitted to the candidate pool.

Pending, rejected, cross-course, source-less, structurally invalid, duplicate, and inactive-node questions are
excluded. Assembly does not rerun M4-B’s LLM or source review.

## Knowledge Coverage Strategy

Active HIGH and MEDIUM importance nodes are the default core scope. If a course has only LOW nodes, all active nodes
become the fallback scope. Nodes are ordered by importance (`HIGH`, `MEDIUM`, `LOW`) and then stable integer ID.

Selection uses `knowledge_coverage_greedy_v1`:

1. Prefer an uncovered core node over any already covered node.
2. Among uncovered nodes, prefer higher importance.
3. Within that constraint, prefer the largest remaining type and difficulty deficit.
4. After coverage, prefer the least represented node.
5. Break every tie by immutable Question ID.

No randomness, LLM decision, integer programming, or hidden state is involved. The same bank and node state produce
the same selected Question IDs and order.

## Dynamic Question Count

The target is bounded to 8–20 and then constrained by the eligible bank:

- 1–4 core nodes: recommended 8;
- 5–10 core nodes: 10–15 using approximately 1.25 questions per node;
- more than 10 core nodes: 15–20 using the same bounded growth rule.

The service never invents or lowers quality to fill a quota. Fewer than eight eligible questions, or failure to cover
every required core node up to the target capacity, returns `QUESTION_BANK_INSUFFICIENT` with available question,
eligible node, covered node, and required question counts. No partial Assessment remains.

## Type and Difficulty Distribution

The deterministic soft targets are 70% single choice, 20% true/false, and the remainder multiple choice; difficulty
targets are 30% easy, 50% medium, and the remainder hard. Coverage always has priority. If the validated bank lacks a
target category, the algorithm selects the best remaining eligible question and reports the actual distributions in
`AssemblyMetadataSchema`. It never selects a pending or invalid item merely to match a ratio.

Difficulty is M4-B’s initial label and is not treated as empirically calibrated psychometric difficulty.

## Fixed Snapshot and Lifecycle

Assembly creates a DRAFT Assessment, selects the complete question list, validates and writes ordered
`assessment_question_v1` snapshots, then changes the same row to READY—all in one transaction. Snapshot insertion
failure rolls back the Assessment and every preceding item. Existing M4-A transitions remain:

```text
DRAFT -> READY -> IN_PROGRESS -> SUBMITTED
```

There is no normal update method for snapshot JSON or order after READY.

## Candidate Answer Isolation

`candidate_questions` resolves by owner and converts snapshots to `CandidateAssessmentQuestionSchema`. It contains only
assessment question ID, order, type, stem, options, and difficulty. It excludes `correct_answer`, explanation, scoring
policy, source evidence, and every scoring internal. M4-C exposes no public API; this is the safe service contract for
future M4-D use.

## Deterministic Scoring Rules

The only supported policy is `objective_exact_match_v1`. Unknown versions return `SCORING_POLICY_UNSUPPORTED`; they
never fall back to a current default.

- Single choice: zero or one normalized option; exact key match earns `max_points`, otherwise zero.
- True/false: only canonical `TRUE` or `FALSE`; exact match earns full points. Localized text such as 对/错 is invalid.
- Multiple choice: set equality is required, so `[A, C]` equals `[C, A]`; missing or extra options earn zero.
- Unanswered: `selected_options=[]`, persisted as a structured Response and scored zero.
- Unknown option keys, duplicate keys, malformed inputs, and unsupported policies are rejected.

The scorer returns `is_correct`, `points_awarded`, `max_points`, and the policy version. There is no partial credit,
negative marking, semantic grading, or Question-table lookup.

## Submission Transaction

M4-A’s submission boundary now performs the M4-C extension inside its existing `session.begin()`:

```text
Require owned IN_PROGRESS assessment
  -> validate one structured answer per snapshot
  -> create/update draft Responses
  -> load the complete response set
  -> score every snapshot/answer pair deterministically
  -> write Response.is_correct and Response.points_awarded
  -> stamp all Responses and compare-and-set Assessment to SUBMITTED
  -> commit
```

Any answer, snapshot, policy, score, constraint, or state failure rolls back every answer and score. Identical repeat
submission returns the existing submitted Assessment without rescoring; a changed payload is rejected.

## Score Persistence and Basic Statistics

M4-A already reserved nullable `Response.is_correct` and `Response.points_awarded`, so M4-C needs no migration. They
become non-null through successful M4-C submission. `score_summary` reads persisted scores and immutable snapshot
maximum points to return total questions, answered questions, correct questions, total/earned points, and accuracy.

The summary describes only this objective assessment. It is not mastery, confidence, long-term evidence aggregation,
weakness analysis, or a knowledge-node diagnostic report.

## Historical Reproducibility

Changing or deleting the source Question, renaming/rebuilding a KnowledgeNode, or changing the current bank never
changes stored snapshots, responses, or scores. Candidate rendering, scoring, and basic result reads do not reconstruct
history through current Question or KnowledgeNode rows.

## Ownership and Course Boundaries

Assembly requires an owner-scoped Course. Candidate and result reads require an owner-scoped Assessment. The bank query
is course-scoped, primary links retain composite course foreign keys, snapshots are attached only to the newly created
course Assessment, and response composite foreign keys prevent cross-assessment attachment.

## M4-D and M4-E Boundaries

- M4-D may call assembly, lifecycle, candidate-view, response, and submission services through new authenticated API
  routes. It must not expose internal snapshots before the applicable result boundary.
- M4-E may derive knowledge-level performance and report views from immutable snapshots plus persisted deterministic
  scores. M4-C deliberately does not implement that analysis.
- Future M5 may consume the structured snapshot/answer/score records as raw evidence input. M4-C creates no M5 model.

## Known Limitations

- The assembly policy is intentionally greedy and explainable, not globally optimized.
- Exact duplicate filtering uses normalized stems; it does not introduce embedding similarity.
- Actual type/difficulty distributions can differ from soft targets when coverage or bank availability requires it.
- Assembly metadata is returned by the service; persisted snapshots remain the historical truth and allow the actual
  distribution to be reconstructed after restart.
- Aggregate score statistics are derived from persisted response scores rather than duplicated in an Assessment field.

