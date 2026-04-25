from __future__ import annotations

import logging

import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING

from app.config import settings

logger = logging.getLogger(__name__)

client = AsyncIOMotorClient(
    settings.mongodb_url,
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=5000,
    retryWrites=True,
)
db = client[settings.database_name]

search_sessions_collection = db["search_sessions"]
call_attempts_collection = db["call_attempts"]
online_results_collection = db["online_results"]
vendor_profiles_collection = db["vendor_profiles"]
product_catalog_collection = db["product_catalog"]
vendor_product_observations_collection = db["vendor_product_observations"]
price_history_collection = db["price_history"]
raw_webhooks_collection = db["raw_webhooks"]

# Legacy aliases kept so older code paths do not break while persistence is migrated.
queries_collection = search_sessions_collection
results_collection = db["results"]
vendors_collection = vendor_profiles_collection


async def init_database() -> None:
    try:
        await search_sessions_collection.create_index([("search_id", ASCENDING)], unique=True)
        await search_sessions_collection.create_index([("created_at", ASCENDING)])
        await search_sessions_collection.create_index([("status", ASCENDING), ("created_at", ASCENDING)])
        await search_sessions_collection.create_index([("request_metadata.device_id", ASCENDING)])
        await search_sessions_collection.create_index([("request_metadata.ip", ASCENDING)])
        await search_sessions_collection.create_index([("query.category", ASCENDING), ("created_at", ASCENDING)])
        await search_sessions_collection.create_index([("query.product", ASCENDING), ("created_at", ASCENDING)])

        await call_attempts_collection.create_index([("call_id", ASCENDING)], unique=True)
        await call_attempts_collection.create_index([("search_id", ASCENDING), ("started_at", ASCENDING)])
        await call_attempts_collection.create_index([("vendor.vendor_key", ASCENDING), ("started_at", ASCENDING)])
        await call_attempts_collection.create_index([("status", ASCENDING), ("started_at", ASCENDING)])

        await online_results_collection.create_index([("search_id", ASCENDING), ("fetched_at", ASCENDING)])
        await online_results_collection.create_index([("platform.platform_id", ASCENDING), ("fetched_at", ASCENDING)])
        await online_results_collection.create_index([("vendor.vendor_key", ASCENDING), ("fetched_at", ASCENDING)])

        await vendor_profiles_collection.create_index([("vendor_key", ASCENDING)], unique=True)
        await vendor_profiles_collection.create_index(
            [("place_id", ASCENDING)],
            unique=True,
            sparse=True,
        )
        await vendor_profiles_collection.create_index([("phone", ASCENDING)])
        await vendor_profiles_collection.create_index([("location.pincode", ASCENDING), ("last_seen_at", ASCENDING)])

        await product_catalog_collection.create_index([("product_key", ASCENDING)], unique=True)
        await product_catalog_collection.create_index([("category", ASCENDING), ("canonical_name", ASCENDING)])
        await product_catalog_collection.create_index([("aliases", ASCENDING)])

        await vendor_product_observations_collection.create_index(
            [("observation_key", ASCENDING)],
            unique=True,
        )
        await vendor_product_observations_collection.create_index(
            [("product.product_key", ASCENDING), ("location.pincode", ASCENDING), ("last_observed_at", ASCENDING)]
        )
        await vendor_product_observations_collection.create_index(
            [("vendor.vendor_key", ASCENDING), ("last_observed_at", ASCENDING)]
        )
        await vendor_product_observations_collection.create_index([("expires_at", ASCENDING)])

        await price_history_collection.create_index([("search_id", ASCENDING), ("observed_at", ASCENDING)])
        await price_history_collection.create_index([("product.product_key", ASCENDING), ("observed_at", ASCENDING)])
        await price_history_collection.create_index([("vendor.vendor_key", ASCENDING), ("observed_at", ASCENDING)])

        await raw_webhooks_collection.create_index([("execution_id", ASCENDING), ("received_at", ASCENDING)])
    except Exception as exc:  # pragma: no cover - depends on external service
        logger.warning("MongoDB index setup failed: %s", exc)


async def ping_database() -> bool:
    try:
        await client.admin.command("ping")
        return True
    except Exception as exc:  # pragma: no cover - depends on external service
        logger.warning("MongoDB ping failed: %s", exc)
        return False
