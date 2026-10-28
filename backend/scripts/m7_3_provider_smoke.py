from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.settings import Settings
from backend.app.db.models import Course, KnowledgeNode, KnowledgeSource, Material, MaterialContent, User
from backend.app.models import KnowledgeDifficulty, KnowledgeImportance, TeachingStrategy
from backend.app.schemas.learning_session import LearningSessionCreate
from backend.app.schemas.tutor import TutorMessageCreate
from backend.app.services.learning_session_service import LearningSessionService
from backend.app.services.tutor_service import TutorService


def main() -> None:
    provider_settings = Settings()
    if not all(
        (
            provider_settings.llm_mode == "provider",
            provider_settings.llm_api_key,
            provider_settings.llm_base_url,
            provider_settings.llm_model,
        )
    ):
        raise RuntimeError("Real provider is not configured.")

    with TemporaryDirectory(prefix="learnpilot-m7-3-") as temporary:
        database_url = f"sqlite+pysqlite:///{Path(temporary) / 'smoke.sqlite3'}"
        environment = os.environ.copy()
        environment["DATABASE_URL"] = database_url
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=environment, check=True)
        settings = provider_settings.model_copy(update={"database_url": database_url, "llm_max_attempts": 1})
        engine = create_engine(database_url)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory() as session, session.begin():
            owner = User(
                email=settings.legacy_bootstrap_user,
                display_name="Provider Smoke",
                is_active=True,
            )
            session.add(owner)
            session.flush()
            systems = Course(owner_id=owner.id, name="Computer Systems", description="")
            networks = Course(owner_id=owner.id, name="Computer Networks", description="")
            session.add_all([systems, networks])
            session.flush()
            lru = _node(systems.id, "LRU Replacement", "Use recency to choose a cache block.")
            unsupported = _node(systems.id, "Quantum Entanglement", "")
            link_recovery = _node(networks.id, "Link Recovery Unit", "Recover a failed network link.")
            session.add_all([lru, unsupported, link_recovery])
            session.flush()
            cache = _material(systems.id, "Cache Lecture", "pdf")
            network = _material(networks.id, "Network Recovery Notes", "txt")
            session.add_all([cache, network])
            session.flush()
            session.add_all(
                [
                    _content(
                        cache.id,
                        "Block 2 was accessed at time 1, while Block 1 was accessed at time 5. "
                        "LRU replaces the least recently used block, so Block 2 is selected.",
                        "PDF 第 2 页",
                        "a",
                    ),
                    _content(
                        network.id,
                        "The Link Recovery Unit switches traffic to a backup link after a failure.",
                        "TXT segment 1",
                        "b",
                    ),
                    KnowledgeSource(
                        knowledge_node_id=lru.id,
                        material_id=cache.id,
                        source_reference="PDF 第 2 页",
                    ),
                    KnowledgeSource(
                        knowledge_node_id=link_recovery.id,
                        material_id=network.id,
                        source_reference="TXT segment 1",
                    ),
                ]
            )
            ids = {
                "systems": systems.id,
                "networks": networks.id,
                "lru": lru.id,
                "unsupported": unsupported.id,
                "link": link_recovery.id,
                "cache": cache.id,
                "network": network.id,
            }

        systems_session = _create_session(factory, settings, ids["systems"], ids["lru"])
        unsupported_session = _create_session(factory, settings, ids["systems"], ids["unsupported"])
        network_session = _create_session(factory, settings, ids["networks"], ids["link"])
        hint = _ask(
            factory,
            settings,
            systems_session,
            "为什么需要替换这个缓存块？",
            TeachingStrategy.HINT,
            "real-hint",
        )
        full = _ask(
            factory,
            settings,
            systems_session,
            "请完整解释为什么替换 Block 2。",
            TeachingStrategy.FULL_EXPLANATION,
            "real-full",
        )
        missing = _ask(
            factory,
            settings,
            unsupported_session,
            "课程资料如何解释贝尔不等式？",
            TeachingStrategy.GUIDED_QUESTION,
            "real-missing",
        )
        isolated = _ask(
            factory,
            settings,
            network_session,
            "发生故障时为什么需要替换当前链路？",
            TeachingStrategy.HINT,
            "real-isolation",
        )

        assert hint.mode == TeachingStrategy.HINT and hint.content.strip()
        assert full.mode == TeachingStrategy.FULL_EXPLANATION and full.content.strip()
        assert any(item.material_id == ids["cache"] for item in full.citations)
        assert missing.insufficient_evidence and not missing.citations
        assert isolated.citations and all(item.material_id == ids["network"] for item in isolated.citations)
        print("M7-3 real provider smoke: PASS (hint, full, insufficient, isolation)")
        engine.dispose()


def _node(course_id: int, name: str, description: str) -> KnowledgeNode:
    return KnowledgeNode(
        course_id=course_id,
        name=name,
        normalized_name=name.casefold(),
        description=description,
        importance=KnowledgeImportance.HIGH,
        difficulty=KnowledgeDifficulty.INTERMEDIATE,
        is_active=True,
    )


def _material(course_id: int, title: str, extension: str) -> Material:
    return Material(
        course_id=course_id,
        title=title,
        material_type="document",
        extension=extension,
        extraction_status="SUCCESS",
        text_extracted=True,
    )


def _content(material_id: int, text: str, reference: str, hash_char: str) -> MaterialContent:
    return MaterialContent(
        material_id=material_id,
        plain_text=text,
        segments=[{"text": text, "source_reference": reference}],
        content_hash=hash_char * 64,
        parser_name="smoke",
        parser_version="1",
        page_count=1 if reference.startswith("PDF") else 0,
    )


def _create_session(factory, settings: Settings, course_id: int, node_id: int) -> int:
    with factory() as session:
        result = LearningSessionService(session, settings).create_for_configured_user(
            LearningSessionCreate(course_id=course_id, target_knowledge_node_id=node_id)
        )
        return result.session_id


def _ask(factory, settings: Settings, session_id: int, text: str, mode: TeachingStrategy, key: str):
    with factory() as session:
        result = TutorService(session, settings).send_message_for_configured_user(
            session_id=session_id,
            payload=TutorMessageCreate(message=text, mode=mode),
            idempotency_key=key,
        )
        return result.tutor_message


if __name__ == "__main__":
    main()
