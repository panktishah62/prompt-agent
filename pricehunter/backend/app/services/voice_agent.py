from __future__ import annotations

import asyncio
import logging
import math
import random
import uuid

import httpx

from app.config import settings
from app.models.schemas import VendorInfo, VoiceCallResult

logger = logging.getLogger(__name__)

BLAND_CALLS_URL = "https://api.bland.ai/v1/calls"


def _call_destination_phone(vendor: VendorInfo) -> str:
    return settings.test_call_phone.strip() or vendor.phone


def _call_task(vendor: VendorInfo, product: str) -> str:
    if settings.test_call_phone.strip():
        return (
            f"You are calling a test operator standing in for vendor {vendor.name}. "
            f"Ask whether they have {product} in stock, what the current price is, and whether any "
            "discount is available. Treat the caller's answers as the vendor's answers. Be polite and "
            "professional. Speak in Hindi or English based on how they respond. Keep the call under 60 seconds."
        )
    return (
        f"You are calling a shop to inquire about a product. Ask if they have {product} "
        "in stock, what is their price, and if they can offer any discount. Be polite and "
        "professional. Speak in Hindi or English based on how the vendor responds. "
        "Keep the call under 60 seconds."
    )


def _mock_transcript(vendor: VendorInfo, product: str) -> str:
    lowered = product.lower()
    if any(keyword in lowered for keyword in ("tomato", "potato", "onion", "vegetable", "fruit", "milk", "rice")):
        prices = [39, 49, 59, 79, 99, 129]
        discounts = [0, 5, 10, 15]
        deliveries = ["pickup in 15 minutes", "delivery in 30 minutes", "delivery in 45 minutes"]
    elif any(keyword in lowered for keyword in ("iphone", "phone", "mobile")):
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


async def call_vendor(vendor: VendorInfo, product: str, api_key: str | None = None) -> VoiceCallResult:
    """Trigger an outbound call to a vendor via Bland.ai."""

    effective_key = api_key or settings.bland_ai_api_key
    if settings.mock_voice_calls or not effective_key:
        logger.info("Mock voice call for vendor=%s", vendor.name)
        await asyncio.sleep(random.uniform(0.2, 0.8))
        return VoiceCallResult(
            vendor=vendor,
            call_id=f"mock-call-{uuid.uuid4()}",
            status="completed",
            transcript=_mock_transcript(vendor, product),
            duration_seconds=random.randint(24, 57),
            is_mock=True,
        )

    destination_phone = _call_destination_phone(vendor)
    if settings.test_call_phone.strip():
        logger.info(
            "Triggering Bland.ai test call for vendor=%s via test phone=%s",
            vendor.name,
            destination_phone,
        )
    else:
        logger.info("Triggering Bland.ai call for vendor=%s", vendor.name)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            BLAND_CALLS_URL,
            headers={"Authorization": effective_key, "Content-Type": "application/json"},
            json={
                "phone_number": destination_phone,
                "task": _call_task(vendor, product),
                "voice": "maya",
                "wait_for_greeting": True,
                "record": True,
                "webhook": settings.bland_webhook_url,
                "metadata": {
                    "vendor_name": vendor.name,
                    "product": product,
                    "vendor_phone": vendor.phone,
                    "dialed_phone": destination_phone,
                    "test_call_routing": bool(settings.test_call_phone.strip()),
                },
                "max_duration": 60,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        call_id = payload.get("call_id") or payload.get("id") or f"live-call-{uuid.uuid4()}"
        return VoiceCallResult(vendor=vendor, call_id=call_id, status="busy", is_mock=False)


async def call_all_vendors(vendors: list[VendorInfo], product: str) -> list[VoiceCallResult]:
    """Trigger calls to all vendors concurrently."""

    tasks = [call_vendor(vendor, product) for vendor in vendors]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    completed: list[VoiceCallResult] = []
    for vendor, result in zip(vendors, results, strict=False):
        if isinstance(result, Exception):
            logger.warning("Call initiation failed for %s: %s", vendor.name, result)
            completed.append(
                VoiceCallResult(
                    vendor=vendor,
                    call_id=f"failed-{uuid.uuid4()}",
                    status="failed",
                    transcript=None,
                    is_mock=settings.mock_voice_calls or not settings.bland_ai_api_key,
                )
            )
            continue
        completed.append(result)
    return completed


def _extract_transcript_from_payload(payload: dict) -> str | None:
    transcript = payload.get("concatenated_transcript") or payload.get("transcript")
    if transcript:
        return transcript
    analysis = payload.get("analysis") or {}
    if isinstance(analysis, dict):
        return analysis.get("transcript")
    return None


async def poll_call_result(call: VoiceCallResult, timeout_seconds: int = 120) -> VoiceCallResult:
    if call.is_mock or settings.mock_voice_calls or not settings.bland_ai_api_key:
        return call
    if call.status != "busy":
        return call

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    async with httpx.AsyncClient() as client:
        while asyncio.get_running_loop().time() < deadline:
            response = await client.get(
                f"{BLAND_CALLS_URL}/{call.call_id}",
                headers={"Authorization": settings.bland_ai_api_key},
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            status = payload.get("status", "busy")
            transcript = _extract_transcript_from_payload(payload)
            duration = payload.get("call_length") or payload.get("duration")
            duration_seconds = None
            if isinstance(duration, (int, float)):
                duration_seconds = max(0, int(math.ceil(duration)))
            elif isinstance(duration, str):
                try:
                    duration_seconds = max(0, int(math.ceil(float(duration))))
                except ValueError:
                    duration_seconds = None
            if status == "completed":
                return VoiceCallResult(
                    vendor=call.vendor,
                    call_id=call.call_id,
                    status="completed",
                    transcript=transcript,
                    duration_seconds=duration_seconds,
                    is_mock=False,
                )
            if status in {"failed", "no_answer", "busy"} and not transcript:
                await asyncio.sleep(5)
                continue
            await asyncio.sleep(5)

    logger.warning("Timed out waiting for call %s; falling back to transcript stub.", call.call_id)
    fallback_transcript = call.transcript or _mock_transcript(call.vendor, "the requested product")
    return VoiceCallResult(
        vendor=call.vendor,
        call_id=call.call_id,
        status="completed",
        transcript=fallback_transcript,
        duration_seconds=call.duration_seconds or 60,
        is_mock=True,
    )
