from __future__ import annotations

import logging
import re

from openai import AsyncOpenAI

from app.config import settings
from app.models.schemas import StructuredQuery

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are a query structuring assistant. Convert the user's natural language shopping query into a structured JSON object.

Return ONLY valid JSON with these exact fields:
- "product": the specific item they want (string)
- "category": broad category like "groceries", "electronics", "clothing", "medicine", "hardware" (string)
- "location": the city or area mentioned, or "unknown" if not specified (string)
- "intent": one of "cheapest", "fastest", "best_value", "nearest" — infer from context (string)
- "raw_query": the original query repeated verbatim (string)

Examples:
User: "I need cheap tomatoes in Rajkot"
Output: {"product": "tomatoes", "category": "groceries", "location": "Rajkot", "intent": "cheapest", "raw_query": "I need cheap tomatoes in Rajkot"}

User: "fastest delivery for iPhone 15 pro max"
Output: {"product": "iPhone 15 Pro Max", "category": "electronics", "location": "unknown", "intent": "fastest", "raw_query": "fastest delivery for iPhone 15 pro max"}

Return ONLY the JSON object, no markdown, no explanation.
""".strip()

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "groceries": ("tomato", "potato", "onion", "vegetable", "fruit", "milk", "rice"),
    "electronics": ("iphone", "phone", "laptop", "tv", "tablet", "earbuds", "camera"),
    "clothing": ("shirt", "jeans", "dress", "shoe", "jacket", "kurta"),
    "medicine": ("medicine", "tablet", "capsule", "syrup", "pharmacy", "paracetamol"),
    "hardware": ("drill", "paint", "pipe", "screw", "hammer", "tool"),
}


def _infer_category(raw_query: str) -> str:
    lowered = raw_query.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return "groceries" if any(token in lowered for token in ("kg", "fresh", "near me")) else "electronics"


def _infer_intent(raw_query: str) -> str:
    lowered = raw_query.lower()
    if any(word in lowered for word in ("cheap", "cheapest", "lowest", "budget")):
        return "cheapest"
    if any(word in lowered for word in ("fast", "fastest", "urgent", "quick")):
        return "fastest"
    if any(word in lowered for word in ("near", "nearby", "closest", "nearest")):
        return "nearest"
    return "best_value"


def _infer_location(raw_query: str) -> str:
    if "near me" in raw_query.lower():
        return "near me"
    for trigger in ("in", "near", "at"):
        if f" {trigger} " in raw_query.lower():
            return raw_query.lower().split(f" {trigger} ", 1)[1].strip().title() or "unknown"
    return "unknown"


def _infer_product(raw_query: str) -> str:
    location_stripped = re.split(r"\b(?:near me|near|in|at)\b", raw_query, maxsplit=1, flags=re.IGNORECASE)[0]
    cleaned = re.sub(
        r"\b(cheapest|cheap|fastest|best|best value|near|near me|in|find|get|need|buy|delivery|for)\b",
        "",
        location_stripped,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
    return cleaned or raw_query.strip()


def _best_effort_structure(raw_query: str) -> StructuredQuery:
    return StructuredQuery(
        product=_infer_product(raw_query),
        category=_infer_category(raw_query),
        location=_infer_location(raw_query),
        intent=_infer_intent(raw_query),
        raw_query=raw_query,
    )


async def structure_query(raw_query: str) -> StructuredQuery:
    logger.info("Structuring query: %s", raw_query)
    if not settings.openai_api_key:
        logger.info("OpenAI API key missing; using heuristic query structurer.")
        return _best_effort_structure(raw_query)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    last_error: Exception | None = None

    for attempt in range(2):
        try:
            response = await client.responses.parse(
                model=settings.openai_model,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": raw_query},
                ],
                text_format=StructuredQuery,
                temperature=0,
            )
            structured = response.output_parsed
            if structured is None:
                raise ValueError("OpenAI returned no parsed StructuredQuery.")
            structured.raw_query = raw_query
            logger.info("Structured query generated successfully on attempt %s", attempt + 1)
            return structured
        except Exception as exc:  # pragma: no cover - depends on external API
            last_error = exc
            logger.warning("Query structurer failed on attempt %s: %s", attempt + 1, exc)

    logger.warning("Falling back to heuristic query structurer after error: %s", last_error)
    return _best_effort_structure(raw_query)
