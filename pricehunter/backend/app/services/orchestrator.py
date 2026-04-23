from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from app.database import queries_collection, results_collection
from app.models.schemas import SearchResponse, SearchStrategy, StructuredQuery, UnifiedResult
from app.services import comparator, offline_pipeline, online_pipeline, query_structurer

logger = logging.getLogger(__name__)


class UnsupportedCategoryError(ValueError):
    """Raised when a query falls outside the currently supported categories."""


async def store_results(query: StructuredQuery, results: list[UnifiedResult]) -> None:
    try:
        await queries_collection.insert_one(query.model_dump(mode="json"))
        if results:
            await results_collection.insert_many([result.model_dump(mode="json") for result in results])
    except Exception as exc:  # pragma: no cover - depends on external service
        logger.warning("Failed to store results in MongoDB: %s", exc)


async def run_search_structured(
    structured_query: StructuredQuery,
    search_strategy: SearchStrategy = "both",
) -> SearchResponse:
    start_time = time.time()
    if not query_structurer.is_supported_category(structured_query.category):
        raise UnsupportedCategoryError(query_structurer.unsupported_category_message())
    logger.info(
        "Running orchestrated search for product=%s strategy=%s",
        structured_query.product,
        search_strategy,
    )

    online_results: list[UnifiedResult] | Exception = []
    offline_results: list[UnifiedResult] | Exception = []

    if search_strategy == "both":
        online_results, offline_results = await asyncio.gather(
            online_pipeline.run(structured_query),
            offline_pipeline.run(structured_query),
            return_exceptions=True,
        )
    elif search_strategy == "online":
        online_results = await online_pipeline.run(structured_query)
    else:
        offline_results = await offline_pipeline.run(structured_query)

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
        search_strategy=search_strategy,
    )


async def run_search(raw_query: str, location: Optional[str] = None) -> SearchResponse:
    start_time = time.time()
    logger.info("Running orchestrated search for query=%s", raw_query)

    structured_query = await query_structurer.structure_query(raw_query)
    if location:
        structured_query.location = location

    result = await run_search_structured(structured_query, search_strategy="both")
    result.total_time_seconds = round(time.time() - start_time, 2)
    return result
