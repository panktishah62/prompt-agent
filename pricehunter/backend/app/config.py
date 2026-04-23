from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    serpapi_api_key: str = ""
    serpapi_base_url: str = "https://serpapi.com/search.json"
    google_places_api_key: str = ""
    bolna_api_key: str = ""
    bolna_agent_id: str = ""
    test_call_phone: str = ""
    frontend_origins: str = "http://localhost:5173"
    mongodb_url: str = "mongodb://localhost:27017"
    database_name: str = "pricehunter"
    bolna_webhook_url: str = "http://localhost:8000/api/webhooks/voice"
    mock_voice_calls: bool = True

    model_config = SettingsConfigDict(
        env_file=(WORKSPACE_ROOT / ".env", PROJECT_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
