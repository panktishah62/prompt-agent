from __future__ import annotations

import json
import logging
import re

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from app.config import settings
from app.models.schemas import UnifiedResult, VendorInfo

logger = logging.getLogger(__name__)

MODEL_NAME = "claude-sonnet-4-20250514"
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


def _extract_json_block(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text


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

    if not settings.anthropic_api_key:
        extraction = _fallback_extract(transcript)
    else:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        try:
            response = await client.messages.create(
                model=MODEL_NAME,
                system=SYSTEM_PROMPT,
                max_tokens=256,
                temperature=0,
                messages=[{"role": "user", "content": transcript}],
            )
            payload = "\n".join(
                block.text for block in response.content if getattr(block, "type", "") == "text"
            ).strip()
            extraction = TranscriptExtraction.model_validate(json.loads(_extract_json_block(payload)))
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
