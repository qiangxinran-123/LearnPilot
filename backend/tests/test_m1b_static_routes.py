from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.types import Scope

from backend.app.web import SPAStaticFiles, mount_spa_static_files


def _http_scope(path: str, method: str = "GET") -> Scope:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": f"/{path}",
        "raw_path": f"/{path}".encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }


def test_spa_static_routes_fallback_only_for_public_page_routes(tmp_path) -> None:
    dist_dir = tmp_path / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<div id='app'>LearnPilot</div>", encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('learnpilot');", encoding="utf-8")
    static_files = SPAStaticFiles(directory=dist_dir, html=True)

    dashboard = asyncio.run(static_files.get_response("dashboard", _http_scope("dashboard")))
    asset = asyncio.run(static_files.get_response("assets/app.js", _http_scope("assets/app.js")))

    assert dashboard.status_code == 200
    assert asset.status_code == 200
    with pytest.raises(HTTPException, match="404"):
        asyncio.run(static_files.get_response("api/not-real", _http_scope("api/not-real")))
    with pytest.raises(HTTPException, match="404"):
        asyncio.run(static_files.get_response("health/debug", _http_scope("health/debug")))


def test_spa_static_mount_is_appended_after_existing_api_routes(tmp_path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<div id='app'>LearnPilot</div>", encoding="utf-8")
    app = FastAPI()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "campusai-backend"}

    @app.get("/api/courses")
    def courses() -> dict[str, object]:
        return {"count": 0, "courses": []}

    assert mount_spa_static_files(app, dist_dir)
    assert app.routes[-1].path == ""
    assert app.routes[-1].name == "frontend"
