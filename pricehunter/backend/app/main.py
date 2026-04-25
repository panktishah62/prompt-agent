from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_database, ping_database
from app.routers import chat, location, search, webhooks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = FastAPI(title="PriceHunter API", version="1.0.0")

allowed_origins = [
    origin.strip()
    for origin in settings.frontend_origins.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router)
app.include_router(chat.router)
app.include_router(location.router)
app.include_router(webhooks.router)


@app.on_event("startup")
async def startup_event() -> None:
    logging.getLogger(__name__).info(
        "Startup config: OpenAI=%s GooglePlaces=%s SerpAPI=%s Bolna=%s Agent=%s MockVoice=%s",
        bool(settings.openai_api_key),
        bool(settings.google_places_api_key),
        bool(settings.serpapi_api_key),
        bool(settings.bolna_api_key),
        bool(settings.bolna_agent_id),
        settings.mock_voice_calls,
    )
    await ping_database()
    await init_database()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
