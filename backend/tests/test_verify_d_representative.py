from __future__ import annotations

import hashlib
import io
import json
import re

import pytest
from docx import Document
from sqlalchemy import select

from backend.app.ai import AIServiceError, GeneratedStructuredOutput, LLMClient
from backend.app.ai.chunking import chunk_segments
from backend.app.db.models import KnowledgeEdge, KnowledgeNode, KnowledgeSource, Material, MaterialContent
from backend.app.documents.parser import DocxDocumentParser
from backend.app.models import KnowledgeRelationType
from backend.app.services.course_knowledge_build_service import CourseKnowledgeBuildError
from backend.app.services.knowledge_extraction_service import ReadyExtractionMaterial
from backend.tests.test_m3b_knowledge_extraction import database as database
from backend.tests.test_m3b_knowledge_extraction import make_service as extraction_service
from backend.tests.test_m3b_knowledge_extraction import seed_data
from backend.tests.test_m3c_knowledge_canonicalization import make_service as canonical_service
from backend.tests.test_m3d_knowledge_relationships import make_relationship_service
from backend.tests.test_m3e_course_knowledge_build import make_service as build_service

TOPICS = [
    (
        "Cache",
        (
            "A cache stores selected memory blocks close to the processor. A hit uses a copy "
            "already present, while a miss requires fetching a block from a lower level. "
            "Locality describes reuse in time and neighboring addresses. The organization "
            "influences lookup cost and capacity."
        ),
    ),
    (
        "Address Mapping",
        (
            "Address mapping divides a memory address into fields used to locate a cache entry. "
            "The index selects a candidate location and a tag distinguishes blocks that map to "
            "the same index. Block offsets select the requested bytes. These fields depend on "
            "cache and block sizes."
        ),
    ),
    (
        "Direct Mapping",
        (
            "Direct mapping assigns each memory block to one cache location selected by its "
            "index. A tag comparison checks whether that location contains the requested block. "
            "Multiple memory blocks can compete for the same location, so address mapping is "
            "needed before studying the direct mapped organization."
        ),
    ),
    (
        "Replacement Policy",
        (
            "A replacement policy chooses a victim when a cache set has no empty entry. Least "
            "recently used chooses an entry based on the most recent time it was accessed, "
            "while FIFO uses insertion order. A policy matters only where more than one "
            "candidate entry is available."
        ),
    ),
]


UNIQUE_TOPICS = [
    ("Cache Coherence", "Coherence maintains a consistent view when processors cache shared memory locations."),
    ("Write Back", "A write back cache records modified data in the cache and later writes it to lower memory."),
    ("Write Through", "A write through cache propagates each cache write to the next memory level."),
    ("Prefetch", "Prefetching brings a predicted memory block closer to the processor before it is requested."),
    ("Associativity", "Associativity describes how many cache entries can be candidates within a set."),
    (
        "Translation Lookaside Buffer",
        "A translation lookaside buffer caches recent virtual to physical address translations.",
    ),
]


class RepresentativeClient(LLMClient):
    provider = "scripted"
    model = "verify-d-representative"

    def __init__(self):
        self.batches = []
        self.relationship_calls = 0
        self.fail_at = None
        self.contexts = []

    def generate_structured(self, *, operation, messages, schema):
        if operation == "knowledge_extraction":
            context = messages[1]["content"].split(chr(10) * 2, 1)[1]
            self.contexts.append(context)
            if self.fail_at == len(self.contexts):
                raise AIServiceError("AI_TIMEOUT", "Simulated isolated timeout.")
            references = list(dict.fromkeys(re.findall(r"^\[(DOCX 第 (\d+) 段)\]$", context, re.MULTILINE)))
            self.batches.append((len(context), [reference for reference, _ in references]))
            grouped = {}
            for reference, index in references:
                if int(index) == 9:
                    name = next(name for name, _ in UNIQUE_TOPICS if name in context)
                else:
                    name = TOPICS[(int(index) - 1) % len(TOPICS)][0]
                grouped.setdefault(name, []).append(reference)
            output = {
                "candidates": [
                    {
                        "name": name,
                        "description": f"{name} is an independently described course concept.",
                        "importance": "medium",
                        "difficulty": "intermediate",
                        "source_references": refs,
                    }
                    for name, refs in grouped.items()
                ]
            }
        elif operation == "knowledge_canonicalization":
            output = {"groups": []}
        elif operation == "knowledge_relationships":
            self.relationship_calls += 1
            block = json.loads(messages[1]["content"].split("Canonical nodes:\n", 1)[1])
            nodes = {node["name"]: node for node in block}
            target = nodes["Direct Mapping"]
            evidence = target["source_evidence"][0]
            citation = {"material_id": evidence["material_id"], "source_reference": evidence["source_reference"]}
            output = {
                "contains_edges": [
                    {
                        "source_node_id": nodes["Cache"]["node_id"],
                        "target_node_id": target["node_id"],
                        "reason": "Direct mapping is a cache organization.",
                        "evidence": [citation],
                    }
                ],
                "prerequisite_edges": [
                    {
                        "source_node_id": nodes["Address Mapping"]["node_id"],
                        "target_node_id": target["node_id"],
                        "reason": "Address mapping is needed to understand direct mapping.",
                        "evidence": [citation],
                    }
                ],
            }
        else:
            raise AssertionError(operation)
        return GeneratedStructuredOutput(schema.model_validate(output), self.provider, self.model)


def test_representative_multi_document_pipeline(database):
    factory, base_settings = database
    settings = base_settings.model_copy(
        update={"llm_context_chars": 2000, "llm_chunk_chars": 400, "llm_chunk_overlap_chars": 50}
    )
    client = RepresentativeClient()
    with factory() as db:
        seed = seed_data(db, settings)
        # Replace the two ready fixture texts and add four separately parsed documents.
        with db.begin():
            existing = list(
                db.scalars(select(Material).where(Material.id.in_([seed.material_id, seed.second_material_id])))
            )
            for doc_index in range(6):
                doc = Document()
                for paragraph in range(8):
                    topic, explanation = TOPICS[paragraph % len(TOPICS)]
                    doc.add_paragraph(
                        f"{topic}. Lecture {doc_index + 1}, section {paragraph + 1}. {explanation} "
                        f"In example {doc_index + 1}-{paragraph + 1}, students compare the described mechanism "
                        "with the surrounding stages and identify the evidence supporting its role."
                    )
                unique_name, unique_description = UNIQUE_TOPICS[doc_index]
                doc.add_paragraph(f"{unique_name}. {unique_description}")
                buffer = io.BytesIO()
                doc.save(buffer)
                parsed = DocxDocumentParser().parse(buffer.getvalue())
                assert parsed.status.value == "SUCCESS"
                if doc_index < 2:
                    material = existing[doc_index]
                    content = db.scalar(select(MaterialContent).where(MaterialContent.material_id == material.id))
                else:
                    material = Material(
                        course_id=seed.course_id,
                        title=f"Isolated lecture {doc_index + 1}",
                        material_type="docx",
                        summary="",
                        storage_status="NOT_STORED",
                        extraction_status="SUCCESS",
                        text_extracted=True,
                        text_length=len(parsed.text),
                        text_preview=parsed.text[:100],
                    )
                    db.add(material)
                    db.flush()
                    content = MaterialContent(material_id=material.id)
                    db.add(content)
                material.text_length = len(parsed.text)
                segments = [{"text": item.text, "source_reference": item.source_reference} for item in parsed.segments]
                content.plain_text = parsed.text
                content.segments = segments
                content.content_hash = hashlib.sha256(parsed.text.encode()).hexdigest()
                content.parser_name = parsed.parser_name
                content.parser_version = parsed.parser_version
                content.page_count = parsed.page_count

        docs = list(
            db.scalars(
                select(Material).where(Material.course_id == seed.course_id, Material.extraction_status == "SUCCESS")
            )
        )
        rows = list(db.scalars(select(MaterialContent).where(MaterialContent.material_id.in_([x.id for x in docs]))))
        material_ids = {item.id for item in docs}
        expected_chunks = [
            (chunk.source_reference, chunk.text)
            for row in sorted(rows, key=lambda item: item.material_id)
            for chunk in chunk_segments(row.segments, max_chars=400, overlap_chars=50)
        ]
        expected_batches = []
        for row in sorted(rows, key=lambda item: item.material_id):
            ready = ReadyExtractionMaterial(
                course_id=seed.course_id,
                material_id=row.material_id,
                material_content_hash=row.content_hash,
                plain_text=row.plain_text,
                segments=row.segments,
            )
            expected_batches.extend(
                batch.context for batch in extraction_service(db, settings, client)._build_batches(ready)
            )
        chunks = sum(len(chunk_segments(row.segments, max_chars=400, overlap_chars=50)) for row in rows)
        chars = sum(len(row.plain_text) for row in rows)
        db.rollback()
        service = build_service(
            db,
            settings,
            extraction_service(db, settings, client),
            canonical_service(db, settings, client),
            make_relationship_service(db, settings, client),
        )
        result = service.build(seed.course_id)
        assert result.material_count == 6
        assert result.node_count == 10
        assert result.contains_edge_count == result.prerequisite_edge_count == 1
        assert len(client.batches) > 6
        assert client.contexts == expected_batches
        observed_chunks = [
            (match.group(1), match.group(2))
            for context in client.contexts
            for match in re.finditer(r"^\[([^\]\n]+)\]\n(.*?)(?=\n\n\[|\Z)", context, re.MULTILINE | re.DOTALL)
        ]
        assert observed_chunks == expected_chunks
        assert all(len(context) <= settings.llm_context_chars for context in client.contexts)
        assert all(length <= settings.llm_context_chars + 500 for length, _ in client.batches)
        seen = {ref for _, refs in client.batches for ref in refs}
        assert seen == {f"DOCX 第 {number} 段" for number in range(1, 10)}
        nodes = list(
            db.scalars(
                select(KnowledgeNode).where(
                    KnowledgeNode.course_id == seed.course_id, KnowledgeNode.is_active.is_(True)
                )
            )
        )
        assert {node.name for node in nodes} == {topic for topic, _ in TOPICS + UNIQUE_TOPICS}
        sources = list(
            db.scalars(
                select(KnowledgeSource).where(KnowledgeSource.knowledge_node_id.in_([node.id for node in nodes]))
            )
        )
        assert {item.material_id for item in sources} == material_ids
        assert len(sources) == 54
        edges = list(db.scalars(select(KnowledgeEdge).where(KnowledgeEdge.course_id == seed.course_id)))
        assert {edge.relation_type for edge in edges} == {
            KnowledgeRelationType.CONTAINS,
            KnowledgeRelationType.PREREQUISITE,
        }
        assert all(
            edge.source_node_id in {node.id for node in nodes} and edge.target_node_id in {node.id for node in nodes}
            for edge in edges
        )
        print(
            f"VERIFY_D_SCALE documents=6 chunks={chunks} batches={len(client.batches)} "
            f"chars={chars} sources={len(sources)}"
        )

        original_names = {node.name for node in nodes}
        original_edges = {(edge.source_node_id, edge.target_node_id, edge.relation_type) for edge in edges}
        original_call_count = len(client.contexts)
        changed_id = max(material_ids)
        db.rollback()
        with db.begin():
            content = db.scalar(select(MaterialContent).where(MaterialContent.material_id == changed_id))
            changed = [dict(segment) for segment in content.segments]
            changed[0]["text"] += " The cache can also be compared using lookup latency."
            content.segments = changed
            content.plain_text = (chr(10) * 2).join(segment["text"] for segment in changed)
            content.content_hash = hashlib.sha256(content.plain_text.encode()).hexdigest()
        client.fail_at = original_call_count + 2
        with pytest.raises(CourseKnowledgeBuildError) as failure:
            service.build(seed.course_id)
        assert failure.value.code == "KNOWLEDGE_MODEL_BUILD_FAILED"
        assert "超时" in failure.value.message
        after_nodes = list(
            db.scalars(
                select(KnowledgeNode).where(
                    KnowledgeNode.course_id == seed.course_id, KnowledgeNode.is_active.is_(True)
                )
            )
        )
        after_edges = list(db.scalars(select(KnowledgeEdge).where(KnowledgeEdge.course_id == seed.course_id)))
        assert {node.name for node in after_nodes} == original_names
        assert {
            (edge.source_node_id, edge.target_node_id, edge.relation_type) for edge in after_edges
        } == original_edges
        db.rollback()
        client.fail_at = None
        retried = service.build(seed.course_id)
        assert retried.material_count == 6 and retried.node_count == 10
        calls_after_retry = len(client.contexts)
        repeated = service.build(seed.course_id)
        assert repeated.reused
        assert len(client.contexts) == calls_after_retry

    with factory() as reopened:
        persisted = list(
            reopened.scalars(
                select(KnowledgeNode).where(
                    KnowledgeNode.course_id == seed.course_id, KnowledgeNode.is_active.is_(True)
                )
            )
        )
        persisted_edges = list(reopened.scalars(select(KnowledgeEdge).where(KnowledgeEdge.course_id == seed.course_id)))
        persisted_sources = list(
            reopened.scalars(
                select(KnowledgeSource).where(KnowledgeSource.knowledge_node_id.in_([node.id for node in persisted]))
            )
        )
        assert {node.name for node in persisted} == {topic for topic, _ in TOPICS + UNIQUE_TOPICS}
        assert len(persisted_edges) == 2
        assert len(persisted_sources) == 54


def test_failed_parse_is_counted_separately_from_ready_documents(database):
    from backend.app.services.course_knowledge_build_job_service import CourseKnowledgeBuildJobService

    factory, settings = database
    with factory() as db:
        seed = seed_data(db, settings)
        with db.begin():
            material = db.get(Material, seed.not_ready_material_id)
            material.extraction_status = "PARSE_FAILED"
            material.extraction_error_code = "PDF_PARSE_ERROR"
        status = CourseKnowledgeBuildJobService(db, settings).get_status(seed.course_id)
        assert status.material_count == 3
        assert status.ready_material_count == 2
        assert status.failed_material_count == 1
        assert status.pending_parse_material_count == 0


def test_failed_database_write_rolls_back_candidates_and_reports_failure(database, monkeypatch):
    from backend.app.db.models import KnowledgeCandidate, KnowledgeExtractionRun
    from backend.app.models import KnowledgeExtractionStatus
    from backend.app.services.knowledge_extraction_service import KnowledgeExtractionError, KnowledgeExtractionService
    from backend.tests.test_m3b_knowledge_extraction import ScriptedClient, candidate

    factory, settings = database
    with factory() as db:
        seed = seed_data(db, settings)
        original = KnowledgeExtractionService._persist_candidates

        def fail_after_insert(self, run, aggregates):
            original(self, run, aggregates)
            raise RuntimeError("simulated isolated persistence failure")

        monkeypatch.setattr(KnowledgeExtractionService, "_persist_candidates", fail_after_insert)
        with pytest.raises(KnowledgeExtractionError) as captured:
            extraction_service(db, settings, ScriptedClient([{"candidates": [candidate()]}])).extract(
                seed.course_id, seed.material_id
            )
        assert captured.value.code == "KNOWLEDGE_EXTRACTION_FAILED"
        assert not list(db.scalars(select(KnowledgeCandidate)))
        run = db.scalar(select(KnowledgeExtractionRun))
        assert run.status == KnowledgeExtractionStatus.FAILED
        assert not run.is_current
