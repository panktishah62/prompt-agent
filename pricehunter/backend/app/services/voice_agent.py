from __future__ import annotations

import asyncio
import logging
import math
import random
import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.config import settings
from app.models.schemas import VendorInfo, VoiceCallResult

logger = logging.getLogger(__name__)

BOLNA_CALL_URL = "https://api.bolna.ai/call"
BOLNA_STATUS_URL = "https://api.bolna.ai/executions/{execution_id}"
_WEBHOOK_CACHE_TTL = timedelta(minutes=30)
_EXECUTION_PAYLOADS: dict[str, tuple[datetime, dict[str, Any]]] = {}


def _normalize_indian_phone(phone_number: str) -> str | None:
    digits = "".join(char for char in phone_number if char.isdigit())
    if not digits:
        return None

    if phone_number.strip().startswith("+"):
        return f"+{digits}"

    if digits.startswith("91") and len(digits) >= 12:
        return f"+{digits}"

    if digits.startswith("0") and len(digits) >= 11:
        return f"+91{digits[1:]}"

    if len(digits) == 10:
        return f"+91{digits}"

    if 8 <= len(digits) <= 12:
        return f"+91{digits.lstrip('0')}"

    return None


def _call_destination_phone(vendor: VendorInfo) -> str:
    raw_phone = settings.test_call_phone.strip() or vendor.phone
    normalized = _normalize_indian_phone(raw_phone)
    return normalized or raw_phone


def _call_prompt(vendor: VendorInfo, product: str) -> str:
    destination_context = (
        f"You are speaking with a test operator acting as vendor {vendor.name}. "
        if settings.test_call_phone.strip()
        else f"You are speaking with shop vendor {vendor.name}. "
    )
    return (
        f"{destination_context}"
        f"Ask whether {product} is in stock, the current quoted price in rupees, whether any discount is available, "
        "and whether pickup or delivery is possible today. Start in English, but if the vendor responds in Hindi or "
        "sounds more comfortable in Hindi, continue in Hindi. Keep the conversation under 60 seconds, be concise, "
        "and end politely after you have price, availability, discount, and timing."
    )


def _mock_transcript(vendor: VendorInfo, product: str) -> str:
    lowered = product.lower()
    if any(keyword in lowered for keyword in ("iphone", "phone", "mobile")):
        prices = [57999, 59999, 62999, 64999, 68999]
        discounts = [0, 500, 1000, 1500]
        deliveries = ["pickup in 30 minutes", "same-day delivery", "delivery in 2 hours"]
    elif any(keyword in lowered for keyword in ("laptop", "macbook")):
        prices = [42999, 48999, 55999, 68999]
        discounts = [0, 1000, 2000, 3000]
        deliveries = ["pickup in 45 minutes", "same-day delivery", "delivery in 3 hours"]
    elif any(keyword in lowered for keyword in ("medicine", "tablet", "capsule", "syrup", "paracetamol")):
        prices = [89, 129, 179, 249, 399]
        discounts = [0, 10, 20, 30]
        deliveries = ["pickup in 10 minutes", "delivery in 20 minutes", "delivery in 35 minutes"]
    else:
        prices = [299, 499, 799, 1299, 2499, 3999]
        discounts = [0, 50, 100, 200]
        deliveries = ["pickup in 20 minutes", "delivery in 45 minutes", "same-day delivery"]

    price = random.choice(prices)
    delivery = random.choice(deliveries)
    discount = random.choice(discounts)
    availability = random.choice(["yes", "yes", "limited stock"])
    if discount:
        discount_line = f"We can reduce it to {max(price - discount, 1)} rupees if you confirm today."
    else:
        discount_line = "The quoted price is final for today."
    return (
        f"Agent: Hello, I am calling to check availability for {product}. "
        f"Vendor: Yes, we have {product} in stock, {availability}. "
        f"Vendor: The current price is {price} rupees. "
        f"Vendor: {discount_line} "
        f"Vendor: {delivery}."
    )


def _mock_extracted_data(transcript: str) -> dict[str, Any]:
    lowered = transcript.lower()
    price = None
    for token in transcript.split():
        normalized = token.replace(",", "")
        if normalized.isdigit():
            price = float(normalized)
            break
    delivery_time = None
    if "pickup in" in lowered:
        delivery_time = transcript[lowered.index("pickup in") :].split(".")[0]
    elif "delivery in" in lowered:
        delivery_time = transcript[lowered.index("delivery in") :].split(".")[0]
    elif "same-day delivery" in lowered:
        delivery_time = "same-day delivery"
    return {
        "price": price,
        "availability": "out of stock" not in lowered and "not available" not in lowered,
        "negotiated": any(phrase in lowered for phrase in ("reduce it", "discount", "offer")),
        "delivery_time": delivery_time,
        "notes": "Mock Bolna call result.",
        "confidence": 0.78 if price is not None else 0.58,
    }


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _build_call_payload(vendor: VendorInfo, product: str) -> dict[str, Any]:
    normalized_phone = _call_destination_phone(vendor)
    payload: dict[str, Any] = {
        "agent_id": settings.bolna_agent_id,
        "recipient_phone_number": normalized_phone,
        "user_data": {
            "product_name": product,
            "shop_name": vendor.name,
            "phone_number": vendor.phone,
            "address": vendor.address,
        },
    }
    return payload


def _prune_webhook_cache() -> None:
    now = datetime.utcnow()
    expired = [key for key, (created_at, _) in _EXECUTION_PAYLOADS.items() if now - created_at > _WEBHOOK_CACHE_TTL]
    for key in expired:
        _EXECUTION_PAYLOADS.pop(key, None)


def store_execution_webhook(payload: dict[str, Any]) -> str | None:
    execution_id = str(
        payload.get("call_id")
        or payload.get("id")
        or payload.get("execution_id")
        or payload.get("data", {}).get("id")
        or ""
    ).strip()
    if not execution_id:
        return None
    _prune_webhook_cache()
    _EXECUTION_PAYLOADS[execution_id] = (datetime.utcnow(), payload)
    return execution_id


def _cached_execution_payload(execution_id: str) -> dict[str, Any] | None:
    _prune_webhook_cache()
    item = _EXECUTION_PAYLOADS.get(execution_id)
    return item[1] if item else None


def _map_bolna_status(status: str | None) -> str:
    normalized = (status or "").strip().lower()
    if normalized in {"completed", "complete", "done"}:
        return "completed"
    if normalized in {"busy"}:
        return "busy"
    if normalized in {"no-answer", "no_answer", "no answer"}:
        return "no_answer"
    if normalized in {"failed", "error", "canceled", "cancelled"}:
        return "failed"
    return "busy"


def _extract_transcript_from_payload(payload: dict[str, Any]) -> str | None:
    direct = payload.get("transcript")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    if isinstance(payload.get("transcript"), list):
        segments = []
        for item in payload["transcript"]:
            if isinstance(item, dict):
                text = item.get("content") or item.get("text") or item.get("message")
                speaker = item.get("speaker") or item.get("role")
                if text:
                    segments.append(f"{speaker or 'Speaker'}: {text}")
            elif isinstance(item, str) and item.strip():
                segments.append(item.strip())
        if segments:
            return " ".join(segments)
    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_transcript_from_payload(data)
    return None


def _extract_extracted_data(payload: dict[str, Any]) -> dict[str, Any] | None:
    extraction = payload.get("extraction")
    if isinstance(extraction, dict):
        return extraction
    extracted = payload.get("extracted_data")
    if isinstance(extracted, dict):
        return extracted
    data = payload.get("data")
    if isinstance(data, dict):
        nested_extraction = data.get("extraction")
        if isinstance(nested_extraction, dict):
            return nested_extraction
        nested = data.get("extracted_data")
        if isinstance(nested, dict):
            return nested
    return None


def _extract_duration_seconds(payload: dict[str, Any]) -> int | None:
    duration = payload.get("duration") or payload.get("duration_seconds") or payload.get("call_length")
    data = payload.get("data")
    if duration is None and isinstance(data, dict):
        duration = data.get("duration") or data.get("duration_seconds") or data.get("call_length")
    if isinstance(duration, (int, float)):
        return max(0, int(math.ceil(duration)))
    if isinstance(duration, str):
        try:
            return max(0, int(math.ceil(float(duration))))
        except ValueError:
            return None
    return None


def _build_call_result_from_payload(call: VoiceCallResult, payload: dict[str, Any]) -> VoiceCallResult:
    transcript = _extract_transcript_from_payload(payload) or call.transcript
    extracted_data = _extract_extracted_data(payload) or call.extracted_data
    status = _map_bolna_status(payload.get("status") or payload.get("event"))
    return VoiceCallResult(
        vendor=call.vendor,
        call_id=call.call_id,
        status=status,  # type: ignore[arg-type]
        transcript=transcript,
        duration_seconds=_extract_duration_seconds(payload) or call.duration_seconds,
        extracted_data=extracted_data,
        is_mock=False,
    )


async def call_vendor(vendor: VendorInfo, product: str, api_key: str | None = None) -> VoiceCallResult:
    """Trigger an outbound call to a vendor via Bolna."""

    effective_key = api_key or settings.bolna_api_key
    if settings.mock_voice_calls or not effective_key or not settings.bolna_agent_id:
        logger.info("Mock voice call for vendor=%s", vendor.name)
        await asyncio.sleep(random.uniform(0.2, 0.8))
        transcript = _mock_transcript(vendor, product)
        return VoiceCallResult(
            vendor=vendor,
            call_id=f"mock-call-{uuid.uuid4()}",
            status="completed",
            transcript=transcript,
            duration_seconds=random.randint(24, 57),
            extracted_data=_mock_extracted_data(transcript),
            is_mock=True,
        )

    destination_phone = _call_destination_phone(vendor)
    if not destination_phone.startswith("+"):
        logger.warning("Vendor phone could not be normalized for Bolna: vendor=%s phone=%s", vendor.name, vendor.phone)
    if settings.test_call_phone.strip():
        logger.info(
            "Triggering Bolna test call for vendor=%s via test phone=%s",
            vendor.name,
            destination_phone,
        )
    else:
        logger.info("Triggering Bolna call for vendor=%s", vendor.name)

    async with httpx.AsyncClient() as client:
        payload = _build_call_payload(vendor, product)
        response = await client.post(
            BOLNA_CALL_URL,
            headers=_auth_headers(effective_key),
            json=payload,
            timeout=30,
        )
        if response.is_error:
            logger.warning(
                "Bolna call request failed for vendor=%s status=%s body=%s payload=%s",
                vendor.name,
                response.status_code,
                response.text,
                payload,
            )
        response.raise_for_status()
        payload = response.json()
        call_id = (
            payload.get("id")
            or payload.get("execution_id")
            or payload.get("call_id")
            or f"bolna-call-{uuid.uuid4()}"
        )
        return VoiceCallResult(vendor=vendor, call_id=str(call_id), status="busy", is_mock=False)


async def call_all_vendors(vendors: list[VendorInfo], product: str) -> list[VoiceCallResult]:
    tasks = [call_vendor(vendor, product) for vendor in vendors]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    completed: list[VoiceCallResult] = []
    for vendor, result in zip(vendors, results, strict=False):
        if isinstance(result, Exception):
            logger.warning("Call initiation failed for %s: %s", vendor.name, result)
            transcript = _mock_transcript(vendor, product)
            completed.append(
                VoiceCallResult(
                    vendor=vendor,
                    call_id=f"fallback-{uuid.uuid4()}",
                    status="completed",
                    transcript=transcript,
                    duration_seconds=random.randint(20, 55),
                    extracted_data=_mock_extracted_data(transcript),
                    is_mock=True,
                )
            )
            continue
        completed.append(result)
    return completed


async def poll_call_result(call: VoiceCallResult, timeout_seconds: int = 120) -> VoiceCallResult:
    if call.is_mock or settings.mock_voice_calls or not settings.bolna_api_key or not settings.bolna_agent_id:
        return call
    if call.status != "busy":
        return call

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    async with httpx.AsyncClient() as client:
        while asyncio.get_running_loop().time() < deadline:
            cached_payload = _cached_execution_payload(call.call_id)
            if cached_payload is not None:
                resolved = _build_call_result_from_payload(call, cached_payload)
                if resolved.status in {"completed", "failed", "no_answer"}:
                    return resolved

            try:
                response = await client.get(
                    BOLNA_STATUS_URL.format(execution_id=call.call_id),
                    headers=_auth_headers(settings.bolna_api_key),
                    timeout=20,
                )
                if response.status_code == 404:
                    logger.info("Bolna execution %s is not ready yet; retrying.", call.call_id)
                    await asyncio.sleep(5)
                    continue
                response.raise_for_status()
                payload = response.json()
                resolved = _build_call_result_from_payload(call, payload)
                if resolved.status in {"completed", "failed", "no_answer"}:
                    return resolved
            except httpx.HTTPStatusError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    logger.info("Bolna execution %s returned 404; retrying.", call.call_id)
                    await asyncio.sleep(5)
                    continue
                raise
            await asyncio.sleep(5)

    logger.warning("Timed out waiting for call %s; falling back to transcript stub.", call.call_id)
    transcript = call.transcript or _mock_transcript(call.vendor, "the requested product")
    return VoiceCallResult(
        vendor=call.vendor,
        call_id=call.call_id,
        status="completed",
        transcript=transcript,
        duration_seconds=call.duration_seconds or 60,
        extracted_data=call.extracted_data or _mock_extracted_data(transcript),
        is_mock=True,
    )
