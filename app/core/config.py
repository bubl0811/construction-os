from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="CONSTRUCTION_OS_", extra="ignore"
    )

    app_name: str = "Construction OS"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    environment: Literal["local", "test", "staging", "production"] = "local"
    secret_key: str = Field(min_length=32)
    access_token_expire_minutes: int = Field(default=60, gt=0)
    jwt_algorithm: str = "HS256"
    database_url: str
    redis_url: str
    log_level: str = "INFO"
    document_storage_path: Path = Path("/var/lib/construction-os/documents")
    max_document_size_mb: int = Field(default=200, ge=1, le=2048)
    document_upload_token_expire_minutes: int = Field(default=10, ge=1, le=60)
    public_api_url: str = "https://185-143-145-25.sslip.io/api/v1"
    cors_allowed_origins: str = "https://construction-os-dashboard.hlpumg.chatgpt.site"


@lru_cache
def get_settings() -> Settings:
    return Settings()
