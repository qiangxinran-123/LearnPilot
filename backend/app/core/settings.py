from __future__ import annotations

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

    llm_mode: str = "provider"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    llm_timeout_seconds: int = Field(default=45, ge=5, le=120)
    llm_max_attempts: int = Field(default=2, ge=1, le=3)
    llm_context_chars: int = Field(default=12000, ge=2000, le=30000)
    llm_chunk_chars: int = Field(default=800, ge=400, le=2000)
    llm_chunk_overlap_chars: int = Field(default=120, ge=0, le=500)
    llm_summary_max_chunks: int = Field(default=8, ge=2, le=16)
    llm_summary_max_input_chars: int = Field(default=200_000, ge=12_000, le=1_000_000)
    knowledge_extraction_max_input_chars: int = Field(default=200_000, ge=12_000, le=1_000_000)
    knowledge_extraction_max_candidates: int = Field(default=100, ge=20, le=500)
    knowledge_canonicalization_max_candidates: int = Field(default=200, ge=2, le=1000)
    knowledge_canonicalization_block_size: int = Field(default=12, ge=2, le=20)
    knowledge_relationship_max_nodes: int = Field(default=120, ge=1, le=500)
    knowledge_relationship_block_size: int = Field(default=12, ge=2, le=20)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def require_database_url(self) -> str:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required. Copy .env.example and configure a safe local database URL.")
        return self.database_url

    @property
    def normalized_upload_root(self) -> Path:
        return self.upload_root.resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
