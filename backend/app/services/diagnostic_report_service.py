from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import KnowledgeNode, Material
from backend.app.models import AssessmentStatus, KnowledgeRelationRole
from backend.app.repositories import AssessmentRepository, ResponseRepository
from backend.app.schemas.diagnostic import AssessmentQuestionSnapshotSchema
from backend.app.schemas.diagnostic_api import (
    DiagnosticHistoricalNodeSchema,
    DiagnosticNodePerformanceSchema,
    DiagnosticQuestionReviewSchema,
    DiagnosticResultSchema,
    DiagnosticSourceReferenceSchema,
)

DIAGNOSTIC_REPORT_POLICY_VERSION = "diagnostic_node_performance_v1"


class DiagnosticReportError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class DiagnosticReportService:
    """Read-only M4-E aggregation over immutable snapshots and persisted M4-C scores."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.assessments = AssessmentRepository(session)
        self.responses = ResponseRepository(session)

    def build_report(self, owner_id: int, assessment_id: int) -> DiagnosticResultSchema:
        with self.session.begin():
            assessment = self.assessments.get_for_owner(assessment_id, owner_id)
            if assessment is None:
                raise DiagnosticReportError("ASSESSMENT_NOT_FOUND", "Assessment not found.")
            if assessment.status != AssessmentStatus.SUBMITTED or assessment.submitted_at is None:
                raise DiagnosticReportError("ASSESSMENT_NOT_SUBMITTED", "A report is available only after submission.")
            policy_version = assessment.report_policy_version or DIAGNOSTIC_REPORT_POLICY_VERSION
            if policy_version != DIAGNOSTIC_REPORT_POLICY_VERSION:
                raise DiagnosticReportError(
                    "REPORT_POLICY_UNSUPPORTED", "The historical report policy is not supported."
                )
            questions = self.assessments.list_questions(assessment.id)
            responses = {
                item.assessment_question_id: item for item in self.responses.list_for_assessment(assessment.id)
            }
            if set(responses) != {item.id for item in questions}:
                raise DiagnosticReportError("ASSESSMENT_INCOMPLETE", "Submitted assessment responses are incomplete.")
            snapshots = [
                (item, AssessmentQuestionSnapshotSchema.model_validate(item.question_snapshot)) for item in questions
            ]
            material_ids = {
                ref.material_id for _, snapshot in snapshots for ref in snapshot.source_refs if ref.material_id
            }
            available_material_ids = (
                set(
                    self.session.scalars(
                        select(Material.id).where(
                            Material.course_id == assessment.course_id, Material.id.in_(material_ids)
                        )
                    )
                )
                if material_ids
                else set()
            )
            node_ids = {node.id for _, snapshot in snapshots for node in snapshot.knowledge_nodes}
            available_node_ids = (
                set(
                    self.session.scalars(
                        select(KnowledgeNode.id).where(
                            KnowledgeNode.course_id == assessment.course_id,
                            KnowledgeNode.id.in_(node_ids),
                            KnowledgeNode.is_active.is_(True),
                        )
                    )
                )
                if node_ids
                else set()
            )
            return self._aggregate(
                assessment, snapshots, responses, available_material_ids, available_node_ids, policy_version
            )

    def _aggregate(self, assessment, snapshots, responses, material_ids, node_ids, policy_version):
        counts = defaultdict(
            lambda: {
                "question_count": 0,
                "answered_count": 0,
                "correct_count": 0,
                "incorrect_count": 0,
                "unanswered_count": 0,
                "name": "",
            }
        )
        reviews: list[DiagnosticQuestionReviewSchema] = []
        earned, total = Decimal("0"), Decimal("0")
        answered_total = correct_total = 0
        for question, snapshot in snapshots:
            response = responses[question.id]
            if response.is_correct is None or response.points_awarded is None:
                raise DiagnosticReportError(
                    "SCORE_RESULT_MISSING", "Submitted assessment has no persisted score result."
                )
            selected = list(response.answer_payload.get("selected_options", []))
            primary = next(node for node in snapshot.knowledge_nodes if node.role == KnowledgeRelationRole.PRIMARY)
            bucket = counts[primary.id]
            bucket["name"], bucket["question_count"] = primary.name, bucket["question_count"] + 1
            if selected:
                bucket["answered_count"] += 1
                answered_total += 1
                if response.is_correct:
                    bucket["correct_count"] += 1
                    correct_total += 1
                else:
                    bucket["incorrect_count"] += 1
            else:
                bucket["unanswered_count"] += 1
            total += Decimal(snapshot.scoring_policy.max_points)
            earned += Decimal(response.points_awarded)

            def node_view(node) -> DiagnosticHistoricalNodeSchema:
                return DiagnosticHistoricalNodeSchema(
                    historical_node_id=node.id,
                    historical_node_name=node.name,
                    map_available=node.id in node_ids,
                )

            reviews.append(
                DiagnosticQuestionReviewSchema(
                    assessment_question_id=question.id,
                    order_index=question.order_index,
                    question_type=snapshot.question_type,
                    stem=snapshot.stem,
                    options=snapshot.options,
                    selected_options=selected,
                    correct_answer=snapshot.correct_answer,
                    explanation=snapshot.explanation,
                    is_correct=response.is_correct,
                    points_awarded=Decimal(response.points_awarded),
                    primary_node=node_view(primary),
                    secondary_nodes=[
                        node_view(node)
                        for node in snapshot.knowledge_nodes
                        if node.role == KnowledgeRelationRole.SECONDARY
                    ],
                    source_refs=[
                        DiagnosticSourceReferenceSchema(
                            **ref.model_dump(), is_accessible=ref.material_id in material_ids
                        )
                        for ref in snapshot.source_refs
                    ],
                )
            )
        performance = [
            self._performance(node_id, values, node_id in node_ids)
            for node_id, values in sorted(counts.items(), key=lambda item: (item[1]["name"].casefold(), item[0]))
        ]
        return DiagnosticResultSchema(
            assessment_id=assessment.id,
            course_id=assessment.course_id,
            course_name=assessment.course.name,
            submitted_at=assessment.submitted_at,
            total_questions=len(snapshots),
            answered_questions=answered_total,
            correct_questions=correct_total,
            total_points=total,
            earned_points=earned,
            accuracy=earned / total if total else Decimal("0"),
            report_policy_version=policy_version,
            covered_knowledge_nodes=len(performance),
            needs_attention_nodes=sum(item.preliminary_status == "needs_attention" for item in performance),
            knowledge_performance=performance,
            question_reviews=reviews,
        )

    @staticmethod
    def _performance(node_id: int, values: dict, map_available: bool) -> DiagnosticNodePerformanceSchema:
        question_count = values["question_count"]
        accuracy = Decimal(values["correct_count"]) / Decimal(question_count) if question_count else None
        if question_count == 0:
            evidence, status = "not_assessed", "not_assessed"
        elif question_count < 3:
            evidence, status = "limited_evidence", "limited_evidence"
        elif accuracy < Decimal("0.5"):
            evidence, status = "basic_evidence", "needs_attention"
        elif accuracy < Decimal("0.8"):
            evidence, status = "basic_evidence", "partially_correct"
        else:
            evidence, status = "basic_evidence", "good_performance"
        return DiagnosticNodePerformanceSchema(
            historical_node_id=node_id,
            historical_node_name=values["name"],
            map_available=map_available,
            question_count=question_count,
            answered_count=values["answered_count"],
            correct_count=values["correct_count"],
            incorrect_count=values["incorrect_count"],
            unanswered_count=values["unanswered_count"],
            accuracy=accuracy,
            evidence_status=evidence,
            preliminary_status=status,
        )
