from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "TheResearcher"
    app_env: str = "pre-prod"
    host: str = "0.0.0.0"
    port: int = 50080
    data_dir: Path = Path("/app/data")
    # All uploads/exports/archives live under storage/, not scattered on the host.
    storage_dir: Path = Path("/app/storage")
    database_url: str = ""
    secret_key: str = "change-me-in-production-use-long-random-string"
    token_fernet_key: str = ""
    access_token_expire_minutes: int = 60 * 12
    default_admin_username: str = "researcher"
    default_admin_password: str = "password"
    cors_origins: str = "*"

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = self.data_dir / "theresearcher.db"
        return f"sqlite:///{db_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
