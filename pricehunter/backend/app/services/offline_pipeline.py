from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.models.schemas import StructuredQuery, UnifiedResult, VoiceCallResult
from app.services.vendor_discovery import discover_vendors
from app.services.voice_agent import call_all_vendors, poll_call_result
from app.services.voice_extractor import extract_from_transcript

logger = logging.getLogger(__name__)


async def _resolve_call(call: VoiceCallResult) -> VoiceCallResult:
    return await poll_call_result(call)


async def run(query: StructuredQuery) -> list[UnifiedResult]:
    logger.info("Starting offline pipeline for %s", query.product)
    location = query.location if query.location != "unknown" else "Rajkot"
    vendors = await discover_vendors(query.product, query.category, location)

    if not vendors:
        logger.warning("Offline pipeline found no vendors.")
        return []

    if settings.test_call_phone.strip():
        logger.info(
            "Offline test-call mode is enabled; limiting vendor calls from %s to 1.",
            len(vendors),
        )
        vendors = vendors[:1]

    calls = await call_all_vendors(vendors, query.product)
    completed_calls = await asyncio.gather(*[_resolve_call(call) for call in calls], return_exceptions=True)

    results: list[UnifiedResult] = []
    extraction_tasks = []
    successful_calls: list[VoiceCallResult] = []

    for completed in completed_calls:
        if isinstance(completed, Exception):
            logger.warning("Call resolution failed: %s", completed)
            continue
        if completed.status != "completed" or not completed.transcript:
            logger.info("Skipping call %s with status=%s", completed.call_id, completed.status)
            continue
        successful_calls.append(completed)
        extraction_tasks.append(
            extract_from_transcript(completed.transcript, completed.vendor, query.product)
        )

    extracted = await asyncio.gather(*extraction_tasks, return_exceptions=True)
    for call, item in zip(successful_calls, extracted, strict=False):
        if isinstance(item, Exception):
            logger.warning("Transcript extraction failed for call %s: %s", call.call_id, item)
            continue
        results.append(item)

    logger.info("Offline pipeline completed with %s results", len(results))
    return results
