from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from app.database import queries_collection, results_collection
from app.models.schemas import SearchResponse, StructuredQuery, UnifiedResult
from app.services import comparator, offline_pipeline, online_pipeline, query_structurer

logger = logging.getLogger(__name__)


async def store_results(query: StructuredQuery, results: list[UnifiedResult]) -> None:
    try:
        await queries_collection.insert_one(query.model_dump(mode="json"))
        if results:
            await results_collection.insert_many([result.model_dump(mode="json") for result in results])
    except Exception as exc:  # pragma: no cover - depends on external service
        logger.warning("Failed to store results in MongoDB: %s", exc)


async def run_search(raw_query: str, location: Optional[str] = None) -> SearchResponse:
    start_time = time.time()
    logger.info("Running orchestrated search for query=%s", raw_query)

    structured_query = await query_structurer.structure_query(raw_query)
    if location:
        structured_query.location = location

    online_results, offline_results = await asyncio.gather(
        online_pipeline.run(structured_query),
        offline_pipeline.run(structured_query),
        return_exceptions=True,
    )

    if isinstance(online_results, Exception):
        logger.warning("Online pipeline failed: %s", online_results)
        online_results = []
    if isinstance(offline_results, Exception):
        logger.warning("Offline pipeline failed: %s", offline_results)
        offline_results = []

    all_results = online_results + offline_results
    ranked_results = comparator.rank(all_results, structured_query.intent)

    await store_results(structured_query, ranked_results)

    total_time = time.time() - start_time
    logger.info(
        "Search complete: total=%s online=%s offline=%s in %.2fs",
        len(ranked_results),
        len(online_results),
        len(offline_results),
        total_time,
    )

    return SearchResponse(
        query=structured_query,
        results=ranked_results,
        online_count=len(online_results),
        offline_count=len(offline_results),
        total_time_seconds=round(total_time, 2),
    )
