from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from app.database import (
    call_attempts_collection,
    online_results_collection,
    price_history_collection,
    product_catalog_collection,
    raw_webhooks_collection,
    search_sessions_collection,
    vendor_product_observations_collection,
    vendor_profiles_collection,
)
from app.models.schemas import StructuredQuery, UnifiedResult, VendorInfo, VoiceCallResult
from app.services.online_discovery import PlatformStrategy

logger = logging.getLogger(__name__)

OBSERVATION_TTL_DAYS = 7


def _normalize_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "unknown"


def _extract_pincode(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"\b\d{6}\b", value)
    return match.group(0) if match else None


def _location_doc(value: str | None) -> dict[str, Any]:
    raw = (value or "unknown").strip() or "unknown"
    return {
        "raw": raw,
        "normalized": _normalize_key(raw),
        "pincode": _extract_pincode(raw),
    }


def _query_tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 1]


def _product_key(product: str, category: str) -> str:
    return f"{category}:{_normalize_key(product)}"


def _vendor_key_from_vendor(vendor: VendorInfo, source_type: str = "offline") -> str:
    if vendor.place_id:
        return f"{source_type}:place:{vendor.place_id}"
    if vendor.phone:
        digits = "".join(char for char in vendor.phone if char.isdigit())
        if digits:
            return f"{source_type}:phone:{digits}"
    return f"{source_type}:name:{_normalize_key(vendor.name)}"


def _vendor_key_from_result(result: UnifiedResult, platform_id: str, source_type: str = "online") -> str:
    if result.url:
        parsed = urlparse(result.url)
        host = parsed.netloc or platform_id
        return f"{source_type}:url:{_normalize_key(host)}:{_normalize_key(result.name)}"
    return f"{source_type}:platform:{platform_id}:{_normalize_key(result.name)}"


def _now() -> datetime:
    return datetime.utcnow()


async def upsert_product(product: str, category: str) -> dict[str, Any]:
    key = _product_key(product, category)
    now = _now()
    doc = {
        "product_key": key,
        "canonical_name": product,
        "category": category,
        "normalized_tokens": _query_tokens(product),
        "updated_at": now,
    }
    await product_catalog_collection.update_one(
        {"product_key": key},
        {
            "$set": doc,
            "$setOnInsert": {"created_at": now, "aliases": [product]},
            "$addToSet": {"aliases": product},
        },
        upsert=True,
    )
    return {**doc, "aliases": [product]}


async def upsert_offline_vendor(vendor: VendorInfo, category: str | None = None) -> dict[str, Any]:
    vendor_key = _vendor_key_from_vendor(vendor, source_type="offline")
    now = _now()
    location = _location_doc(vendor.address)
    doc = {
        "vendor_key": vendor_key,
        "source_type": "offline",
        "canonical_name": vendor.name,
        "phone": vendor.phone,
        "address": vendor.address,
        "place_id": vendor.place_id,
        "location": location,
        "rating": vendor.rating,
        "user_rating_count": vendor.user_rating_count,
        "last_seen_at": now,
        "is_mock": vendor.is_mock,
    }
    set_on_insert = {
        "created_at": now,
        "aliases": [vendor.name],
        "categories": [category] if category else [],
    }
    await vendor_profiles_collection.update_one(
        {"vendor_key": vendor_key},
        {
            "$set": doc,
            "$setOnInsert": set_on_insert,
            "$addToSet": {
                "aliases": vendor.name,
                **({"categories": category} if category else {}),
            },
        },
        upsert=True,
    )
    return {**doc, "aliases": [vendor.name], "categories": [category] if category else []}


async def upsert_online_vendor(result: UnifiedResult, platform_name: str, platform_id: str) -> dict[str, Any]:
    vendor_key = _vendor_key_from_result(result, platform_id, source_type="online")
    now = _now()
    parsed = urlparse(result.url or "")
    domain = parsed.netloc or None
    doc = {
        "vendor_key": vendor_key,
        "source_type": "online",
        "canonical_name": result.name or platform_name,
        "platform_name": platform_name,
        "platform_id": platform_id,
        "domain": domain,
        "location": _location_doc(result.address),
        "last_seen_at": now,
        "is_mock": result.is_mock,
    }
    await vendor_profiles_collection.update_one(
        {"vendor_key": vendor_key},
        {
            "$set": doc,
            "$setOnInsert": {"created_at": now, "aliases": [result.name or platform_name]},
            "$addToSet": {"aliases": result.name or platform_name},
        },
        upsert=True,
    )
    return {**doc, "aliases": [result.name or platform_name]}


async def initialize_search_session(
    *,
    search_id: str,
    query: StructuredQuery,
    search_strategy: str,
    request_metadata: dict[str, Any] | None = None,
    session_id: str | None = None,
    source_flow: str = "chat",
    discovered_vendors: list[VendorInfo] | None = None,
    online_platforms: list[PlatformStrategy] | None = None,
) -> None:
    now = _now()
    product = await upsert_product(query.product, query.category)
    location = _location_doc(query.location)

    vendor_keys: list[str] = []
    if discovered_vendors:
        for vendor in discovered_vendors:
            vendor_doc = await upsert_offline_vendor(vendor, query.category)
            vendor_keys.append(vendor_doc["vendor_key"])

    await search_sessions_collection.update_one(
        {"search_id": search_id},
        {
            "$set": {
                "search_id": search_id,
                "session_id": session_id,
                "source_flow": source_flow,
                "status": "running",
                "query": query.model_dump(mode="json"),
                "product": product,
                "location": location,
                "search_strategy": search_strategy,
                "request_metadata": request_metadata or {},
                "discovered_vendor_keys": vendor_keys,
                "online_platforms": [strategy.model_dump(mode="json") for strategy in (online_platforms or [])],
                "updated_at": now,
            },
            "$setOnInsert": {
                "created_at": now,
            },
        },
        upsert=True,
    )


async def complete_search_session(
    *,
    search_id: str,
    query: StructuredQuery,
    final_results: list[UnifiedResult],
    status: str,
    error: str | None = None,
    total_time_seconds: float | None = None,
) -> None:
    now = _now()
    calls_attempted = await call_attempts_collection.count_documents({"search_id": search_id})
    calls_completed = await call_attempts_collection.count_documents(
        {"search_id": search_id, "status": {"$in": ["completed", "no_answer", "busy", "failed"]}}
    )
    online_results_count = await online_results_collection.count_documents({"search_id": search_id})
    offline_results_count = len([result for result in final_results if result.source_type == "offline"])
    best_price = min((result.price for result in final_results if result.price is not None), default=None)
    best_result = next((result for result in final_results if result.price == best_price), None) if best_price else None

    await search_sessions_collection.update_one(
        {"search_id": search_id},
        {
            "$set": {
                "status": status,
                "updated_at": now,
                "completed_at": now if status == "completed" else None,
                "error": error,
                "summary": {
                    "calls_attempted": calls_attempted,
                    "calls_completed": calls_completed,
                    "online_results_count": online_results_count,
                    "offline_results_count": offline_results_count,
                    "best_price": best_price,
                    "best_source": best_result.name if best_result else None,
                    "total_time_seconds": total_time_seconds,
                },
                "top_results": [result.model_dump(mode="json") for result in final_results[:5]],
                "query": query.model_dump(mode="json"),
            }
        },
    )


async def record_call_attempt(
    *,
    search_id: str,
    query: StructuredQuery,
    call: VoiceCallResult,
    extracted_result: UnifiedResult | None = None,
) -> None:
    now = _now()
    product = await upsert_product(query.product, query.category)
    vendor = await upsert_offline_vendor(call.vendor, query.category)
    location = _location_doc(query.location)

    await call_attempts_collection.update_one(
        {"call_id": call.call_id},
        {
            "$set": {
                "search_id": search_id,
                "call_id": call.call_id,
                "status": call.status,
                "product": product,
                "vendor": vendor,
                "location": location,
                "duration_seconds": call.duration_seconds,
                "transcript": call.transcript,
                "extracted_data": call.extracted_data,
                "result_snapshot": extracted_result.model_dump(mode="json") if extracted_result else None,
                "is_mock": call.is_mock,
                "updated_at": now,
                "completed_at": now if call.status != "busy" else None,
            },
            "$setOnInsert": {
                "started_at": now,
            },
        },
        upsert=True,
    )

    if extracted_result:
        await _record_observation(
            search_id=search_id,
            query=query,
            product=product,
            vendor=vendor,
            result=extracted_result,
            source_channel="live_call",
        )


async def record_online_results(
    *,
    search_id: str,
    query: StructuredQuery,
    strategy: PlatformStrategy,
    results: list[UnifiedResult],
) -> None:
    if not results:
        return

    product = await upsert_product(query.product, query.category)
    location = _location_doc(query.location)
    now = _now()

    for rank, result in enumerate(results, start=1):
        vendor = await upsert_online_vendor(result, strategy.platform_name, strategy.platform_id)
        result_key = f"{search_id}:{strategy.platform_id}:{_normalize_key(result.url or result.name)}:{rank}"
        await online_results_collection.update_one(
            {"result_key": result_key},
            {
                "$set": {
                    "result_key": result_key,
                    "search_id": search_id,
                    "product": product,
                    "vendor": vendor,
                    "platform": strategy.model_dump(mode="json"),
                    "location": location,
                    "result": result.model_dump(mode="json"),
                    "rank": rank,
                    "fetched_at": now,
                }
            },
            upsert=True,
        )
        await _record_observation(
            search_id=search_id,
            query=query,
            product=product,
            vendor=vendor,
            result=result,
            source_channel="online_fetch",
        )


async def record_raw_webhook(execution_id: str | None, payload: dict[str, Any]) -> None:
    await raw_webhooks_collection.insert_one(
        {
            "execution_id": execution_id,
            "payload": payload,
            "received_at": _now(),
        }
    )


async def _record_observation(
    *,
    search_id: str,
    query: StructuredQuery,
    product: dict[str, Any],
    vendor: dict[str, Any],
    result: UnifiedResult,
    source_channel: str,
) -> None:
    now = _now()
    location = _location_doc(query.location or result.address)
    observation_key = ":".join(
        [
            vendor["vendor_key"],
            product["product_key"],
            location["pincode"] or location["normalized"],
            result.source_type,
        ]
    )

    observation_doc = {
        "observation_key": observation_key,
        "search_id": search_id,
        "product": product,
        "vendor": vendor,
        "location": location,
        "source_type": result.source_type,
        "source_channel": source_channel,
        "latest_price": result.price,
        "availability": result.availability,
        "delivery_time": result.delivery_time,
        "confidence": result.confidence,
        "url": result.url,
        "notes": result.notes,
        "last_observed_at": now,
        "expires_at": now + timedelta(days=OBSERVATION_TTL_DAYS),
        "is_mock": result.is_mock,
    }

    await vendor_product_observations_collection.update_one(
        {"observation_key": observation_key},
        {
            "$set": observation_doc,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )

    await price_history_collection.insert_one(
        {
            "search_id": search_id,
            "product": product,
            "vendor": vendor,
            "location": location,
            "source_type": result.source_type,
            "source_channel": source_channel,
            "price": result.price,
            "availability": result.availability,
            "delivery_time": result.delivery_time,
            "confidence": result.confidence,
            "url": result.url,
            "notes": result.notes,
            "observed_at": now,
            "is_mock": result.is_mock,
        }
    )
