from __future__ import annotations

import abc
import asyncio
import logging
import random
import re
from typing import Iterable

from app.models.schemas import UnifiedResult

logger = logging.getLogger(__name__)


class PlatformAdapter(abc.ABC):
    # TODO: Replace with real API/scraper

    platform_name: str
    platform_id: str
    category_fit: dict[str, float] = {}

    def __init__(self, expected_category: str):
        self.expected_category = expected_category

    @abc.abstractmethod
    async def search(self, query: str) -> list[UnifiedResult]:
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
        query: str,
        price: float,
        delivery_time: str,
        availability: bool = True,
        url: str | None = None,
        notes: str | None = None,
    ) -> UnifiedResult:
        return UnifiedResult(
            source_type="online",
            name=self.platform_name,
            price=round(price, 2),
            delivery_time=delivery_time,
            availability=availability,
            confidence=self._confidence(),
            url=url,
            notes=notes,
            is_mock=True,
        )


class AmazonAdapter(PlatformAdapter):
    # TODO: Replace with real API/scraper

    platform_name = "Amazon India"
    platform_id = "amazon_in"
    category_fit = {"electronics": 0.94, "clothing": 0.88, "hardware": 0.83, "groceries": 0.67}

    async def search(self, query: str) -> list[UnifiedResult]:
        await self._simulate_latency()
        product = self._normalize_product(query)
        return [
            self._build_result(
                query=query,
                price=self._sample_price(query, 1.0),
                delivery_time=random.choice(["Same day", "1 day", "2 days"]),
                url=f"https://amazon.in/s?k={product.replace(' ', '+')}",
                notes=f"{product} via Prime eligible seller",
            ),
            self._build_result(
                query=query,
                price=self._sample_price(query, 0.97),
                delivery_time=random.choice(["1 day", "2 days", "3 days"]),
                availability=random.choice([True, True, False]),
                url=f"https://amazon.in/s?k={product.replace(' ', '+')}",
                notes=f"{product} alternate listing",
            ),
        ]


class FlipkartAdapter(PlatformAdapter):
    # TODO: Replace with real API/scraper

    platform_name = "Flipkart"
    platform_id = "flipkart"
    category_fit = {"electronics": 0.93, "clothing": 0.84, "hardware": 0.8, "groceries": 0.55}

    async def search(self, query: str) -> list[UnifiedResult]:
        await self._simulate_latency()
        product = self._normalize_product(query)
        return [
            self._build_result(
                query=query,
                price=self._sample_price(query, 0.98),
                delivery_time=random.choice(["Same day", "1 day", "2 days"]),
                url=f"https://www.flipkart.com/search?q={product.replace(' ', '%20')}",
                notes=f"{product} assured listing",
            ),
            self._build_result(
                query=query,
                price=self._sample_price(query, 0.96),
                delivery_time=random.choice(["1 day", "2 days", "4 days"]),
                availability=random.choice([True, True, False]),
                url=f"https://www.flipkart.com/search?q={product.replace(' ', '%20')}",
                notes=f"{product} open-box delivery eligible",
            ),
        ]


class BlinkitAdapter(PlatformAdapter):
    # TODO: Replace with real API/scraper

    platform_name = "Blinkit"
    platform_id = "blinkit"
    category_fit = {"groceries": 0.95, "medicine": 0.74}

    async def search(self, query: str) -> list[UnifiedResult]:
        await self._simulate_latency()
        product = self._normalize_product(query)
        base_price = self._sample_price(query, 0.94)
        return [
            self._build_result(
                query=query,
                price=base_price,
                delivery_time=random.choice(["10 mins", "12 mins", "18 mins"]),
                url=f"https://blinkit.com/s/?q={product.replace(' ', '%20')}",
                notes=f"{product} available from nearby dark store",
            )
        ]


class SwiggyInstamartAdapter(PlatformAdapter):
    # TODO: Replace with real API/scraper

    platform_name = "Swiggy Instamart"
    platform_id = "swiggy_instamart"
    category_fit = {"groceries": 0.92, "medicine": 0.7}

    async def search(self, query: str) -> list[UnifiedResult]:
        await self._simulate_latency()
        product = self._normalize_product(query)
        return [
            self._build_result(
                query=query,
                price=self._sample_price(query, 0.92),
                delivery_time=random.choice(["14 mins", "20 mins", "25 mins"]),
                url=f"https://www.swiggy.com/instamart/search?query={product.replace(' ', '%20')}",
                notes=f"{product} from nearby Instamart hub",
            )
        ]


class BigBasketAdapter(PlatformAdapter):
    # TODO: Replace with real API/scraper

    platform_name = "BigBasket"
    platform_id = "bigbasket"
    category_fit = {"groceries": 0.9, "hardware": 0.55}

    async def search(self, query: str) -> list[UnifiedResult]:
        await self._simulate_latency()
        product = self._normalize_product(query)
        return [
            self._build_result(
                query=query,
                price=self._sample_price(query, 0.9),
                delivery_time=random.choice(["45 mins", "2 hours", "Next morning"]),
                url=f"https://www.bigbasket.com/ps/?q={product.replace(' ', '%20')}",
                notes=f"{product} from BigBasket warehouse inventory",
            )
        ]


class CromaAdapter(PlatformAdapter):
    # TODO: Replace with real API/scraper

    platform_name = "Croma"
    platform_id = "croma"
    category_fit = {"electronics": 0.91, "hardware": 0.5}

    async def search(self, query: str) -> list[UnifiedResult]:
        await self._simulate_latency()
        product = self._normalize_product(query)
        return [
            self._build_result(
                query=query,
                price=self._sample_price(query, 1.02),
                delivery_time=random.choice(["2 hours", "Same day", "1 day"]),
                url=f"https://www.croma.com/search/?text={product.replace(' ', '%20')}",
                notes=f"{product} with store pickup option",
            )
        ]


class GenericAdapter(PlatformAdapter):
    # TODO: Replace with real API/scraper

    def __init__(self, platform_name: str, platform_id: str, expected_category: str):
        super().__init__(expected_category)
        self.platform_name = platform_name
        self.platform_id = platform_id

    async def search(self, query: str) -> list[UnifiedResult]:
        await self._simulate_latency()
        product = self._normalize_product(query)
        return [
            self._build_result(
                query=query,
                price=self._sample_price(query, 1.0),
                delivery_time=random.choice(["30 mins", "1 day", "2 days"]),
                url=None,
                notes=f"{product} via {self.platform_name}",
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
