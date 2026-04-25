from __future__ import annotations

import asyncio
import logging

from app.models.schemas import StructuredQuery, UnifiedResult
from app.services import persistence
from app.services.online_discovery import PlatformStrategy, discover_platforms
from app.services.platform_adapters import get_adapters

logger = logging.getLogger(__name__)


async def _persist_safely(coroutine, context: str) -> None:
    try:
        await coroutine
    except Exception as exc:  # pragma: no cover - depends on external service
        logger.warning("Persistence skipped for %s: %s", context, exc)


async def _run_adapter(
    adapter,
    strategy: PlatformStrategy,
    location: str | None,
) -> list[UnifiedResult]:
    search_query = strategy.search_query.strip()
    results = await adapter.search(search_query, location=location)
    for result in results:
        if result.is_mock:
            result.name = strategy.platform_name
            continue
        if not result.name:
            result.name = strategy.platform_name
        if result.notes and strategy.platform_name.lower() not in result.notes.lower():
            result.notes = f"{result.notes} | Requested via {strategy.platform_name}"
        elif not result.notes:
            result.notes = f"Requested via {strategy.platform_name}"
    return results


def _dedupe_results(results: list[UnifiedResult]) -> list[UnifiedResult]:
    deduped: list[UnifiedResult] = []
    seen: set[str] = set()
    for result in results:
        key = result.url or f"{result.name}:{result.price}:{result.delivery_time}:{result.source_type}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return deduped


async def run(query: StructuredQuery, search_id: str | None = None) -> list[UnifiedResult]:
    logger.info("Starting online pipeline for %s", query.product)
    strategies = await discover_platforms(query)
    if not strategies:
        logger.info("No online platforms selected for %s", query.product)
        return []
    adapters = get_adapters([strategy.platform_id for strategy in strategies], query.category)

    tasks = [
        _run_adapter(adapter, strategy, query.location)
        for adapter, strategy in zip(adapters, strategies, strict=False)
    ]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    combined: list[UnifiedResult] = []
    for strategy, result in zip(strategies, raw_results, strict=False):
        if isinstance(result, Exception):
            logger.warning("Adapter %s failed: %s", strategy.platform_id, result)
            continue
        if search_id:
            await _persist_safely(
                persistence.record_online_results(
                    search_id=search_id,
                    query=query,
                    strategy=strategy,
                    results=result,
                ),
                f"online results {strategy.platform_id}",
            )
        combined.extend(result)

    combined = _dedupe_results(combined)
    logger.info("Online pipeline completed with %s results", len(combined))
    return combined
