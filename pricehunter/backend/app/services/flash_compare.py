from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.config import settings
from app.models.schemas import StructuredQuery, UnifiedResult
from app.services.browser_use_client import BrowserUseClient, BrowserUseError, classify_browser_error
from app.services.flash_price_parser import FlashPriceEntry, parse_flash_store_rows
from app.services.online_discovery import PlatformStrategy


logger = logging.getLogger(__name__)

FLASH_ROUTE_RE = re.compile(r"https://flash\.co/(?:product-details|item)/[^?#]+")
FLASH_COMPARE_ROUTE_RE = re.compile(r"https://flash\.co/(?:product-compare|price-compare)/[^?#]+")
VIEW_ALL_STORES_RE = re.compile(r"View all\s+\d+\s+stores", re.IGNORECASE)


@dataclass(frozen=True)
class FlipkartSeed:
    title: str
    url: str
    score: int


class FlashCompareError(RuntimeError):
    def __init__(self, message: str, *, code: str = "flash_compare_error") -> None:
        super().__init__(message)
        self.code = code


async def search_flash_compare(query: StructuredQuery) -> list[UnifiedResult]:
    if not settings.flash_compare_enabled:
        return []
    if not settings.browser_use_api_key:
        logger.info("Flash compare disabled because BROWSER_USE_API_KEY is missing.")
        return []
    if not settings.serpapi_api_key:
        logger.info("Flash compare disabled because SERPAPI_API_KEY is missing.")
        return []
    enabled_categories = {
        category.strip().lower()
        for category in settings.flash_compare_categories.split(",")
        if category.strip()
    }
    if query.category.lower() not in enabled_categories:
        logger.info("Flash compare skipped for category=%s", query.category)
        return []

    seed = await discover_flipkart_seed(query.product)
    if not seed:
        logger.info("Flash compare could not find a Flipkart seed URL for %s", query.product)
        return []

    last_error: Exception | None = None
    attempts = max(1, settings.browser_use_retry_attempts)
    for attempt in range(1, attempts + 1):
        try:
            logger.info("Flash compare Browser Use attempt %s/%s", attempt, attempts)
            entries, metadata = await _run_flash_browser(seed.url)
            return [_to_unified_result(entry, seed, metadata) for entry in entries]
        except Exception as exc:  # pragma: no cover - external provider
            last_error = exc
            logger.warning("Flash compare attempt %s/%s failed: %s", attempt, attempts, exc)
            if attempt < attempts:
                await asyncio.sleep(min(2 * attempt, 8))

    if last_error:
        logger.warning("Flash compare failed after %s attempts: %s", attempts, last_error)
    return []


async def discover_flipkart_seed(product: str) -> FlipkartSeed | None:
    params = {
        "engine": "google",
        "api_key": settings.serpapi_api_key,
        "q": f"site:flipkart.com {product}",
        "google_domain": "google.co.in",
        "gl": "in",
        "hl": "en",
        "location": "India",
        "num": 10,
    }
    async with httpx.AsyncClient(timeout=settings.flash_serpapi_timeout_seconds) as client:
        response = await client.get(settings.serpapi_base_url, params=params)
    response.raise_for_status()
    payload = response.json()

    candidates: list[FlipkartSeed] = []
    for item in payload.get("organic_results", []):
        if not isinstance(item, dict):
            continue
        url = str(item.get("link") or "").strip()
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if "flipkart.com" not in url:
            continue
        score = _score_flipkart_candidate(product, title, url, snippet)
        if score <= 0:
            continue
        candidates.append(FlipkartSeed(title=title, url=url, score=score))

    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    return candidates[0] if candidates else None


async def _run_flash_browser(flipkart_url: str) -> tuple[list[FlashPriceEntry], dict[str, Any]]:
    client = BrowserUseClient()
    session: dict[str, Any] | None = None
    session_id: str | None = None
    browser = None
    flash_url = f"https://flash.co/{flipkart_url}"

    try:
        session = await client.create_session()
        session_id = session.get("id")
        logger.info("Browser Use session created: id=%s live=%s", session_id, session.get("liveUrl"))

        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect_over_cdp(session["cdpUrl"])
            context = browser.contexts[0] if browser.contexts else await browser.new_context(locale="en-IN")
            page = context.pages[0] if context.pages else await context.new_page()
            page.set_default_timeout(settings.flash_browser_timeout_ms)

            await page.goto(flash_url, wait_until="domcontentloaded", timeout=settings.flash_browser_timeout_ms)
            await page.wait_for_url(FLASH_ROUTE_RE, timeout=settings.flash_browser_timeout_ms)
            await page.wait_for_load_state("networkidle")
            summary_url = page.url

            view_all_button = page.locator("button").filter(has_text=VIEW_ALL_STORES_RE).first
            await view_all_button.wait_for(state="visible", timeout=settings.flash_browser_timeout_ms)
            await view_all_button.click()

            await page.wait_for_url(FLASH_COMPARE_ROUTE_RE, timeout=settings.flash_browser_timeout_ms)
            await page.wait_for_load_state("networkidle")
            compare_url = page.url
            await page.wait_for_timeout(1000)

            rows = await page.evaluate(
                """
                () => Array.from(document.querySelectorAll('a')).map((link) => ({
                  text: (link.innerText || '').replace(/\\s+/g, ' ').trim(),
                  href: link.href || null,
                })).filter((row) => /₹\\s*[0-9][0-9,]*/.test(row.text))
                """
            )
            await browser.close()
            browser = None
    except (PlaywrightTimeoutError, BrowserUseError) as exc:
        code = getattr(exc, "code", None) or classify_browser_error(exc)
        raise FlashCompareError(str(exc), code=code) from exc
    except Exception as exc:
        raise FlashCompareError(str(exc), code=classify_browser_error(exc)) from exc
    finally:
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass
        if session_id:
            stop_metadata = await client.stop_session(session_id)
            if stop_metadata:
                logger.info(
                    "Browser Use session stopped: id=%s proxyUsedMb=%s proxyCost=%s browserCost=%s",
                    session_id,
                    stop_metadata.get("proxyUsedMb"),
                    stop_metadata.get("proxyCost"),
                    stop_metadata.get("browserCost"),
                )

    entries = parse_flash_store_rows(rows)
    if not entries:
        raise FlashCompareError("Flash compare returned no merchant rows", code="no_compare_results")
    metadata = {
        "flash_url": flash_url,
        "summary_url": summary_url,
        "compare_url": compare_url,
        "browser_use_session_id": session_id,
        "browser_use_proxy_country": settings.browser_use_proxy_country,
    }
    return entries, metadata


def _to_unified_result(entry: FlashPriceEntry, seed: FlipkartSeed, metadata: dict[str, Any]) -> UnifiedResult:
    notes = (
        f"Flash compare via Flipkart seed: {seed.title}. "
        f"Compare URL: {metadata.get('compare_url')}"
    )
    return UnifiedResult(
        source_type="online",
        name=entry.site,
        price=entry.price,
        currency="INR",
        delivery_time=None,
        availability=True,
        confidence=0.86,
        url=entry.url,
        notes=notes,
        is_mock=False,
    )


def _score_flipkart_candidate(product: str, title: str, url: str, snippet: str) -> int:
    lowered_title = title.lower()
    lowered_url = url.lower()
    lowered_snippet = snippet.lower()
    product_tokens = [token for token in re.findall(r"[a-z0-9]+", product.lower()) if len(token) > 1]

    score = 0
    if "/p/" in lowered_url:
        score += 8
    if "/search" in lowered_url:
        score -= 5
    if "flipkart.com" in lowered_url:
        score += 3
    for token in product_tokens:
        if token in lowered_title:
            score += 3
        elif token in lowered_url or token in lowered_snippet:
            score += 1
    if any(bad in lowered_title for bad in ("case", "cover", "tempered glass", "charger")):
        score -= 5
    return score


def flash_platform_strategy() -> PlatformStrategy:
    return PlatformStrategy(
        platform_name="Flash Compare",
        platform_id="flash_compare",
        search_query="flash compare",
        expected_category="electronics",
    )
