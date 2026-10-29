import pytest
from sqlalchemy import select

from backend.app.db.models import KnowledgeNode, MaterialContent
from backend.app.services.knowledge_canonicalization_service import KnowledgeCanonicalizationError
from backend.tests.test_m3c_knowledge_canonicalization import (
    CandidateSpec,
    ScriptedCanonicalClient,
    add_current_extraction,
    make_service,
    seed_data,
)
from backend.tests.test_m3c_knowledge_canonicalization import database as database


def test_exact_duplicates_across_materials_do_not_consume_distinct_limit(database):
    factory, base_settings = database
    settings = base_settings.model_copy(update={"knowledge_canonicalization_max_candidates": 2})
    with factory() as session:
        seed = seed_data(
            session,
            settings,
            [
                [CandidateSpec("C++"), CandidateSpec("C#")],
                [CandidateSpec("c++"), CandidateSpec("c#")],
            ],
        )
        client = ScriptedCanonicalClient([{"groups": []}])
        result = make_service(session, settings, client).canonicalize(seed.course_id)
        assert len(result.nodes) == 2
        assert len(result.resolutions) == 4
        assert len({node.normalized_name for node in result.nodes}) == 2
        assert {node.normalized_name for node in result.nodes} == {"c++", "c#"}
        assert all({source.material_id for source in node.sources} == set(seed.material_ids) for node in result.nodes)


@pytest.mark.parametrize(
    "materials",
    [
        [["Alpha", "Beta", "Gamma"]],
        [["Alpha", "Beta"], ["Alpha", "Beta"], ["Alpha"]],
    ],
)
def test_distinct_and_raw_bounds_remain_enforced(database, materials):
    factory, base_settings = database
    settings = base_settings.model_copy(update={"knowledge_canonicalization_max_candidates": 2})
    client = ScriptedCanonicalClient([{"groups": []}])
    with factory() as session:
        seed = seed_data(session, settings, [[CandidateSpec(name) for name in group] for group in materials])
        with pytest.raises(KnowledgeCanonicalizationError) as error:
            make_service(session, settings, client).canonicalize(seed.course_id)
        assert error.value.code == "KNOWLEDGE_CANONICALIZATION_NOT_READY"
        assert "超过单次知识结构构建能力" in error.value.message
        assert client.calls == 0


def test_limit_failure_preserves_current_model_and_later_retry_succeeds(database):
    factory, base_settings = database
    settings = base_settings.model_copy(update={"knowledge_canonicalization_max_candidates": 2})
    with factory() as session:
        seed = seed_data(session, settings, [[CandidateSpec("Alpha")]])
        service = make_service(session, settings, lambda _settings: None)
        first = service.canonicalize(seed.course_id)
        node_id, run_id = first.nodes[0].id, first.run.id
        with session.begin():
            content = session.scalar(select(MaterialContent).where(MaterialContent.material_id == seed.material_ids[0]))
            add_current_extraction(
                session,
                course_id=seed.course_id,
                material_id=seed.material_ids[0],
                content_hash=content.content_hash,
                reference="TXT segment 1",
                candidates=[CandidateSpec("Alpha"), CandidateSpec("Beta"), CandidateSpec("Gamma")],
            )
        with pytest.raises(KnowledgeCanonicalizationError):
            service.canonicalize(seed.course_id, regenerate=True)
        current = service.get_canonicalization(seed.course_id)
        assert current.run.id == run_id
        assert [node.id for node in current.nodes] == [node_id]
        with session.begin():
            content = session.scalar(select(MaterialContent).where(MaterialContent.material_id == seed.material_ids[0]))
            add_current_extraction(
                session,
                course_id=seed.course_id,
                material_id=seed.material_ids[0],
                content_hash=content.content_hash,
                reference="TXT segment 1",
                candidates=[CandidateSpec("Alpha")],
            )
        retried = service.canonicalize(seed.course_id, regenerate=True)
        assert retried.nodes[0].id == node_id
        assert session.get(KnowledgeNode, node_id).is_active
