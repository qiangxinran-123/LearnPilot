from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text

from backend.app.api.routes import router
from backend.app.core.config import APP_DESCRIPTION, APP_NAME, APP_VERSION
from backend.app.core.errors import install_exception_handlers
from backend.app.core.logging import configure_logging
from backend.app.core.settings import get_settings
from backend.app.db.session import get_engine, reset_database_state
from backend.app.web import mount_spa_static_files

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    logger.info("Application startup environment=%s", settings.app_env)
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database connection validation failed")
        reset_database_state()
        raise
    yield
    reset_database_state()
    logger.info("Application shutdown complete")


app = FastAPI(
    title=f"{APP_NAME} API",
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    lifespan=lifespan,
)
install_exception_handlers(app)
app.include_router(router)

FRONTEND_DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
mount_spa_static_files(app, FRONTEND_DIST_DIR)
