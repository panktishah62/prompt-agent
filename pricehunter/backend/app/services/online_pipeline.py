from __future__ import annotations

import asyncio
import logging

from app.models.schemas import StructuredQuery, UnifiedResult
from app.services.online_discovery import PlatformStrategy, discover_platforms
from app.services.platform_adapters import get_adapters

logger = logging.getLogger(__name__)


async def _run_adapter(
    adapter,
    strategy: PlatformStrategy,
    product: str,
    location: str | None,
) -> list[UnifiedResult]:
    search_query = product.strip() or strategy.search_query
    results = await adapter.search(search_query, location=location)
    for result in results:
        result.name = strategy.platform_name
    return results


async def run(query: StructuredQuery) -> list[UnifiedResult]:
    logger.info("Starting online pipeline for %s", query.product)
    strategies = await discover_platforms(query)
    if not strategies:
        logger.info("No online platforms selected for %s", query.product)
        return []
    adapters = get_adapters([strategy.platform_id for strategy in strategies], query.category)

    tasks = [
        _run_adapter(adapter, strategy, query.product, query.location)
        for adapter, strategy in zip(adapters, strategies, strict=False)
    ]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    combined: list[UnifiedResult] = []
    for strategy, result in zip(strategies, raw_results, strict=False):
        if isinstance(result, Exception):
            logger.warning("Adapter %s failed: %s", strategy.platform_id, result)
            continue
        combined.extend(result)

    logger.info("Online pipeline completed with %s results", len(combined))
    return combined
