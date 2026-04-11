from __future__ import annotations

import json
import logging
import re

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from app.config import settings
from app.models.schemas import StructuredQuery

logger = logging.getLogger(__name__)

MODEL_NAME = "claude-sonnet-4-20250514"
SYSTEM_PROMPT = """
You are an e-commerce platform selection assistant for India.
Given a structured shopping query, pick the most relevant Indian e-commerce platforms and return ONLY valid JSON.

Supported platforms include:
- amazon_in
- flipkart
- jiomart
- bigbasket
- blinkit
- swiggy_instamart
- zepto
- croma
- reliance_digital
- meesho

Pick 3 to 5 platforms based on the product category. Groceries should favor quick-commerce and grocery platforms. Electronics should favor Amazon India, Flipkart, Croma, and Reliance Digital. Clothing should favor Amazon India, Flipkart, and Meesho.

Return JSON with this exact shape:
{
  "platforms": [
    {
      "platform_name": "Amazon India",
      "platform_id": "amazon_in",
      "search_query": "iPhone 15 Pro Max",
      "expected_category": "electronics"
    }
  ]
}
""".strip()


class PlatformStrategy(BaseModel):
    platform_name: str
    platform_id: str
    search_query: str
    expected_category: str


class DiscoveryResponse(BaseModel):
    platforms: list[PlatformStrategy]


def _extract_json_block(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text


def _fallback_platforms(query: StructuredQuery) -> DiscoveryResponse:
    category_map: dict[str, list[tuple[str, str]]] = {
        "groceries": [
            ("Blinkit", "blinkit"),
            ("Swiggy Instamart", "swiggy_instamart"),
            ("BigBasket", "bigbasket"),
            ("JioMart", "jiomart"),
            ("Amazon India", "amazon_in"),
        ],
        "electronics": [
            ("Amazon India", "amazon_in"),
            ("Flipkart", "flipkart"),
            ("Croma", "croma"),
            ("Reliance Digital", "reliance_digital"),
        ],
        "clothing": [
            ("Flipkart", "flipkart"),
            ("Amazon India", "amazon_in"),
            ("Meesho", "meesho"),
        ],
        "medicine": [
            ("Blinkit", "blinkit"),
            ("Swiggy Instamart", "swiggy_instamart"),
            ("Amazon India", "amazon_in"),
        ],
        "hardware": [
            ("Amazon India", "amazon_in"),
            ("Flipkart", "flipkart"),
            ("JioMart", "jiomart"),
        ],
    }
    selected = category_map.get(query.category, category_map["electronics"])
    return DiscoveryResponse(
        platforms=[
            PlatformStrategy(
                platform_name=name,
                platform_id=platform_id,
                search_query=query.product,
                expected_category=query.category,
            )
            for name, platform_id in selected
        ]
    )


async def discover_platforms(query: StructuredQuery) -> list[PlatformStrategy]:
    logger.info("Discovering platforms for category=%s product=%s", query.category, query.product)
    if not settings.anthropic_api_key:
        logger.info("Anthropic API key missing; using fallback platform selection.")
        return _fallback_platforms(query).platforms

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    try:
        response = await client.messages.create(
            model=MODEL_NAME,
            system=SYSTEM_PROMPT,
            max_tokens=512,
            temperature=0,
            messages=[{"role": "user", "content": query.model_dump_json()}],
        )
        payload = "\n".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        parsed = DiscoveryResponse.model_validate(json.loads(_extract_json_block(payload)))
        if not parsed.platforms:
            raise ValueError("No platforms returned by LLM.")
        return parsed.platforms
    except Exception as exc:  # pragma: no cover - depends on external API
        logger.warning("Online discovery failed, using fallback platforms: %s", exc)
        return _fallback_platforms(query).platforms
