"""Async MongoDB connection (Motor) with Atlas-friendly startup diagnostics."""
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo.errors import ConfigurationError, PyMongoError, ServerSelectionTimeoutError

from app.config.settings import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class MongoManager:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None
    connected: bool = False


mongo = MongoManager()


def _masked_uri(uri: str) -> str:
    """Return the URI without exposing credentials in logs."""
    if not uri:
        return "<missing>"
    try:
        prefix, rest = uri.split("://", 1)
    except ValueError:
        return "<invalid-uri>"
    if "@" in rest and ":" in rest.split("@", 1)[0]:
        credentials, target = rest.split("@", 1)
        username = credentials.split(":", 1)[0]
        return f"{prefix}://{username}:***@{target}"
    return f"{prefix}://{rest}"


async def connect_to_mongo() -> bool:
    """Connect to MongoDB/Atlas and verify the selected database with ping."""
    mongo.connected = False
    mongo.db = None

    if not settings.MONGODB_URI.strip():
        logger.error("MongoDB connection skipped: MONGODB_URI is missing")
        return False

    try:
        mongo.client = AsyncIOMotorClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=8000,
            connectTimeoutMS=8000,
            socketTimeoutMS=10000,
            retryWrites=True,
            uuidRepresentation="standard",
        )
        await mongo.client.admin.command("ping")
        mongo.db = mongo.client[settings.MONGODB_DATABASE]
        mongo.connected = True
        logger.info(
            "MongoDB connected -> database='%s' uri='%s'",
            settings.MONGODB_DATABASE,
            _masked_uri(settings.MONGODB_URI),
        )
        return True
    except ServerSelectionTimeoutError as exc:
        logger.error(
            "MongoDB server selection failed: %s | uri='%s' | check Atlas IP access list, "
            "database-user credentials, DNS/SRV resolution, and outbound network access",
            exc.__class__.__name__,
            _masked_uri(settings.MONGODB_URI),
        )
    except ConfigurationError as exc:
        logger.error(
            "MongoDB URI configuration failed: %s | uri='%s'",
            exc,
            _masked_uri(settings.MONGODB_URI),
        )
    except PyMongoError as exc:
        logger.error(
            "MongoDB connection failed: %s | uri='%s'",
            exc.__class__.__name__,
            _masked_uri(settings.MONGODB_URI),
        )

    if mongo.client is not None:
        mongo.client.close()
        mongo.client = None
    return False


async def close_mongo_connection() -> None:
    if mongo.client is not None:
        mongo.client.close()
        mongo.client = None
        mongo.db = None
        mongo.connected = False
        logger.info("MongoDB connection closed")


def get_db() -> AsyncIOMotorDatabase:
    if not mongo.connected or mongo.db is None:
        raise RuntimeError("Database is not available. Is MongoDB running?")
    return mongo.db


def collection(name: str) -> AsyncIOMotorCollection:
    return get_db()[name]


# Named accessors keep collection-name typos out of the service layer.
def users() -> AsyncIOMotorCollection:
    return collection("users")


def customers() -> AsyncIOMotorCollection:
    return collection("customers")


def shops() -> AsyncIOMotorCollection:
    return collection("shops")


def inventory_items() -> AsyncIOMotorCollection:
    return collection("inventory_items")


def product_requests() -> AsyncIOMotorCollection:
    return collection("product_requests")


def merchant_matches() -> AsyncIOMotorCollection:
    return collection("merchant_matches")


def demand_events() -> AsyncIOMotorCollection:
    return collection("demand_events")


def khata_entries() -> AsyncIOMotorCollection:
    return collection("khata_entries")


def auth_tokens() -> AsyncIOMotorCollection:
    return collection("auth_tokens")


def sessions() -> AsyncIOMotorCollection:
    return collection("sessions")


def notifications() -> AsyncIOMotorCollection:
    return collection("notifications")


def merchant_cooldowns() -> AsyncIOMotorCollection:
    return collection("merchant_cooldowns")
