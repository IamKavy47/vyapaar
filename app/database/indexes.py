"""Index creation. Idempotent — safe to run on every boot."""
from pymongo import ASCENDING, DESCENDING, GEOSPHERE, TEXT
from pymongo.errors import PyMongoError

from app.database import mongo as m
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def create_indexes() -> None:
    try:
        await m.users().create_index([("email", ASCENDING)], unique=True, sparse=True)
        # Partial, not sparse: sparse still indexes an explicit null, so every
        # web-registered or logged-out user would collide on the same null.
        await m.users().create_index(
            [("telegram_user_id", ASCENDING)], unique=True,
            partialFilterExpression={"telegram_user_id": {"$type": "number"}},
            name="telegram_user_id_unique_linked",
        )
        await m.users().create_index([("role", ASCENDING)])

        await m.customers().create_index([("user_id", ASCENDING)], unique=True)
        await m.customers().create_index([("telegram_user_id", ASCENDING)])
        await m.customers().create_index([("location", GEOSPHERE)])

        await m.shops().create_index([("user_id", ASCENDING)], unique=True)
        await m.shops().create_index([("telegram_user_id", ASCENDING)])
        await m.shops().create_index([("location", GEOSPHERE)])
        await m.shops().create_index([("category", ASCENDING)])
        await m.shops().create_index([("capabilities", ASCENDING)])
        await m.shops().create_index([("is_active", ASCENDING), ("category", ASCENDING)])
        await m.shops().create_index([("shop_name", TEXT), ("description", TEXT)])

        await m.inventory_items().create_index([("shop_id", ASCENDING), ("product_key", ASCENDING)])
        await m.inventory_items().create_index([("product", TEXT)])

        await m.product_requests().create_index([("request_id", ASCENDING)], unique=True)
        await m.product_requests().create_index([("customer_id", ASCENDING), ("created_at", DESCENDING)])
        await m.product_requests().create_index([("status", ASCENDING)])
        await m.product_requests().create_index([("location", GEOSPHERE)])

        await m.merchant_matches().create_index([("request_id", ASCENDING), ("merchant_id", ASCENDING)], unique=True)
        await m.merchant_matches().create_index([("merchant_id", ASCENDING), ("status", ASCENDING)])

        await m.demand_events().create_index([("product_key", ASCENDING), ("created_at", DESCENDING)])
        await m.demand_events().create_index([("merchant_id", ASCENDING), ("created_at", DESCENDING)])
        await m.demand_events().create_index([("category", ASCENDING)])
        await m.demand_events().create_index([("location", GEOSPHERE)])

        await m.khata_entries().create_index([("merchant_id", ASCENDING), ("customer_key", ASCENDING)])
        await m.khata_entries().create_index([("created_at", DESCENDING)])

        # TTL indexes clean expired auth material up automatically.
        await m.auth_tokens().create_index([("token_hash", ASCENDING)], unique=True)
        await m.auth_tokens().create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
        await m.sessions().create_index([("session_id", ASCENDING)], unique=True)
        await m.sessions().create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)

        await m.merchant_cooldowns().create_index(
            [("merchant_id", ASCENDING), ("product_key", ASCENDING)], unique=True
        )
        await m.merchant_cooldowns().create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)

        await m.notifications().create_index([("created_at", DESCENDING)])
        logger.info("MongoDB indexes ensured (including 2dsphere geospatial indexes)")
    except PyMongoError as exc:
        logger.error("Index creation failed: %s", exc)
