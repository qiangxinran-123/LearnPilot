# LearnPilot V1 — M5-C Mastery & Confidence Model

## 1. Domain Boundary

M5-C consumes persisted `LearningEvidence` and maintains one current `StudentKnowledgeState` for a user, course, and
active current knowledge node. It does not read raw answers to rescore them, invoke an LLM, update M4 records, modify
Evidence, expose an HTTP API, or implement a frontend/recommendation feature.

Only Evidence with an explicit M5-B `current_knowledge_node_id` matching the target is eligible. Historical Evidence
whose current mapping is NULL remains preserved but is excluded from current-node calculation.

## 2. Mastery Definition and Configuration

The versioned algorithm is `mastery_v1`:

```text
MasteryScore = 100 × (λ × m0 + Σ(w_i × x_i)) / (λ + Σw_i)

m0 = 0.5
λ  = 2.0
```

`x_i` is the persisted Evidence `normalized_score`. The effective weight is:

```text
w_i = difficulty_weight × source_weight × attribution_weight
```

The M5-B attribution weight is applied exactly once. Configuration is centralized in
`backend/app/services/mastery_config.py`:

| Parameter | Value |
|---|---:|
| easy | 1.0 |
| medium | 1.2 |
| hard | 1.4 |
| diagnostic source | 1.0 |
| minimum independent Evidence | 3 |

Scores are calculated with `Decimal` and published to two decimal places using half-up rounding. The result is an
explainable heuristic estimate, not a calibrated probability or a restatement of raw accuracy.

## 3. Evidence Eligibility and Independence

`MasteryService` scopes the query by exact `user_id`, `course_id`, and `current_knowledge_node_id`, then requires:

- an active target node in the requested course;
- course ownership by the requested user;
- historical and current node IDs both equal to the target;
- supported source and difficulty enums;
- score in `[0, 1]` and attribution weight in `(0, 1]`;
- one compatible knowledge-model version across the eligible set.

An independent fact is identified by source type, Assessment, immutable question occurrence, Response, and current
node. Exact repeated inputs are deduplicated. Multiple Evidence schema versions of the same fact do not increase the
independent count; conflicting values for one fact are rejected as `CONFLICTING_DUPLICATE_EVIDENCE`.

`evidence_count` records unique Evidence identities, while `independent_evidence_count` records unique answer facts.
The mastery formula and confidence rules use only independent facts.

## 4. Insufficient Evidence and Mastery Status

With fewer than three valid independent facts, the engine may validate the inputs but publishes:

```text
mastery_score = NULL
mastery_status = NOT_ASSESSED
confidence_level = INSUFFICIENT
```

For published scores, status is deterministic:

| Score | Status |
|---:|---|
| 80–100 | `GOOD_PERFORMANCE` |
| 60–<80 | `NEEDS_REINFORCEMENT` |
| 40–<60 | `POSSIBLY_WEAK` |
| 0–<40 | `NEEDS_ATTENTION` |

These states are calculated from M5-C mastery and do not reuse M4 report attention labels.

## 5. Confidence Rules

Confidence is calculated independently from Mastery:

| Independent Evidence | Base confidence |
|---:|---|
| 0–2 | `INSUFFICIENT` |
| 3–5 | `LOW` |
| 6–9 | `MEDIUM` |
| 10+ | `HIGH` candidate |

`HIGH` additionally requires at least two Assessments and at least two difficulty levels. A single Assessment or one
difficulty caps a `HIGH` candidate at `MEDIUM`. For each Assessment, the engine calculates a deterministic weighted
mean. If the maximum difference between Assessment means exceeds `0.40`, confidence is capped at `MEDIUM`.

The ordered explanation codes are:

- `INSUFFICIENT_EVIDENCE`;
- `SINGLE_ASSESSMENT`;
- `LIMITED_DIFFICULTY_COVERAGE`;
- `PERFORMANCE_VARIATION`;
- `SUFFICIENT_EVIDENCE`.

## 6. StudentKnowledgeState Schema

`student_knowledge_states` stores:

- user, course, and current knowledge-node identity;
- the single compatible historical knowledge-model version, when present;
- nullable mastery score and deterministic status;
- confidence level and JSON reason-code list;
- unique Evidence count, independent fact count, and Assessment count;
- algorithm version, Evidence fingerprint, and calculation timestamp.

The database unique key `(user_id, course_id, knowledge_node_id)` guarantees one current state. A composite foreign
key proves that the node belongs to the course. CHECK constraints protect score/count/fingerprint ranges. This table
is derived current state only; it does not replace Evidence or create historical mastery snapshots.

## 7. Fingerprint and Idempotency

The SHA-256 fingerprint uses canonical JSON with fixed key ordering, stable Evidence ordering, normalized decimal
text, and no timestamps or Python `hash()`. Each row contributes its stable source identity, normalized score,
effective weight, historical node, knowledge-model version, difficulty, and Evidence schema version.

The service compares both fingerprint and `algorithm_version`. If both match the persisted state, it performs no
write and preserves `calculated_at`. New Evidence changes the fingerprint. An algorithm-version change recalculates
the same state row without modifying source Evidence.

## 8. Transactions and Reproducibility

Target validation, Evidence read, calculation, and state insert/update occur in one caller-provided SQLAlchemy Session
transaction. A persistence failure rolls back the state write. M4 Assessment/Snapshot/Response and M5 Evidence are
never written by the service. A result can be rebuilt from immutable Evidence plus the named algorithm configuration.

## 9. Historical Node and Version Safety

No name-based mapping exists. Evidence with no confirmed M5-B current-node mapping is excluded. Eligible rows must
retain exact historical/current target identity. If eligible Evidence contains more than one knowledge-model version,
the service rejects calculation with `INCOMPATIBLE_KNOWLEDGE_MODEL_VERSIONS` rather than merging versions silently.

The current M3 node model has no independent graph-version column. M5-C therefore relies on M5-B's explicit stable-ID
mapping and preserves the Evidence snapshot version; it does not invent a current graph version.

## 10. Future Evidence Sources

Calculators depend on `MasteryEvidenceSchema`, not Assessment or Response ORM objects. A future authorized stage may
add source weights and new `LearningEvidence` source enum values for practice/review/session evidence. M5-C creates no
such source records or workflows.

## 11. Known Limitations

- The formula is a transparent competition-grade heuristic, not psychometric calibration, BKT, or DKT.
- Confidence variation uses a fixed cross-Assessment range threshold, not a statistical significance test.
- States are refreshed through `MasteryService`; M5-C does not add an API, queue, scheduler, or submission hook.
- Mixed knowledge-model versions require an explicit future migration policy and are not merged.
- No mastery history, recommendations, learning path, analytics dashboard, or frontend overlay is implemented.
