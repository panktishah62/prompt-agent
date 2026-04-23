from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.database import results_collection
from app.services.voice_agent import store_execution_webhook

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/webhooks/voice")
async def voice_webhook(request: Request) -> dict[str, str]:
    """Receives call completion callbacks from Bolna."""

    body = await request.json()
    execution_id = store_execution_webhook(body)
    logger.info("Received Bolna webhook payload for execution=%s.", execution_id or "unknown")
    try:
        await results_collection.insert_one({"type": "voice_webhook", "payload": body})
    except Exception as exc:  # pragma: no cover - depends on external service
        logger.warning("Failed to persist webhook payload: %s", exc)
    return {"status": "received"}
