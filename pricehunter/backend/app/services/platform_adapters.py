from __future__ import annotations

import abc
import asyncio
import logging
import random
import re
from typing import Any, Iterable

import httpx

from app.config import settings
from app.models.schemas import UnifiedResult

logger = logging.getLogger(__name__)

SERPAPI_TIMEOUT_SECONDS = 30
LIVE_RESULTS_PER_PLATFORM = 2
SHOPPING_TIME_PATTERN = re.compile(
    r"(\d+\s*(?:mins?|minutes|hours?|days?)|\d+\s*-\s*\d+\s*(?:mins?|minutes|hours?|days?)|same day|next morning|pickup)",
    re.IGNORECASE,
)


class PlatformAdapter(abc.ABC):
    # TODO: Replace with real API/scraper

    platform_name: str
    platform_id: str
    category_fit: dict[str, float] = {}
    source_aliases: tuple[str, ...] = ()
    platform_domains: tuple[str, ...] = ()

    def __init__(self, expected_category: str):
        self.expected_category = expected_category

    async def search(self, query: str, location: str | None = None) -> list[UnifiedResult]:
        if settings.serpapi_api_key:
            try:
                live_results = await self._search_live(query, location)
                if live_results:
                    logger.info(
                        "Live pricing returned %s result(s) for %s",
                        len(live_results),
                        self.platform_id,
                    )
                    return live_results
                logger.warning(
                    "Live pricing returned no usable matches for %s; using mock fallback.",
                    self.platform_id,
                )
            except Exception as exc:  # pragma: no cover - external dependency
                logger.warning(
                    "Live pricing failed for %s: %s. Falling back to mock results.",
                    self.platform_id,
                    exc,
                )

        await self._simulate_latency()
        return self._search_mock(query)

    @abc.abstractmethod
    def _search_mock(self, query: str) -> list[UnifiedResult]:
        raise NotImplementedError

    def _confidence(self) -> float:
        return self.category_fit.get(self.expected_category, 0.58)

    async def _simulate_latency(self) -> None:
        await asyncio.sleep(random.uniform(0.5, 2.0))

    def _normalize_product(self, query: str) -> str:
        return re.sub(r"\s+", " ", query).strip().title()

    def _price_range(self, query: str) -> tuple[float, float]:
        lowered = query.lower()
        if self.expected_category == "groceries":
            return (20, 280)
        if self.expected_category == "medicine":
            return (60, 1800)
        if self.expected_category == "clothing":
            return (399, 4999)
        if self.expected_category == "hardware":
            return (150, 6500)
        if any(keyword in lowered for keyword in ("iphone", "phone", "mobile")):
            return (54999, 89999)
        if any(keyword in lowered for keyword in ("laptop", "macbook")):
            return (34999, 149999)
        if any(keyword in lowered for keyword in ("tv", "television")):
            return (12999, 99999)
        if any(keyword in lowered for keyword in ("earbuds", "headphone", "speaker")):
            return (999, 24999)
        return (899, 59999)

    def _sample_price(self, query: str, variance: float = 1.0) -> float:
        minimum, maximum = self._price_range(query)
        midpoint = random.uniform(minimum, maximum)
        return round(midpoint * variance, 2)

    def _build_result(
        self,
        *,
        price: float | None,
        delivery_time: str | None,
        availability: bool = True,
        url: str | None = None,
        notes: str | None = None,
        is_mock: bool,
        confidence: float | None = None,
    ) -> UnifiedResult:
        return UnifiedResult(
            source_type="online",
            name=self.platform_name,
            price=round(price, 2) if price is not None else None,
            delivery_time=delivery_time,
            availability=availability,
            confidence=confidence if confidence is not None else self._confidence(),
            url=url,
            notes=notes,
            is_mock=is_mock,
        )

    async def _search_live(self, query: str, location: str | None) -> list[UnifiedResult]:
        search_queries = [query.strip()]
        if self.platform_name.lower() not in query.lower():
            search_queries.append(f"{query} {self.platform_name}")

        ranked_candidates: list[tuple[float, UnifiedResult]] = []
        seen_urls: set[str] = set()

        async with httpx.AsyncClient() as client:
            for search_query in search_queries:
                response = await client.get(
                    settings.serpapi_base_url,
                    params={
                        "engine": "google_shopping",
                        "api_key": settings.serpapi_api_key,
                        "q": search_query,
                        "google_domain": "google.co.in",
                        "gl": "in",
                        "hl": "en",
                        "location": location or "India",
                        "no_cache": "true",
                    },
                    timeout=SERPAPI_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                payload = response.json()
                for score, result in self._extract_live_candidates(payload, query):
                    dedupe_key = result.url or f"{result.name}:{result.price}:{result.delivery_time}"
                    if dedupe_key in seen_urls:
                        continue
                    seen_urls.add(dedupe_key)
                    ranked_candidates.append((score, result))
                if len(ranked_candidates) >= LIVE_RESULTS_PER_PLATFORM:
                    break

        ranked_candidates.sort(key=lambda item: item[0], reverse=True)
        return [result for _, result in ranked_candidates[:LIVE_RESULTS_PER_PLATFORM]]

    def _extract_live_candidates(
        self,
        payload: dict[str, Any],
        query: str,
    ) -> list[tuple[float, UnifiedResult]]:
        results: list[tuple[float, UnifiedResult]] = []
        for item in payload.get("shopping_results", []):
            if not isinstance(item, dict) or not self._matches_platform(item):
                continue

            price = self._extract_price(item)
            if price is None:
                continue

            title = str(item.get("title", "")).strip()
            delivery_time = self._extract_delivery_time(item)
            availability = self._extract_availability(item)
            notes = self._build_live_notes(item)
            confidence = self._live_confidence(item, query)
            result = self._build_result(
                price=price,
                delivery_time=delivery_time,
                availability=availability,
                url=self._extract_url(item),
                notes=notes,
                is_mock=False,
                confidence=confidence,
            )
            results.append((self._candidate_score(item, query, confidence), result))

        return results

    def _candidate_score(self, item: dict[str, Any], query: str, confidence: float) -> float:
        title = str(item.get("title", "")).lower()
        query_tokens = self._query_tokens(query)
        title_hits = sum(1 for token in query_tokens if token in title)
        score = confidence * 10 + title_hits * 1.5
        if self._extract_delivery_time(item):
            score += 0.4
        if self._extract_url(item):
            score += 0.2
        return score

    def _matches_platform(self, item: dict[str, Any]) -> bool:
        aliases = {self._normalize_source(alias) for alias in self.source_aliases or (self.platform_name,)}
        domains = tuple(domain.lower() for domain in self.platform_domains)

        source_candidates = [
            item.get("source"),
            item.get("seller"),
            item.get("merchant"),
            item.get("store"),
        ]
        source_candidates.extend(self._flatten_strings(item.get("stores")))
        source_candidates.extend(self._flatten_strings(item.get("extensions")))

        normalized_candidates = [self._normalize_source(value) for value in source_candidates if value]
        if any(candidate and any(alias in candidate for alias in aliases) for candidate in normalized_candidates):
            return True

        url = (self._extract_url(item) or "").lower()
        return any(domain in url for domain in domains)

    def _live_confidence(self, item: dict[str, Any], query: str) -> float:
        confidence = self._confidence() + 0.08
        title = str(item.get("title", "")).lower()
        title_hits = sum(1 for token in self._query_tokens(query) if token in title)
        confidence += min(title_hits * 0.03, 0.12)
        if self._extract_delivery_time(item):
            confidence += 0.03
        return min(round(confidence, 2), 0.99)

    def _build_live_notes(self, item: dict[str, Any]) -> str | None:
        fragments: list[str] = []
        title = str(item.get("title", "")).strip()
        source = str(item.get("source", "")).strip()
        rating = item.get("rating")
        reviews = item.get("reviews")
        snippet = str(item.get("snippet", "")).strip()

        if title:
            fragments.append(title)
        if source and source.lower() != self.platform_name.lower():
            fragments.append(f"Source: {source}")
        if rating:
            fragments.append(f"Rating: {rating}")
        if reviews:
            fragments.append(f"Reviews: {reviews}")
        if snippet:
            fragments.append(snippet)
        return " | ".join(fragments) if fragments else None

    def _extract_delivery_time(self, item: dict[str, Any]) -> str | None:
        for key in ("delivery", "shipping"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        for candidate in self._flatten_strings(item.get("extensions")):
            match = SHOPPING_TIME_PATTERN.search(candidate)
            if match:
                return match.group(1)
        return None

    def _extract_availability(self, item: dict[str, Any]) -> bool:
        haystack = " ".join(
            self._flatten_strings(
                [
                    item.get("title"),
                    item.get("snippet"),
                    item.get("delivery"),
                    item.get("shipping"),
                    item.get("tag"),
                    item.get("availability"),
                    item.get("extensions"),
                ]
            )
        ).lower()
        unavailable_markers = ("out of stock", "unavailable", "sold out", "currently unavailable")
        return not any(marker in haystack for marker in unavailable_markers)

    def _extract_url(self, item: dict[str, Any]) -> str | None:
        for key in ("link", "product_link", "serpapi_link"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _extract_price(self, item: dict[str, Any]) -> float | None:
        for key in ("extracted_price", "price"):
            value = item.get(key)
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                match = re.search(r"([\d,]+(?:\.\d+)?)", value)
                if match:
                    return float(match.group(1).replace(",", ""))
        return None

    def _query_tokens(self, query: str) -> list[str]:
        stop_words = {
            "the",
            "for",
            "and",
            "with",
            "price",
            "buy",
            "best",
            "cheap",
            "cheapest",
            "near",
            "delivery",
        }
        return [
            token
            for token in re.findall(r"[a-z0-9]+", query.lower())
            if len(token) > 1 and token not in stop_words
        ]

    def _normalize_source(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    def _flatten_strings(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            flattened: list[str] = []
            for nested in value.values():
                flattened.extend(self._flatten_strings(nested))
            return flattened
        if isinstance(value, (list, tuple, set)):
            flattened = []
            for item in value:
                flattened.extend(self._flatten_strings(item))
            return flattened
        return [str(value)]


class AmazonAdapter(PlatformAdapter):
    # TODO: Replace with real API/scraper

    platform_name = "Amazon India"
    platform_id = "amazon_in"
    category_fit = {"electronics": 0.94, "clothing": 0.88, "hardware": 0.83, "groceries": 0.67}
    source_aliases = ("amazon", "amazon india")
    platform_domains = ("amazon.in", "amazon.com")

    def _search_mock(self, query: str) -> list[UnifiedResult]:
        product = self._normalize_product(query)
        return [
            self._build_result(
                price=self._sample_price(query, 1.0),
                delivery_time=random.choice(["Same day", "1 day", "2 days"]),
                url=f"https://amazon.in/s?k={product.replace(' ', '+')}",
                notes=f"{product} via Prime eligible seller",
                is_mock=True,
            ),
            self._build_result(
                price=self._sample_price(query, 0.97),
                delivery_time=random.choice(["1 day", "2 days", "3 days"]),
                availability=random.choice([True, True, False]),
                url=f"https://amazon.in/s?k={product.replace(' ', '+')}",
                notes=f"{product} alternate listing",
                is_mock=True,
            ),
        ]


class FlipkartAdapter(PlatformAdapter):
    # TODO: Replace with real API/scraper

    platform_name = "Flipkart"
    platform_id = "flipkart"
    category_fit = {"electronics": 0.93, "clothing": 0.84, "hardware": 0.8, "groceries": 0.55}
    source_aliases = ("flipkart",)
    platform_domains = ("flipkart.com",)

    def _search_mock(self, query: str) -> list[UnifiedResult]:
        product = self._normalize_product(query)
        return [
            self._build_result(
                price=self._sample_price(query, 0.98),
                delivery_time=random.choice(["Same day", "1 day", "2 days"]),
                url=f"https://www.flipkart.com/search?q={product.replace(' ', '%20')}",
                notes=f"{product} assured listing",
                is_mock=True,
            ),
            self._build_result(
                price=self._sample_price(query, 0.96),
                delivery_time=random.choice(["1 day", "2 days", "4 days"]),
                availability=random.choice([True, True, False]),
                url=f"https://www.flipkart.com/search?q={product.replace(' ', '%20')}",
                notes=f"{product} open-box delivery eligible",
                is_mock=True,
            ),
        ]


class BlinkitAdapter(PlatformAdapter):
    # TODO: Replace with real API/scraper

    platform_name = "Blinkit"
    platform_id = "blinkit"
    category_fit = {"groceries": 0.95, "medicine": 0.74}
    source_aliases = ("blinkit",)
    platform_domains = ("blinkit.com",)

    def _search_mock(self, query: str) -> list[UnifiedResult]:
        product = self._normalize_product(query)
        return [
            self._build_result(
                price=self._sample_price(query, 0.94),
                delivery_time=random.choice(["10 mins", "12 mins", "18 mins"]),
                url=f"https://blinkit.com/s/?q={product.replace(' ', '%20')}",
                notes=f"{product} available from nearby dark store",
                is_mock=True,
            )
        ]


class SwiggyInstamartAdapter(PlatformAdapter):
    # TODO: Replace with real API/scraper

    platform_name = "Swiggy Instamart"
    platform_id = "swiggy_instamart"
    category_fit = {"groceries": 0.92, "medicine": 0.7}
    source_aliases = ("swiggy instamart", "instamart", "swiggy")
    platform_domains = ("swiggy.com",)

    def _search_mock(self, query: str) -> list[UnifiedResult]:
        product = self._normalize_product(query)
        return [
            self._build_result(
                price=self._sample_price(query, 0.92),
                delivery_time=random.choice(["14 mins", "20 mins", "25 mins"]),
                url=f"https://www.swiggy.com/instamart/search?query={product.replace(' ', '%20')}",
                notes=f"{product} from nearby Instamart hub",
                is_mock=True,
            )
        ]


class BigBasketAdapter(PlatformAdapter):
    # TODO: Replace with real API/scraper

    platform_name = "BigBasket"
    platform_id = "bigbasket"
    category_fit = {"groceries": 0.9, "hardware": 0.55}
    source_aliases = ("bigbasket", "bbnow")
    platform_domains = ("bigbasket.com",)

    def _search_mock(self, query: str) -> list[UnifiedResult]:
        product = self._normalize_product(query)
        return [
            self._build_result(
                price=self._sample_price(query, 0.9),
                delivery_time=random.choice(["45 mins", "2 hours", "Next morning"]),
                url=f"https://www.bigbasket.com/ps/?q={product.replace(' ', '%20')}",
                notes=f"{product} from BigBasket warehouse inventory",
                is_mock=True,
            )
        ]


class CromaAdapter(PlatformAdapter):
    # TODO: Replace with real API/scraper

    platform_name = "Croma"
    platform_id = "croma"
    category_fit = {"electronics": 0.91, "hardware": 0.5}
    source_aliases = ("croma",)
    platform_domains = ("croma.com",)

    def _search_mock(self, query: str) -> list[UnifiedResult]:
        product = self._normalize_product(query)
        return [
            self._build_result(
                price=self._sample_price(query, 1.02),
                delivery_time=random.choice(["2 hours", "Same day", "1 day"]),
                url=f"https://www.croma.com/search/?text={product.replace(' ', '%20')}",
                notes=f"{product} with store pickup option",
                is_mock=True,
            )
        ]


class GenericAdapter(PlatformAdapter):
    # TODO: Replace with real API/scraper

    def __init__(self, platform_name: str, platform_id: str, expected_category: str):
        super().__init__(expected_category)
        self.platform_name = platform_name
        self.platform_id = platform_id
        self.source_aliases = (platform_name, platform_id.replace("_", " "))
        self.platform_domains = ()

    def _search_mock(self, query: str) -> list[UnifiedResult]:
        product = self._normalize_product(query)
        return [
            self._build_result(
                price=self._sample_price(query, 1.0),
                delivery_time=random.choice(["30 mins", "1 day", "2 days"]),
                url=None,
                notes=f"{product} via {self.platform_name}",
                is_mock=True,
            )
        ]


ADAPTER_REGISTRY = {
    "amazon_in": AmazonAdapter,
    "flipkart": FlipkartAdapter,
    "blinkit": BlinkitAdapter,
    "swiggy_instamart": SwiggyInstamartAdapter,
    "bigbasket": BigBasketAdapter,
    "croma": CromaAdapter,
}


def get_adapters(platform_ids: Iterable[str], expected_category: str) -> list[PlatformAdapter]:
    adapters: list[PlatformAdapter] = []
    for platform_id in platform_ids:
        adapter_class = ADAPTER_REGISTRY.get(platform_id)
        if adapter_class:
            adapters.append(adapter_class(expected_category))
            continue
        prettified_name = platform_id.replace("_", " ").title()
        adapters.append(GenericAdapter(prettified_name, platform_id, expected_category))
    logger.info("Prepared %s platform adapters.", len(adapters))
    return adapters
