"""Pydantic Settings — 12-factor 환경변수 기반 설정.

P0 §0: 최소 항목만. JWT/OAuth/GitHub/Slack는 §2~P2 단계에서 활성화.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_env: str = Field(default="dev")
    app_debug: bool = Field(default=True)
    app_tz: str = Field(default="Asia/Seoul")

    # --- Backend ---
    backend_host: str = Field(default="0.0.0.0")
    backend_port: int = Field(default=9100)
    backend_cors_origins: str = Field(default="http://localhost:4100")

    # --- Database ---
    database_url: str = Field(default="postgresql+asyncpg://opsconsole_svc:CHANGE_ME@localhost:5432/opsconsole_dev")
    database_pool_size: int = Field(default=5)
    database_max_overflow: int = Field(default=10)

    # --- JWT (활성화는 §2 auth) ---
    jwt_secret_key: str = Field(default="CHANGE_ME")
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=720)

    # --- Google OAuth (§2 auth) ---
    google_oauth_client_id: str = Field(default="")
    google_oauth_client_secret: str = Field(default="")
    google_oauth_redirect_uri: str = Field(default="http://localhost:4100/auth/callback")

    # --- GitHub (§2 sync / P2 bridge) ---
    github_pat: str = Field(default="")
    github_api_base: str = Field(default="https://api.github.com")

    # --- Slack (P1) ---
    slack_webhook_url: str = Field(default="")

    # --- Manifest sync ---
    manifest_default_ref: str = Field(default="main")
    manifest_local_fallback_path: str = Field(default="")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
