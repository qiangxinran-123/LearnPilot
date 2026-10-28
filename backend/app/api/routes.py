from fastapi import APIRouter

from backend.app.api.courses import router as courses_router
from backend.app.api.diagnostics import router as diagnostics_router
from backend.app.api.knowledge import router as knowledge_router
from backend.app.api.learning_plans import router as learning_plans_router
from backend.app.api.learning_sessions import router as learning_sessions_router
from backend.app.api.mastery import router as mastery_router
from backend.app.api.materials import router as materials_router
from backend.app.core.config import APP_NAME, APP_VERSION

router = APIRouter()
router.include_router(courses_router)
router.include_router(materials_router)
router.include_router(knowledge_router)
router.include_router(diagnostics_router)
router.include_router(mastery_router)
router.include_router(learning_plans_router)
router.include_router(learning_sessions_router)


@router.get("/api")
def root():
    return {
        "message": "Welcome to CampusAI API",
        "app": APP_NAME,
        "version": APP_VERSION,
    }


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": APP_NAME,
    }


@router.get("/api/project/status")
def project_status():
    return {
        "project": APP_NAME,
        "version": APP_VERSION,
        "stage": "backend-basic-structure",
        "progress": "18%",
        "features": [
            "FastAPI backend",
            "basic routing",
            "health check",
            "project status API",
        ],
    }
