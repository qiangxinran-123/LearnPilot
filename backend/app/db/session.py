from __future__ import annotations

import logging
from collections.abc import Generator
from threading import RLock

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.settings import get_settings

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_online_engines: dict[str, Engine] = {}
_online_factories: dict[str, sessionmaker[Session]] = {}
_online_lock = RLock()


def reset_database_state() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    with _online_lock:
        for engine in _online_engines.values():
            engine.dispose()
        _online_engines.clear()
        _online_factories.clear()


def get_engine() -> Engine:
    global _engine
    settings = get_settings()
    if settings.online_demo_enabled:
        if not settings.online_demo_session_id:
            raise RuntimeError("Online demo database access requires a valid session.")
        key = settings.require_database_url()
        with _online_lock:
            if key not in _online_engines:
                engine = create_engine(key, future=True, pool_pre_ping=True, connect_args={"check_same_thread": False})

                @event.listens_for(engine, "connect")
                def _online_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
                    cursor = dbapi_connection.cursor()
                    cursor.execute("PRAGMA foreign_keys=ON")
                    cursor.close()

                _online_engines[key] = engine
            return _online_engines[key]
    if _engine is None:
        settings = get_settings()
        database_url = settings.require_database_url()
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        _engine = create_engine(
            database_url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        if database_url.startswith("sqlite"):

            @event.listens_for(_engine, "connect")
            def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    settings = get_settings()
    if settings.online_demo_enabled:
        if not settings.online_demo_session_id:
            raise RuntimeError("Online demo database access requires a valid session.")
        key = settings.require_database_url()
        with _online_lock:
            if key not in _online_factories:
                _online_factories[key] = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
            return _online_factories[key]
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    except SQLAlchemyError:
        logger.exception("Database request transaction failed")
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
