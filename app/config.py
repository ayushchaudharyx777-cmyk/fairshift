from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PORT: int = 8080
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_TTS_MODEL: str = "gemini-2.5-flash-preview-tts"
    GEMINI_TTS_VOICE: str = "Kore"
    ADMIN_PIN: str = "4821"
    SESSION_SECRET: str = "fairshift-secret-key-keep-it-safe-2026"
    ALLOWED_ORIGINS: str = "*"
    RESET_DB_ON_START: bool = False  # true => wipe saved data and re-seed fresh demo data on next start
    DATABASE_URL: str = ""  # empty => in-memory only; e.g. postgresql://... or sqlite:///fairshift.db

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
