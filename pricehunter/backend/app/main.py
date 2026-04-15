from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import ping_database
from app.routers import chat, search, webhooks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = FastAPI(title="PriceHunter API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router)
app.include_router(chat.router)
app.include_router(webhooks.router)


@app.on_event("startup")
async def startup_event() -> None:
    await ping_database()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
