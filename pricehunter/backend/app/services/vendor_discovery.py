from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.models.schemas import VendorInfo

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"


def _queries_for_category(category: str, location: str) -> list[str]:
    category_queries = {
        "groceries": [f"grocery stores near {location}", f"vegetable vendors near {location}"],
        "electronics": [f"electronics shops near {location}", f"mobile phone stores near {location}"],
        "medicine": [f"pharmacies near {location}", f"medical stores near {location}"],
        "hardware": [f"hardware stores near {location}", f"tool shops near {location}"],
        "clothing": [f"clothing stores near {location}", f"garment shops near {location}"],
    }
    return category_queries.get(category, [f"{category} stores near {location}", f"{category} vendors near {location}"])


def _mock_vendors(product: str, category: str, location: str) -> list[VendorInfo]:
    city = location if location and location != "unknown" else "Rajkot"
    seeds = [
        ("Shree Krishna Traders", "+919825001245", f"Yagnik Road, {city}", 4.6),
        ("Patel Brothers Market", "+919723450981", f"Kalawad Road, {city}", 4.4),
        ("Navkar Sales", "+919998112233", f"University Road, {city}", 4.5),
        ("Om Sai Retail", "+919879901122", f"Race Course, {city}", 4.3),
        ("Mahavir Storefront", "+918866554433", f"Amin Marg, {city}", 4.2),
    ]
    return [
        VendorInfo(
            name=name,
            phone=phone,
            address=address,
            rating=rating,
            location={"lat": 22.3039, "lng": 70.8022},
            place_id=f"mock-{index}",
            is_mock=True,
        )
        for index, (name, phone, address, rating) in enumerate(seeds, start=1)
    ]


async def _geocode_location(client: httpx.AsyncClient, location: str) -> tuple[float, float]:
    response = await client.get(
        GEOCODE_URL,
        params={"address": location, "key": settings.google_places_api_key},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    coordinates = payload["results"][0]["geometry"]["location"]
    return coordinates["lat"], coordinates["lng"]


async def _fetch_place_phone(client: httpx.AsyncClient, place_id: str) -> str | None:
    response = await client.get(
        PLACE_DETAILS_URL.format(place_id=place_id),
        headers={
            "X-Goog-Api-Key": settings.google_places_api_key,
            "X-Goog-FieldMask": "nationalPhoneNumber,internationalPhoneNumber",
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("nationalPhoneNumber") or payload.get("internationalPhoneNumber")


async def discover_vendors(product: str, category: str, location: str) -> list[VendorInfo]:
    logger.info("Starting vendor discovery for %s in %s", product, location)
    if not settings.google_places_api_key:
        logger.info("Google Places API key missing; returning mock vendors.")
        return _mock_vendors(product, category, location)

    try:
        async with httpx.AsyncClient() as client:
            lat, lng = await _geocode_location(client, location)
            search_queries = _queries_for_category(category, location)

            candidates: list[VendorInfo] = []
            for query in search_queries:
                response = await client.post(
                    PLACES_SEARCH_URL,
                    headers={
                        "X-Goog-Api-Key": settings.google_places_api_key,
                        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.rating",
                    },
                    json={
                        "textQuery": query,
                        "locationBias": {
                            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": 5000.0}
                        },
                        "maxResultCount": 10,
                    },
                    timeout=25,
                )
                response.raise_for_status()
                payload = response.json()
                for place in payload.get("places", []):
                    place_id = place.get("id")
                    if not place_id:
                        continue
                    phone = await _fetch_place_phone(client, place_id)
                    if not phone:
                        continue
                    candidates.append(
                        VendorInfo(
                            name=place.get("displayName", {}).get("text", "Unknown Vendor"),
                            phone=phone,
                            address=place.get("formattedAddress", "Address unavailable"),
                            location={
                                "lat": place.get("location", {}).get("latitude"),
                                "lng": place.get("location", {}).get("longitude"),
                            },
                            place_id=place_id,
                            rating=place.get("rating"),
                            is_mock=False,
                        )
                    )

            unique: dict[str, VendorInfo] = {vendor.phone: vendor for vendor in candidates}
            vendors = sorted(
                unique.values(),
                key=lambda item: (item.rating or 0, item.name),
                reverse=True,
            )[:10]
            if not vendors:
                raise ValueError("No callable vendors returned by Google Places.")
            logger.info("Vendor discovery completed with %s vendors", len(vendors))
            return vendors
    except Exception as exc:  # pragma: no cover - external integration
        logger.warning("Vendor discovery failed, using mock vendors: %s", exc)
        return _mock_vendors(product, category, location)
