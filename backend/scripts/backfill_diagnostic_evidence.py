from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from backend.app.db.models import Assessment
from backend.app.models import AssessmentStatus
from backend.app.services.diagnostic_evidence_ingestion import EvidenceIngestionError, EvidenceIngestionService


@dataclass
class BackfillSummary:
    dry_run: bool
    assessments_scanned: int = 0
    assessments_eligible: int = 0
    evidence_planned: int = 0
    evidence_created: int = 0
    evidence_skipped: int = 0
    invalid_snapshot_count: int = 0
    scoring_incomplete_count: int = 0
    unmapped_historical_node_count: int = 0
    errors: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill LearningEvidence from submitted M4 diagnostics.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, future=True, pool_pre_ping=True, connect_args=connect_args)
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def backfill_diagnostic_evidence(*, database_url: str, dry_run: bool = False) -> BackfillSummary:
    engine = _engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    summary = BackfillSummary(dry_run=dry_run)
    try:
        with factory() as session, session.begin():
            rows = list(session.execute(select(Assessment.id, Assessment.status).order_by(Assessment.id)))
        summary.assessments_scanned = len(rows)
        for assessment_id, status in rows:
            if status != AssessmentStatus.SUBMITTED:
                continue
            summary.assessments_eligible += 1
            with factory() as session:
                try:
                    result = EvidenceIngestionService(session).ingest_assessment(
                        assessment_id,
                        dry_run=dry_run,
                    )
                except EvidenceIngestionError as error:
                    summary.errors.append(
                        {
                            "assessment_id": assessment_id,
                            "code": error.code,
                            "message": error.message,
                        }
                    )
                    continue
            summary.evidence_planned += result.candidates - result.skipped
            summary.evidence_created += result.created
            summary.evidence_skipped += result.skipped
            summary.unmapped_historical_node_count += result.unavailable_historical_nodes
            for issue in result.issues:
                if issue.code == "INVALID_QUESTION_SNAPSHOT":
                    summary.invalid_snapshot_count += 1
                if issue.code == "SCORING_INCOMPLETE":
                    summary.scoring_incomplete_count += 1
                summary.errors.append(issue.model_dump(mode="json"))
    finally:
        engine.dispose()
    return summary


def main() -> int:
    args = parse_args()
    summary = backfill_diagnostic_evidence(database_url=args.database_url, dry_run=args.dry_run)
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 1 if summary.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
