from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

logger = logging.getLogger(__name__)

client = AsyncIOMotorClient(
    settings.mongodb_url,
    serverSelectionTimeoutMS=2000,
    connectTimeoutMS=2000,
    socketTimeoutMS=2000,
)
db = client[settings.database_name]

queries_collection = db["queries"]
results_collection = db["results"]
vendors_collection = db["vendors"]


async def ping_database() -> bool:
    try:
        await client.admin.command("ping")
        return True
    except Exception as exc:  # pragma: no cover - depends on external service
        logger.warning("MongoDB ping failed: %s", exc)
        return False
