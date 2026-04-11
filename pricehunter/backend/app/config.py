from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    google_places_api_key: str = ""
    bland_ai_api_key: str = ""
    mongodb_url: str = "mongodb://localhost:27017"
    database_name: str = "pricehunter"
    bland_webhook_url: str = "http://localhost:8000/api/webhooks/voice"
    mock_voice_calls: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
