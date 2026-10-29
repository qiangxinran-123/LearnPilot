from backend.app.db.models import CourseKnowledgeBuildState, KnowledgeNode
from backend.app.services.course_knowledge_build_job_service import CourseKnowledgeBuildJobService
from backend.tests.test_m3e_knowledge_workspace_status import database as database
from backend.tests.test_m3e_knowledge_workspace_status import seed_course


def test_success_without_nodes_is_distinct_from_never_built_or_failure(database):
    factory, settings = database
    with factory() as session:
        course_id, _, _, node_ids, _ = seed_course(session, settings)
        service = CourseKnowledgeBuildJobService(session, settings)
        service.start(course_id)
        with session.begin():
            state = session.get(CourseKnowledgeBuildState, course_id)
            state.status = "success"
            state.stage = "complete"
            state.success_material_snapshot_hash = state.requested_material_snapshot_hash
            for node_id in node_ids:
                session.get(KnowledgeNode, node_id).is_active = False
        status = service.get_status(course_id)
        assert status.state == "ready"
        assert status.node_count == 0
        assert status.has_model is False
        with session.begin():
            state = session.get(CourseKnowledgeBuildState, course_id)
            state.status = "failed"
        assert service.get_status(course_id).state == "failed"
