from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from starlette.concurrency import run_in_threadpool

from backend.app.ai.errors import AIServiceError
from backend.app.core.settings import Settings, get_base_settings, request_settings
from scripts.init_demo import FIXTURE, validate

COOKIE_NAME = "learnpilot_demo_session"


def _root(settings: Settings) -> Path:
    if settings.online_demo_root is None or not settings.online_demo_root.is_absolute():
        raise RuntimeError("ONLINE_DEMO_ROOT must be an absolute persistent directory.")
    if len(settings.online_demo_secret.encode("utf-8")) < 32:
        raise RuntimeError("ONLINE_DEMO_SECRET must contain at least 32 bytes.")
    root = settings.online_demo_root.resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    (root / "sessions").mkdir(exist_ok=True, mode=0o700)
    return root


def validate_online_configuration(settings: Settings) -> None:
    _root(settings)
    validate(FIXTURE)
    with _connect(settings):
        pass


def _control_url(settings: Settings) -> str:
    configured = settings.online_demo_control_database_url
    if configured:
        if configured.startswith("postgres://"):
            configured = "postgresql+psycopg://" + configured[len("postgres://") :]
        elif configured.startswith("postgresql://"):
            configured = "postgresql+psycopg://" + configured[len("postgresql://") :]
        if not configured.startswith("postgresql+psycopg://"):
            raise RuntimeError("Online demo control database must use PostgreSQL.")
        return configured
    if settings.online_demo_require_durable_budget:
        raise RuntimeError("Online demo requires a durable control database.")
    return f"sqlite+pysqlite:///{(_root(settings) / 'control.sqlite3').as_posix()}"


@lru_cache(maxsize=4)
def _control_engine(url: str) -> Engine:
    options = {"check_same_thread": False, "timeout": 20} if url.startswith("sqlite") else {}
    return create_engine(url, pool_pre_ping=True, connect_args=options)


class _ControlConnection:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def execute(self, statement: str, values: tuple[object, ...] = ()):
        parts = statement.split("?")
        if len(parts) != len(values) + 1:
            raise ValueError("Invalid control database parameters.")
        query = parts[0]
        for index, part in enumerate(parts[1:]):
            query += f":p{index}" + part
        return self.connection.execute(text(query), {f"p{i}": value for i, value in enumerate(values)})

    def commit(self) -> None:
        self.connection.commit()


@contextmanager
def _connect(settings: Settings) -> Iterator[_ControlConnection]:
    url = _control_url(settings)
    engine = _control_engine(url)
    with engine.connect() as connection:
        try:
            if engine.dialect.name == "sqlite":
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                connection.exec_driver_sql("SELECT pg_advisory_xact_lock(7265910421)")
            db = _ControlConnection(connection)
            db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, created_at BIGINT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS api_requests (session_id TEXT NOT NULL, created_at BIGINT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS model_calls (session_id TEXT NOT NULL, created_at BIGINT NOT NULL)")
            db.execute(
                "CREATE TABLE IF NOT EXISTS upload_reservations (session_id TEXT NOT NULL, bytes BIGINT NOT NULL)"
            )
            yield db
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def _sign(nonce: str, secret: str) -> str:
    return hmac.new(secret.encode(), nonce.encode(), hashlib.sha256).hexdigest()


def _make_token(secret: str) -> str:
    nonce = base64.urlsafe_b64encode(secrets.token_bytes(24)).decode().rstrip("=")
    return nonce + "." + _sign(nonce, secret)


def _session_id(token: str, secret: str) -> str | None:
    parts = token.split(".")
    if len(parts) != 2:
        return None
    nonce, signature = parts
    if len(nonce) != 32 or len(signature) != 64 or any(c not in "0123456789abcdef" for c in signature):
        return None
    if not all(c.isascii() and (c.isalnum() or c in "-_") for c in nonce):
        return None
    if not hmac.compare_digest(_sign(nonce, secret), signature):
        return None
    return hashlib.sha256(nonce.encode()).hexdigest()


def _new_session(settings: Settings, existing_token: str | None = None) -> tuple[str, str, Path]:
    root = _root(settings)
    token = existing_token or _make_token(settings.online_demo_secret)
    session_id = _session_id(token, settings.online_demo_secret)
    assert session_id is not None
    destination = root / "sessions" / session_id
    with _connect(settings) as db:
        registered = db.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if registered is not None and (destination / "demo.sqlite3").is_file():
            return token, session_id, destination
        if registered is None:
            count = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            if count >= settings.online_demo_max_sessions:
                raise RuntimeError("DEMO_SESSION_LIMIT")
        if destination.exists():
            raise RuntimeError("DEMO_SESSION_UNAVAILABLE")
        validate(FIXTURE)
        staging = Path(tempfile.mkdtemp(prefix=".new-", dir=root / "sessions"))
        try:
            shutil.copy2(FIXTURE / "demo.sqlite3", staging / "demo.sqlite3")
            shutil.copytree(FIXTURE / "uploads", staging / "uploads")
            shutil.copy2(FIXTURE / "manifest.json", staging / "manifest.json")
            validate(staging)
            staging.rename(destination)
            if registered is None:
                db.execute("INSERT INTO sessions VALUES (?, ?)", (session_id, int(time.time())))
            db.commit()
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
    return token, session_id, destination


def _existing_session(settings: Settings, token: str) -> tuple[str, Path] | None:
    session_id = _session_id(token, settings.online_demo_secret)
    if session_id is None:
        return None
    destination = _root(settings) / "sessions" / session_id
    with _connect(settings) as db:
        found = db.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if found is None or not (destination / "demo.sqlite3").is_file():
        return None
    return session_id, destination


def _record_request(settings: Settings, session_id: str) -> bool:
    now = int(time.time())
    with _connect(settings) as db:
        db.execute("DELETE FROM api_requests WHERE created_at < ?", (now - 60,))
        count = db.execute("SELECT COUNT(*) FROM api_requests WHERE session_id = ?", (session_id,)).fetchone()[0]
        if count >= settings.online_demo_requests_per_minute:
            return False
        db.execute("INSERT INTO api_requests VALUES (?, ?)", (session_id, now))
        db.commit()
    return True


def _reserve_upload(settings: Settings, session_id: str, length: int) -> bool:
    with _connect(settings) as db:
        own = db.execute(
            "SELECT COALESCE(SUM(bytes), 0) FROM upload_reservations WHERE session_id = ?", (session_id,)
        ).fetchone()[0]
        total = db.execute("SELECT COALESCE(SUM(bytes), 0) FROM upload_reservations").fetchone()[0]
        if own + length > settings.online_demo_session_upload_bytes:
            return False
        if total + length > settings.online_demo_global_upload_bytes:
            return False
        db.execute("INSERT INTO upload_reservations VALUES (?, ?)", (session_id, length))
        db.commit()
    return True


def reserve_model_call(settings: Settings) -> None:
    session_id = settings.online_demo_session_id
    if len(session_id) != 64:
        raise AIServiceError("AI_RATE_LIMITED", "Online demo identity is unavailable.")
    now = int(time.time())
    with _connect(settings) as db:
        registered = db.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
        total = db.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0]
        own = db.execute("SELECT COUNT(*) FROM model_calls WHERE session_id = ?", (session_id,)).fetchone()[0]
        recent = db.execute(
            "SELECT COUNT(*) FROM model_calls WHERE session_id = ? AND created_at >= ?", (session_id, now - 60)
        ).fetchone()[0]
        if (
            not registered
            or total >= settings.online_demo_global_call_limit
            or own >= settings.online_demo_session_call_limit
        ):
            raise AIServiceError("AI_RATE_LIMITED", "Online demo AI request budget has been reached.")
        if recent >= settings.online_demo_model_calls_per_minute:
            raise AIServiceError("AI_RATE_LIMITED", "Online demo AI request rate limit has been reached.")
        db.execute("INSERT INTO model_calls VALUES (?, ?)", (session_id, now))
        db.commit()


async def online_demo_middleware(request: Request, call_next):
    base = get_base_settings()
    if not base.online_demo_enabled:
        return await call_next(request)
    path = request.url.path
    if path == "/health" or path.startswith("/assets/") or path in {"/favicon.ico", "/robots.txt"}:
        return await call_next(request)
    is_api = path == "/api" or path.startswith("/api/")
    if is_api and request.method in {"POST", "PUT", "PATCH"}:
        length = request.headers.get("content-length")
        if length is not None:
            try:
                if int(length) < 0 or int(length) > base.max_upload_bytes + 1024 * 1024:
                    return JSONResponse(
                        {"error": {"code": "REQUEST_TOO_LARGE", "message": "Request exceeds the demo size limit."}},
                        status_code=413,
                    )
            except ValueError:
                return JSONResponse({"error": {"code": "INVALID_LENGTH", "message": "Invalid request length."}}, 400)
    accepts_html = "text/html" in request.headers.get("accept", "")
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie and not is_api and not accepts_html:
        return await call_next(request)
    existing = None
    if cookie:
        if _session_id(cookie, base.online_demo_secret) is None:
            return JSONResponse(
                {"error": {"code": "INVALID_SESSION", "message": "Invalid demo session."}}, status_code=403
            )
        existing = await run_in_threadpool(_existing_session, base, cookie)
    if existing is not None:
        session_id, destination = existing
        new_token = None
    else:
        try:
            new_token, session_id, destination = await run_in_threadpool(_new_session, base, cookie)
        except RuntimeError as error:
            if str(error) == "DEMO_SESSION_LIMIT":
                return JSONResponse(
                    {"error": {"code": "DEMO_SESSION_LIMIT", "message": "Demo capacity reached."}}, status_code=503
                )
            raise
    if path == "/api/online-demo/reset" and request.method == "POST":
        response = JSONResponse({"reset": True})
        response.delete_cookie(
            COOKIE_NAME, path="/", secure=base.online_demo_secure_cookie, httponly=True, samesite="lax"
        )
        return response
    if is_api and not await run_in_threadpool(_record_request, base, session_id):
        return JSONResponse({"error": {"code": "DEMO_RATE_LIMITED", "message": "Too many requests."}}, status_code=429)
    if request.method == "POST" and re.fullmatch(r"/api/courses/[0-9]+/materials/upload", path):
        length = request.headers.get("content-length")
        if length is None:
            return JSONResponse(
                {"error": {"code": "LENGTH_REQUIRED", "message": "Upload length is required."}}, status_code=411
            )
        if not await run_in_threadpool(_reserve_upload, base, session_id, int(length)):
            return JSONResponse(
                {"error": {"code": "DEMO_UPLOAD_LIMIT", "message": "Demo upload budget has been reached."}},
                status_code=429,
            )
    scoped = base.model_copy(
        update={
            "database_url": f"sqlite+pysqlite:///{(destination / 'demo.sqlite3').as_posix()}",
            "upload_root": destination / "uploads",
            "online_demo_session_id": session_id,
        }
    )
    with request_settings(scoped):
        response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    if new_token is not None:
        response.set_cookie(
            COOKIE_NAME,
            new_token,
            httponly=True,
            secure=base.online_demo_secure_cookie,
            samesite="lax",
            max_age=7 * 24 * 3600,
            path="/",
        )
    return response
