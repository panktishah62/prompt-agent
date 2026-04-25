from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from app.config import settings
from app.models.schemas import (
    SearchProgressSnapshot,
    SearchProgressStep,
    SearchResponse,
    SearchStrategy,
    StructuredQuery,
    UnifiedResult,
    VendorInfo,
    VoiceCallResult,
)
from app.services import comparator, orchestrator, persistence, query_structurer
from app.services.online_discovery import PlatformStrategy, discover_platforms
from app.services.platform_adapters import get_adapters
from app.services.vendor_discovery import discover_vendors
from app.services.voice_agent import call_vendor, poll_call_result
from app.services.voice_extractor import extract_from_call_result

logger = logging.getLogger(__name__)

_SEARCHES: dict[str, SearchProgressSnapshot] = {}
_TASKS: dict[str, asyncio.Task[None]] = {}


async def _persist_safely(coroutine, context: str) -> None:
    try:
        await coroutine
    except Exception as exc:  # pragma: no cover - depends on external service
        logger.warning("Persistence skipped for %s: %s", context, exc)


async def _run_with_semaphore(
    semaphore: asyncio.Semaphore,
    coroutine,
) -> list[UnifiedResult]:
    async with semaphore:
        return await coroutine


def _step_id(prefix: str, value: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")
    collapsed = "-".join(chunk for chunk in normalized.split("-") if chunk)
    return f"{prefix}-{collapsed or 'item'}"


def _touch(snapshot: SearchProgressSnapshot) -> None:
    snapshot.updated_at = datetime.utcnow()


def _set_step(
    snapshot: SearchProgressSnapshot,
    step_id: str,
    status: str,
    detail: str | None = None,
) -> None:
    for step in snapshot.steps:
        if step.id == step_id:
            step.status = status
            if detail is not None:
                step.detail = detail
            _touch(snapshot)
            return


def _dedupe_results(results: list[UnifiedResult]) -> list[UnifiedResult]:
    deduped: list[UnifiedResult] = []
    seen: set[str] = set()
    for result in results:
        key = result.url or f"{result.source_type}:{result.name}:{result.price}:{result.phone}:{result.delivery_time}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return deduped


def _update_partial_results(
    snapshot: SearchProgressSnapshot,
    new_results: list[UnifiedResult],
    intent: str,
) -> None:
    combined = _dedupe_results(snapshot.partial_results + new_results)
    snapshot.partial_results = comparator.rank(combined, intent)
    _touch(snapshot)


def _apply_online_strategy_name(result: UnifiedResult, strategy: PlatformStrategy) -> UnifiedResult:
    if result.is_mock:
        result.name = strategy.platform_name
        return result
    if not result.name:
        result.name = strategy.platform_name
    if result.notes and strategy.platform_name.lower() not in result.notes.lower():
        result.notes = f"{result.notes} | Requested via {strategy.platform_name}"
    elif not result.notes:
        result.notes = f"Requested via {strategy.platform_name}"
    return result


def _build_steps(
    query: StructuredQuery,
    search_strategy: SearchStrategy,
    vendors: list[VendorInfo],
    platforms: list[PlatformStrategy],
) -> list[SearchProgressStep]:
    steps = [
        SearchProgressStep(
            id="understanding",
            label=f"Understanding {query.product} in {query.location}",
            status="completed",
            detail="Search brief locked in.",
        )
    ]

    if search_strategy in {"both", "offline"}:
        steps.append(
            SearchProgressStep(
                id="vendor-discovery",
                label=f"Found {len(vendors)} nearby vendors",
                status="completed",
                detail="Vendor discovery complete.",
            )
        )
        for vendor in vendors:
            steps.append(
                SearchProgressStep(
                    id=_step_id("offline", vendor.name),
                    label=f"Contacting {vendor.name}",
                    status="pending",
                    detail="Waiting to start call.",
                )
            )

    if search_strategy in {"both", "online"}:
        steps.append(
            SearchProgressStep(
                id="online-discovery",
                label=f"Checking {len(platforms)} online platforms",
                status="completed",
                detail="Platform plan ready.",
            )
        )
        for strategy in platforms:
            steps.append(
                SearchProgressStep(
                    id=_step_id("online", strategy.platform_id),
                    label=f"Fetching {strategy.platform_name}",
                    status="pending",
                    detail="Waiting to start fetch.",
                )
            )
    return steps


async def _resolve_vendor(
    snapshot: SearchProgressSnapshot,
    query: StructuredQuery,
    vendor: VendorInfo,
) -> list[UnifiedResult]:
    step_id = _step_id("offline", vendor.name)
    _set_step(snapshot, step_id, "running", "Calling vendor for live availability.")
    try:
        call = await call_vendor(vendor, query.product)
        await _persist_safely(
            persistence.record_call_attempt(
                search_id=snapshot.search_id,
                query=query,
                call=call,
            ),
            f"call start {call.call_id}",
        )
        completed = await poll_call_result(call)
        if completed.status != "completed" and not completed.extracted_data:
            await _persist_safely(
                persistence.record_call_attempt(
                    search_id=snapshot.search_id,
                    query=query,
                    call=completed,
                ),
                f"call completion {completed.call_id}",
            )
            _set_step(snapshot, step_id, "failed", f"Call ended with status: {completed.status}.")
            return []
        if not completed.transcript and not completed.extracted_data:
            await _persist_safely(
                persistence.record_call_attempt(
                    search_id=snapshot.search_id,
                    query=query,
                    call=completed,
                ),
                f"call completion {completed.call_id}",
            )
            _set_step(snapshot, step_id, "failed", "Call completed without usable result data.")
            return []

        result = await extract_from_call_result(completed, query.product)
        await _persist_safely(
            persistence.record_call_attempt(
                search_id=snapshot.search_id,
                query=query,
                call=completed,
                extracted_result=result,
            ),
            f"call result {completed.call_id}",
        )
        _update_partial_results(snapshot, [result], query.intent)
        detail = "Quote captured."
        if result.price is not None:
            detail = f"Quote captured at INR {result.price:,.0f}."
        _set_step(snapshot, step_id, "completed", detail)
        return [result]
    except Exception as exc:  # pragma: no cover - external integrations
        logger.warning("Offline vendor resolution failed for %s: %s", vendor.name, exc)
        _set_step(snapshot, step_id, "failed", "Could not fetch vendor quote.")
        return []


async def _resolve_online_platform(
    snapshot: SearchProgressSnapshot,
    query: StructuredQuery,
    strategy: PlatformStrategy,
    adapter,
) -> list[UnifiedResult]:
    step_id = _step_id("online", strategy.platform_id)
    _set_step(snapshot, step_id, "running", "Fetching online listings.")
    try:
        raw_results = await adapter.search(strategy.search_query, location=query.location)
        results = [_apply_online_strategy_name(result, strategy) for result in raw_results]
        await _persist_safely(
            persistence.record_online_results(
                search_id=snapshot.search_id,
                query=query,
                strategy=strategy,
                results=results,
            ),
            f"online results {strategy.platform_id}",
        )
        _update_partial_results(snapshot, results, query.intent)
        detail = f"{len(results)} listing(s) added." if results else "No usable listings found."
        _set_step(snapshot, step_id, "completed", detail)
        return results
    except Exception as exc:  # pragma: no cover - external integrations
        logger.warning("Online platform fetch failed for %s: %s", strategy.platform_id, exc)
        _set_step(snapshot, step_id, "failed", "Could not fetch listings.")
        return []


async def _run_background_search(
    snapshot: SearchProgressSnapshot,
    query: StructuredQuery,
    search_strategy: SearchStrategy,
    vendors: list[VendorInfo],
    platforms: list[PlatformStrategy],
) -> None:
    started = snapshot.started_at.timestamp()
    snapshot.status = "running"
    _touch(snapshot)

    online_results: list[UnifiedResult] = []
    offline_results: list[UnifiedResult] = []

    try:
        tasks: list[asyncio.Task[list[UnifiedResult]]] = []

        if search_strategy in {"both", "offline"} and vendors:
            vendors_to_contact = vendors[:1] if settings.test_call_phone.strip() else vendors
            if settings.test_call_phone.strip():
                for vendor in vendors[1:]:
                    _set_step(
                        snapshot,
                        _step_id("offline", vendor.name),
                        "completed",
                        "Skipped in test-call mode.",
                    )
            concurrency_limit = max(1, settings.bolna_max_concurrent_calls)
            semaphore = asyncio.Semaphore(concurrency_limit)
            tasks.extend(
                asyncio.create_task(_run_with_semaphore(semaphore, _resolve_vendor(snapshot, query, vendor)))
                for vendor in vendors_to_contact
            )

        if search_strategy in {"both", "online"} and platforms:
            adapters = get_adapters([strategy.platform_id for strategy in platforms], query.category)
            tasks.extend(
                asyncio.create_task(_resolve_online_platform(snapshot, query, strategy, adapter))
                for strategy, adapter in zip(platforms, adapters, strict=False)
            )

        completed = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []
        all_results: list[UnifiedResult] = []
        for item in completed:
            if isinstance(item, Exception):
                logger.warning("Background search task failed: %s", item)
                continue
            all_results.extend(item)

        ranked = comparator.rank(_dedupe_results(all_results), query.intent)
        online_results = [result for result in ranked if result.source_type == "online"]
        offline_results = [result for result in ranked if result.source_type == "offline"]

        snapshot.final_results = SearchResponse(
            query=query,
            results=ranked,
            online_count=len(online_results),
            offline_count=len(offline_results),
            total_time_seconds=round(time.time() - started, 2),
            search_strategy=search_strategy,
        )
        snapshot.partial_results = ranked
        snapshot.status = "completed"
        _touch(snapshot)
        await _persist_safely(
            persistence.complete_search_session(
                search_id=snapshot.search_id,
                query=query,
                final_results=ranked,
                status="completed",
                total_time_seconds=round(time.time() - started, 2),
            ),
            f"search completion {snapshot.search_id}",
        )
    except Exception as exc:  # pragma: no cover - background orchestration
        logger.exception("Background search failed for %s", query.product)
        snapshot.status = "failed"
        snapshot.error = str(exc)
        _touch(snapshot)
        await _persist_safely(
            persistence.complete_search_session(
                search_id=snapshot.search_id,
                query=query,
                final_results=snapshot.partial_results,
                status="failed",
                error=str(exc),
                total_time_seconds=round(time.time() - started, 2),
            ),
            f"search failure {snapshot.search_id}",
        )
    finally:
        _TASKS.pop(snapshot.search_id, None)


async def start_search(
    query: StructuredQuery,
    search_strategy: SearchStrategy = "both",
    request_metadata: dict[str, str | None] | None = None,
    session_id: str | None = None,
) -> SearchProgressSnapshot:
    if not query_structurer.is_supported_category(query.category):
        raise orchestrator.UnsupportedCategoryError(query_structurer.unsupported_category_message())
    started_at = datetime.utcnow()

    vendor_task = (
        discover_vendors(query.product, query.category, query.location if query.location != "unknown" else "Rajkot")
        if search_strategy in {"both", "offline"}
        else asyncio.sleep(0, result=[])
    )
    platform_task = (
        discover_platforms(query)
        if search_strategy in {"both", "online"}
        else asyncio.sleep(0, result=[])
    )

    vendors, platforms = await asyncio.gather(vendor_task, platform_task)

    snapshot = SearchProgressSnapshot(
        query=query,
        status="running",
        discovered_vendors=vendors,
        online_platforms=[strategy.platform_name for strategy in platforms],
        steps=_build_steps(query, search_strategy, vendors, platforms),
        started_at=started_at,
        updated_at=started_at,
    )
    await _persist_safely(
        persistence.initialize_search_session(
            search_id=snapshot.search_id,
            query=query,
            search_strategy=search_strategy,
            request_metadata=request_metadata,
            session_id=session_id,
            source_flow="chat",
            discovered_vendors=vendors,
            online_platforms=platforms,
        ),
        f"search init {snapshot.search_id}",
    )
    _SEARCHES[snapshot.search_id] = snapshot
    _TASKS[snapshot.search_id] = asyncio.create_task(
        _run_background_search(snapshot, query, search_strategy, vendors, platforms)
    )
    return snapshot


def get_snapshot(search_id: str) -> SearchProgressSnapshot | None:
    return _SEARCHES.get(search_id)
