from __future__ import annotations

import logging
import re

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.config import settings
from app.models.schemas import UnifiedResult, VendorInfo, VoiceCallResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are a data extraction assistant. Given a phone call transcript between an AI agent and a shop vendor, extract the following information as JSON:

- "price": the price quoted (number, in INR, null if not mentioned)
- "availability": whether the product is in stock (boolean)
- "negotiated": whether any discount was offered or negotiated (boolean)
- "delivery_time": any delivery or pickup time mentioned (string, null if not mentioned)
- "notes": any other relevant details like brand, condition, warranty mentioned (string)
- "confidence": how confident you are in the extracted data from 0.0 to 1.0 (number)

Return ONLY valid JSON, no markdown, no explanation.
""".strip()


class TranscriptExtraction(BaseModel):
    price: float | None = None
    availability: bool = True
    negotiated: bool = False
    delivery_time: str | None = None
    notes: str | None = None
    confidence: float = 0.6


def _coerce_bool(value: object, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "in stock", "available"}:
            return True
        if normalized in {"false", "no", "out of stock", "unavailable"}:
            return False
    return default


def _coerce_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = re.sub(r"[^\d.]", "", value)
        if normalized:
            try:
                return float(normalized)
            except ValueError:
                return None
    return None


def extract_from_structured_data(
    extracted_data: dict,
    vendor: VendorInfo,
    product: str,
) -> UnifiedResult:
    price = _coerce_float(extracted_data.get("price"))
    availability = _coerce_bool(extracted_data.get("availability"), default=True)
    negotiated = _coerce_bool(extracted_data.get("negotiated"), default=False)
    delivery_time = extracted_data.get("delivery_time")
    if delivery_time is not None:
        delivery_time = str(delivery_time)
    notes = extracted_data.get("notes")
    if notes is not None:
        notes = str(notes)
    confidence = _coerce_float(extracted_data.get("confidence")) or 0.74

    resolved_notes = notes or f"Asked about {product} via phone inquiry."
    if vendor.is_mock:
        resolved_notes = f"{resolved_notes} Demo vendor discovery data."

    return UnifiedResult(
        source_type="offline",
        name=vendor.name,
        price=price,
        delivery_time=delivery_time,
        availability=availability,
        negotiated=negotiated,
        confidence=max(0.0, min(confidence, 1.0)),
        phone=vendor.phone,
        address=vendor.address,
        notes=resolved_notes,
        is_mock=vendor.is_mock,
    )


def _fallback_extract(transcript: str) -> TranscriptExtraction:
    price_match = re.search(r"(\d[\d,]*)\s*rupees?", transcript, re.IGNORECASE)
    availability = not any(
        phrase in transcript.lower() for phrase in ("out of stock", "not available", "no stock")
    )
    negotiated = any(
        phrase in transcript.lower()
        for phrase in ("discount", "reduce it", "best price", "offer", "lower it")
    )
    delivery_match = re.search(
        r"(pickup in \d+\s*(?:minutes|mins)|delivery in \d+\s*(?:minutes|mins)|same-day delivery)",
        transcript,
        re.IGNORECASE,
    )
    notes = None
    if "limited stock" in transcript.lower():
        notes = "Vendor mentioned limited stock."
    return TranscriptExtraction(
        price=float(price_match.group(1).replace(",", "")) if price_match else None,
        availability=availability,
        negotiated=negotiated,
        delivery_time=delivery_match.group(1) if delivery_match else None,
        notes=notes,
        confidence=0.72 if price_match else 0.55,
    )


async def extract_from_transcript(transcript: str, vendor: VendorInfo, product: str) -> UnifiedResult:
    logger.info("Extracting structured data from transcript for vendor=%s", vendor.name)
    extraction: TranscriptExtraction

    if not settings.openai_api_key:
        extraction = _fallback_extract(transcript)
    else:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        try:
            response = await client.responses.parse(
                model=settings.openai_model,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": transcript},
                ],
                text_format=TranscriptExtraction,
                temperature=0,
            )
            extraction = response.output_parsed
            if extraction is None:
                raise ValueError("OpenAI returned no parsed transcript extraction.")
        except Exception as exc:  # pragma: no cover - depends on external API
            logger.warning("Voice extraction failed, using fallback parser: %s", exc)
            extraction = _fallback_extract(transcript)

    notes = extraction.notes or f"Asked about {product} via phone inquiry."
    if vendor.is_mock:
        notes = f"{notes} Demo vendor discovery data."

    return UnifiedResult(
        source_type="offline",
        name=vendor.name,
        price=extraction.price,
        delivery_time=extraction.delivery_time,
        availability=extraction.availability,
        negotiated=extraction.negotiated,
        confidence=extraction.confidence,
        phone=vendor.phone,
        address=vendor.address,
        notes=notes,
        is_mock=vendor.is_mock,
    )


async def extract_from_call_result(call: VoiceCallResult, product: str) -> UnifiedResult:
    if call.extracted_data:
        try:
            return extract_from_structured_data(call.extracted_data, call.vendor, product)
        except Exception as exc:  # pragma: no cover - provider payload variability
            logger.warning("Structured voice extraction failed, falling back to transcript parser: %s", exc)

    transcript = call.transcript or ""
    return await extract_from_transcript(transcript, call.vendor, product)
