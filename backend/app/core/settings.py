from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = ""
    upload_root: Path = Path("backend/app/uploads")
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    log_level: str = "INFO"
    legacy_bootstrap_user: str = "legacy-bootstrap@learnpilot.local"
    legacy_bootstrap_user_display_name: str = "Legacy CampusAI"

    online_demo_enabled: bool = False
    online_demo_root: Path | None = None
    online_demo_secret: str = ""
    online_demo_control_database_url: str = ""
    online_demo_require_durable_budget: bool = False
    online_demo_secure_cookie: bool = True
    online_demo_max_sessions: int = Field(default=30, ge=1, le=500)
    online_demo_session_call_limit: int = Field(default=30, ge=1, le=10000)
    online_demo_global_call_limit: int = Field(default=300, ge=1, le=100000)
    online_demo_model_calls_per_minute: int = Field(default=20, ge=1, le=1000)
    online_demo_requests_per_minute: int = Field(default=180, ge=1, le=10000)
    online_demo_session_upload_bytes: int = Field(default=50 * 1024 * 1024, ge=1)
    online_demo_global_upload_bytes: int = Field(default=250 * 1024 * 1024, ge=1)
    online_demo_session_id: str = ""

    llm_mode: str = "provider"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    llm_timeout_seconds: int = Field(default=45, ge=5, le=120)
    llm_max_attempts: int = Field(default=2, ge=1, le=3)
    llm_max_output_tokens: int | None = Field(default=None, ge=1, le=8192)
    llm_context_chars: int = Field(default=12000, ge=2000, le=30000)
    llm_chunk_chars: int = Field(default=800, ge=400, le=2000)
    llm_chunk_overlap_chars: int = Field(default=120, ge=0, le=500)
    llm_summary_max_chunks: int = Field(default=8, ge=2, le=16)
    llm_summary_max_input_chars: int = Field(default=200_000, ge=12_000, le=1_000_000)
    knowledge_extraction_max_input_chars: int = Field(default=200_000, ge=12_000, le=1_000_000)
    knowledge_extraction_max_output_tokens: int = Field(default=4096, ge=1, le=8192)
    knowledge_extraction_max_candidates: int = Field(default=100, ge=20, le=500)
    knowledge_canonicalization_max_candidates: int = Field(default=200, ge=2, le=1000)
    knowledge_canonicalization_max_raw_candidates: int = Field(default=1000, ge=1, le=10000)
    knowledge_canonicalization_block_size: int = Field(default=12, ge=2, le=20)
    knowledge_relationship_max_nodes: int = Field(default=120, ge=1, le=500)
    knowledge_relationship_block_size: int = Field(default=12, ge=2, le=20)
    diagnostic_question_max_count: int = Field(default=4, ge=1, le=8)
    diagnostic_question_similarity_threshold: float = Field(default=0.9, ge=0.75, le=1.0)
    diagnostic_replenish_max_calls: int = Field(default=8, ge=1, le=8)
    practice_basic_target: int = Field(default=3, ge=2, le=5)
    practice_intermediate_target: int = Field(default=4, ge=3, le=5)
    practice_advanced_target: int = Field(default=5, ge=4, le=5)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def require_database_url(self) -> str:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required. Copy .env.example and configure a safe local database URL.")
        return self.database_url

    @property
    def normalized_upload_root(self) -> Path:
        return self.upload_root.resolve()


_request_settings: ContextVar[Settings | None] = ContextVar("online_demo_settings", default=None)


@lru_cache
def get_base_settings() -> Settings:
    return Settings()


def get_settings() -> Settings:
    return _request_settings.get() or get_base_settings()


@contextmanager
def request_settings(settings: Settings) -> Iterator[None]:
    token = _request_settings.set(settings)
    try:
        yield
    finally:
        _request_settings.reset(token)
