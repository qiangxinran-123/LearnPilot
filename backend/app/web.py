from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.types import Scope

logger = logging.getLogger(__name__)

_RESERVED_PATHS = ("api", "health", "docs", "redoc", "openapi.json")
_SPA_METHODS = {"GET", "HEAD"}


def _is_reserved_path(path: str) -> bool:
    normalized_path = path.strip("/")
    return any(
        normalized_path == reserved or normalized_path.startswith(f"{reserved}/") for reserved in _RESERVED_PATHS
    )


def _should_fallback_to_spa(path: str, scope: Scope) -> bool:
    return scope["method"] in _SPA_METHODS and not _is_reserved_path(path)


class SPAStaticFiles(StaticFiles):
    """Serve build assets and fall back to the SPA only for public page routes."""

    async def get_response(self, path: str, scope: Scope):
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or not _should_fallback_to_spa(path, scope):
                raise
            return await super().get_response("index.html", scope)

        if response.status_code == 404 and _should_fallback_to_spa(path, scope):
            return await super().get_response("index.html", scope)
        return response


def mount_spa_static_files(app: FastAPI, directory: Path) -> bool:
    """Mount a built SPA when available without shadowing API-style paths."""

    if not directory.is_dir():
        logger.warning("Frontend build directory is unavailable: %s", directory)
        return False

    app.mount("/", SPAStaticFiles(directory=directory, html=True), name="frontend")
    return True
