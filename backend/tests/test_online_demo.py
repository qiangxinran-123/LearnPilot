from __future__ import annotations

import http.cookiejar
import json
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

import pytest
from pydantic import BaseModel

from backend.app.ai.client import OpenAICompatibleLLMClient
from backend.app.ai.errors import AIServiceError
from backend.app.core.online_demo import _new_session, _reserve_upload, reserve_model_call
from backend.app.core.settings import Settings


class Answer(BaseModel):
    answer: str


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"choices":[{"message":{"content":"{\\"answer\\":\\"ok\\"}"}}]}'


def settings_for(root: Path, **kwargs) -> Settings:
    values = {
        "_env_file": None,
        "online_demo_enabled": True,
        "online_demo_root": root,
        "online_demo_secret": "test-only-secret-never-used-in-production-01234567",
        "online_demo_secure_cookie": False,
        "llm_api_key": "test-canary-not-a-real-key",
        "llm_base_url": "https://example.test/v1",
        "llm_model": "test-model",
        "llm_max_attempts": 1,
    }
    values.update(kwargs)
    return Settings(**values)


def scoped(settings: Settings) -> Settings:
    _, session_id, _ = _new_session(settings)
    return settings.model_copy(update={"online_demo_session_id": session_id})


def test_model_budget_is_enforced_before_network(monkeypatch, tmp_path):
    base = settings_for(tmp_path, online_demo_session_call_limit=2, online_demo_global_call_limit=3)
    a, b = scoped(base), scoped(base)
    sent = []

    def send(*args, **kwargs):
        sent.append(1)
        return FakeResponse()

    monkeypatch.setattr("backend.app.ai.client.urlopen", send)
    client_a = OpenAICompatibleLLMClient(a)
    for _ in range(2):
        assert client_a.generate_structured(operation="test", messages=[], schema=Answer).data.answer == "ok"
    with pytest.raises(AIServiceError) as error:
        client_a.generate_structured(operation="test", messages=[], schema=Answer)
    assert error.value.code == "AI_RATE_LIMITED"
    client_b = OpenAICompatibleLLMClient(b)
    client_b.generate_structured(operation="test", messages=[], schema=Answer)
    with pytest.raises(AIServiceError) as error:
        client_b.generate_structured(operation="test", messages=[], schema=Answer)
    assert error.value.code == "AI_RATE_LIMITED"
    assert len(sent) == 3


def test_global_budget_is_atomic_across_concurrent_sessions(tmp_path):
    base = settings_for(tmp_path, online_demo_session_call_limit=20, online_demo_global_call_limit=3)
    users = [scoped(base) for _ in range(5)]

    def attempt(settings):
        try:
            reserve_model_call(settings)
            return True
        except AIServiceError:
            return False

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(attempt, users))
    assert sum(results) == 3


def test_online_requires_strong_secret_and_absolute_storage(tmp_path):
    with pytest.raises(RuntimeError):
        scoped(settings_for(tmp_path, online_demo_secret="short"))
    with pytest.raises(RuntimeError):
        scoped(settings_for(Path("relative")))


@pytest.fixture
def online_server(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(
        ONLINE_DEMO_ENABLED="true",
        ONLINE_DEMO_ROOT=str(tmp_path / "online"),
        ONLINE_DEMO_SECRET="test-only-secret-never-used-in-production-01234567",
        ONLINE_DEMO_SECURE_COOKIE="false",
        LLM_MODE="mock",
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            with urlopen(base + "/health", timeout=1):
                break
        except URLError, TimeoutError:
            if process.poll() is not None:
                raise RuntimeError("Online server stopped during startup")
            time.sleep(0.1)
    else:
        process.terminate()
        raise RuntimeError("Online server did not start")
    try:
        yield base
    finally:
        process.terminate()
        process.wait(timeout=10)


def request(client, base, method, path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = Request(base + path, data=body, headers={"Content-Type": "application/json"}, method=method)
    try:
        with client.open(req, timeout=20) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def test_judges_have_independent_courses_and_learning_state(online_server):
    a = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    b = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    for user in (a, b):
        status, result = request(user, online_server, "GET", "/api/courses")
        assert status == 200 and result["count"] == 1
    status, course = request(a, online_server, "POST", "/api/courses", {"name": "private test course"})
    assert status == 201
    assert request(b, online_server, "GET", f"/api/courses/{course['id']}")[0] == 404
    status, assessment = request(a, online_server, "POST", "/api/diagnostics/assessments", {"course_id": 1})
    assert status == 201
    assessment_id = assessment["id"]
    status, assessment = request(a, online_server, "POST", f"/api/diagnostics/assessments/{assessment_id}/start")
    assert status == 200
    for question in assessment["questions"]:
        status, _ = request(
            a,
            online_server,
            "PUT",
            f"/api/diagnostics/assessments/{assessment_id}/responses/{question['assessment_question_id']}",
            {"selected_options": [question["options"][0]["key"]]},
        )
        assert status == 200
    assert request(a, online_server, "POST", f"/api/diagnostics/assessments/{assessment_id}/submit")[0] == 200
    assert request(a, online_server, "POST", "/api/courses/1/learning-plan/generate")[0] == 200
    assert request(b, online_server, "GET", f"/api/diagnostics/assessments/{assessment_id}")[0] == 404
    status, readiness = request(b, online_server, "GET", "/api/diagnostics/courses/1/readiness")
    assert status == 200 and readiness["can_start"] is True
    forged = Request(online_server + "/api/courses", headers={"Cookie": "learnpilot_demo_session=forged"})
    with pytest.raises(HTTPError) as error:
        urlopen(forged, timeout=10)
    assert error.value.code == 403


def test_valid_cookie_recovers_after_ephemeral_restart_without_duplicate_sessions(tmp_path):
    before = settings_for(tmp_path / "before")
    token, session_id, _ = _new_session(before)
    after = settings_for(tmp_path / "after")

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda _: _new_session(after, token), range(5)))

    assert all(result[1] == session_id for result in results)
    assert len({result[2] for result in results}) == 1


def test_background_knowledge_build_stays_in_the_judge_session(online_server):
    a = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    b = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    assert request(a, online_server, "GET", "/api/courses")[0] == 200
    assert request(b, online_server, "GET", "/api/courses")[0] == 200
    status, course = request(a, online_server, "POST", "/api/courses", {"name": "private build"})
    assert status == 201
    course_id = course["id"]
    boundary = "LearnPilotTestBoundary"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="source.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "Cache improves access to data in a computer system.\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    upload = Request(
        f"{online_server}/api/courses/{course_id}/materials/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with a.open(upload, timeout=10) as response:
        assert response.status == 201
    status, _ = request(a, online_server, "POST", f"/api/courses/{course_id}/knowledge-model/build-jobs")
    assert status == 202
    for _ in range(100):
        status, result = request(a, online_server, "GET", f"/api/courses/{course_id}/knowledge-model/build-status")
        assert status == 200
        if result["state"] in {"ready", "failed"}:
            break
        time.sleep(0.1)
    assert result["state"] == "ready", result
    assert result["node_count"] > 0
    assert request(b, online_server, "GET", f"/api/courses/{course_id}")[0] == 404


def test_provider_calls_are_metered_in_real_online_request_path(tmp_path):
    calls: list[int] = []

    class Provider(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            calls.append(1)
            content = json.dumps(
                {
                    "answer": "Cache is discussed in the source.",
                    "sufficient_evidence": True,
                    "references": ["全文"],
                }
            )
            body = json.dumps({"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(
        ONLINE_DEMO_ENABLED="true",
        ONLINE_DEMO_ROOT=str(tmp_path / "provider-test"),
        ONLINE_DEMO_SECRET="test-only-secret-never-used-in-production-01234567",
        ONLINE_DEMO_SECURE_COOKIE="false",
        ONLINE_DEMO_SESSION_CALL_LIMIT="1",
        ONLINE_DEMO_GLOBAL_CALL_LIMIT="2",
        LLM_MODE="provider",
        LLM_BASE_URL=f"http://127.0.0.1:{provider.server_port}/v1",
        LLM_MODEL="fake-provider-model",
        LLM_API_KEY="fake-test-key",
        LLM_MAX_ATTEMPTS="1",
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                with urlopen(base + "/health", timeout=1):
                    break
            except URLError, TimeoutError:
                if process.poll() is not None:
                    raise RuntimeError("Provider test server stopped")
                time.sleep(0.1)
        else:
            raise RuntimeError("Provider test server did not start")
        a = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        b = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        c = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        for client in (a, b, c):
            assert request(client, base, "GET", "/api/courses")[0] == 200
        status, result = request(a, base, "POST", "/api/materials/1/qa", {"question": "Cache"})
        assert status == 200 and result["provider"] == "openai-compatible"
        assert request(a, base, "POST", "/api/materials/1/qa", {"question": "Cache"})[0] == 429
        assert request(b, base, "POST", "/api/materials/1/qa", {"question": "Cache"})[0] == 200
        assert request(c, base, "POST", "/api/materials/1/qa", {"question": "Cache"})[0] == 429
        assert len(calls) == 2
    finally:
        process.terminate()
        process.wait(timeout=10)
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=10)


def test_online_mode_fails_closed_without_required_durable_budget(tmp_path):
    config = settings_for(tmp_path, online_demo_require_durable_budget=True)
    with pytest.raises(RuntimeError, match="durable"):
        scoped(config)


def test_new_sessions_cannot_exceed_configured_capacity(tmp_path):
    config = settings_for(tmp_path, online_demo_max_sessions=1)
    scoped(config)
    with pytest.raises(RuntimeError, match="SESSION_LIMIT"):
        scoped(config)


def test_upload_budgets_are_atomic_and_per_session(tmp_path):
    base = settings_for(tmp_path, online_demo_session_upload_bytes=8, online_demo_global_upload_bytes=10)
    a, b = scoped(base), scoped(base)
    assert _reserve_upload(base, a.online_demo_session_id, 6)
    assert not _reserve_upload(base, a.online_demo_session_id, 3)
    assert _reserve_upload(base, b.online_demo_session_id, 4)
    assert not _reserve_upload(base, b.online_demo_session_id, 1)
