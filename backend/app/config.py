from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str
    hotel_timezone: str = "Europe/Warsaw"
    jwt_secret_key: SecretStr = Field(min_length=43)
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_days: int = Field(default=7, ge=1, le=30)

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix):]
        return value


settings = Settings()
HOTEL_ZONE = ZoneInfo(settings.hotel_timezone)
