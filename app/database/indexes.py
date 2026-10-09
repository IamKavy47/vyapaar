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
        # Multi-offer window: lets the scheduler find requests whose window
        # has elapsed but the customer hasn't been notified yet — for
        # batched flushes.
        await m.product_requests().create_index([("offer_window_expires_at", ASCENDING)])
        # Customer-selection audit trail: which shop the customer picked
        # (atomic exactly-one selection is enforced at update_one filter
        # time, but this index makes "who did this customer pick?" fast).
        await m.product_requests().create_index(
            [("selected_match_id", ASCENDING)],
            partialFilterExpression={"selected_match_id": {"$type": "objectId"}},
            name="selected_match_id_when_set",
        )

        await m.merchant_matches().create_index([("request_id", ASCENDING), ("merchant_id", ASCENDING)], unique=True)
        await m.merchant_matches().create_index([("merchant_id", ASCENDING), ("status", ASCENDING)])
        # Source provenance (real / demo_simulated) — supports filtering
        # offer lists by provenance and demo-mode analytics.
        await m.merchant_matches().create_index([("source", ASCENDING)])

        await m.demand_events().create_index([("product_key", ASCENDING), ("created_at", DESCENDING)])
        await m.demand_events().create_index([("merchant_id", ASCENDING), ("created_at", DESCENDING)])
        await m.demand_events().create_index([("category", ASCENDING)])
        await m.demand_events().create_index([("location", GEOSPHERE)])
        # Dedup guard: a single (request_id, merchant_id) must never produce
        # two demand events. record_response in merchant_matching already
        # enforces idempotency at the match layer, but this index makes it
        # impossible even for a buggy writer.
        await m.demand_events().create_index(
            [("request_id", ASCENDING), ("merchant_id", ASCENDING)], unique=True,
        )

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

        # Phone OTP verification codes — sha256(code) at rest, TTL auto-cleanup.
        await m.otp_codes().create_index([("code_hash", ASCENDING)], unique=True)
        await m.otp_codes().create_index([("phone", ASCENDING), ("created_at", DESCENDING)])
        await m.otp_codes().create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)

        # In-app chat — one chat per request, messages sorted oldest-first.
        await m.chats().create_index([("request_id", ASCENDING)], unique=True)
        await m.chats().create_index([("customer_id", ASCENDING), ("updated_at", DESCENDING)])
        await m.chats().create_index([("merchant_id", ASCENDING), ("updated_at", DESCENDING)])
        await m.chat_messages().create_index(
            [("chat_id", ASCENDING), ("created_at", ASCENDING)],
        )
        await m.chat_messages().create_index([("request_id", ASCENDING), ("created_at", ASCENDING)])

        # Shop reports + panic events — manual review queue + audit trail.
        await m.flagged_shops().create_index([("shop_id", ASCENDING), ("created_at", DESCENDING)])
        await m.flagged_shops().create_index([("status", ASCENDING)])
        await m.panic_events().create_index([("customer_id", ASCENDING), ("created_at", DESCENDING)])

        # Product image cache — one image URL per product_key, with a 24h
        # TTL so stale fetches are re-tried.
        await m.product_images().create_index([("product_key", ASCENDING)], unique=True)
        await m.product_images().create_index([("fetched_at", DESCENDING)])

        # Payments — Razorpay order + payment records linked to request+match.
        await m.payments().create_index([("razorpay_order_id", ASCENDING)], unique=True)
        await m.payments().create_index([("request_id", ASCENDING)])
        await m.payments().create_index([("customer_id", ASCENDING), ("created_at", DESCENDING)])

        logger.info("MongoDB indexes ensured (including 2dsphere geospatial indexes)")
    except PyMongoError as exc:
        logger.error("Index creation failed: %s", exc)
