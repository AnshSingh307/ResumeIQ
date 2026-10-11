from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


load_dotenv()


def _as_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class AppConfig(BaseModel):
    app_name: str = "ResumeIQ"
    environment: str = Field(default_factory=lambda: os.getenv("RESUMEIQ_ENVIRONMENT", "development").lower())
    demo_mode: bool = Field(default_factory=lambda: _as_bool("RESUMEIQ_DEMO_MODE"))
    auth_required: bool = Field(default_factory=lambda: _as_bool("RESUMEIQ_AUTH_REQUIRED"))
    allowed_tenant_id: str = Field(default_factory=lambda: os.getenv("RESUMEIQ_ALLOWED_TENANT_ID", ""))
    data_dir: Path = Field(default_factory=lambda: Path(os.getenv("RESUMEIQ_DATA_DIR", "./data")))
    demo_data_dir: Path = Field(default_factory=lambda: Path(os.getenv("RESUMEIQ_DEMO_DATA_DIR", "./data/demo")))
    max_file_mb: int = Field(default_factory=lambda: int(os.getenv("RESUMEIQ_MAX_FILE_MB", "10")))
    retention_days: int = Field(default_factory=lambda: int(os.getenv("RESUMEIQ_RETENTION_DAYS", "30")))
    anonymous_default: bool = Field(default_factory=lambda: _as_bool("RESUMEIQ_ANONYMOUS_DEFAULT"))
    semantic_provider: str = Field(default_factory=lambda: os.getenv("RESUMEIQ_SEMANTIC_PROVIDER", "tfidf"))
    sentence_model: str = Field(default_factory=lambda: os.getenv("RESUMEIQ_SENTENCE_MODEL", "all-MiniLM-L6-v2"))
    use_azure_document_intelligence: bool = Field(
        default_factory=lambda: _as_bool("RESUMEIQ_USE_AZURE_DOCUMENT_INTELLIGENCE")
    )
    use_azure_language: bool = Field(default_factory=lambda: _as_bool("RESUMEIQ_USE_AZURE_LANGUAGE"))
    use_azure_blob: bool = Field(default_factory=lambda: _as_bool("RESUMEIQ_USE_AZURE_BLOB"))

    @property
    def active_data_dir(self) -> Path:
        return self.demo_data_dir if self.demo_mode else self.data_dir

    @property
    def database_path(self) -> Path:
        return self.active_data_dir / "resumeiq.sqlite3"

    @property
    def upload_dir(self) -> Path:
        return self.active_data_dir / "uploads"

    def anonymous_review_enabled(self, saved_preference: bool | None = None) -> bool:
        """Demo mode is always anonymous; private workspaces may use the saved preference."""
        if self.demo_mode:
            return True
        return self.anonymous_default if saved_preference is None else saved_preference

    def ensure_directories(self) -> None:
        self.active_data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def deployment_errors(self) -> list[str]:
        errors: list[str] = []
        if self.is_production and not self.demo_mode and not self.auth_required:
            errors.append("Production candidate data requires RESUMEIQ_AUTH_REQUIRED=true and Azure App Service Authentication.")
        if self.is_production and not self.demo_mode and not str(self.active_data_dir).replace("\\", "/").startswith("/home/"):
            errors.append("Production SQLite must be stored under App Service persistent /home storage.")
        if self.is_production and not self.demo_mode and not self.use_azure_blob:
            errors.append("Production candidate documents require RESUMEIQ_USE_AZURE_BLOB=true with a private container.")
        return errors


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    config = AppConfig()
    config.ensure_directories()
    return config

