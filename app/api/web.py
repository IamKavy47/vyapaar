"""JSON REST API for the LocalMart React web app (``web/``).

This is the bridge between the uploaded React frontend and the existing
Vyapaar-Mitra backend. Every endpoint here reuses the same business services
that power the Telegram bot (``app/services/*``), so web and Telegram share
one database, one matching engine, one khata ledger and one notification pipe:

  - A customer searching on the web triggers the same zero-inventory matching
    and the same Telegram notifications to merchants as a bot search.
  - A merchant answering in the web inbox runs the same
    ``handle_merchant_response`` path as the bot's YES/NO buttons — the
    customer is notified on Telegram if their account is linked.

Auth is the existing cookie session (``vm_session``) — same as the HTML auth
pages, just JSON instead of form posts.

Field naming: responses use the frontend's camelCase shapes (name,
categoryKey, distanceMeters, ...) so the React app needs no mapping layer.
"""
from datetime import timedelta
from typing import List, Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.ai import intent_engine
from app.ai.intent_engine import AIUnavailableError
from app.api.deps import (
    SESSION_COOKIE, check_auth_rate_limit, clear_session_cookie, current_web_user,
    set_session_cookie,
)
from app.config.settings import settings
from app.database import mongo as m
from app.models.inventory import product_key
from app.models.khata import EntryType
from app.models.merchant_match import MatchStatus
from app.models.product_request import RequestStatus
from app.models.shop import category_label, normalize_category
from app.models.user import UserRole, utcnow
from app.schemas.intent import ProductIntent
from app.services import (
    auth_service, inventory_service, khata_service, merchant_matching,
    notification_service, search_service,
)
from app.services.auth_service import AuthError
from app.services.location_service import update_customer_location
from app.utils.errors import DatabaseError
from app.utils.geo import from_geojson_point, haversine_meters
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["web-app"])

# Backend category taxonomy -> the web app's display categories.
FE_CATEGORY = {
    "kirana": "kirana",
    "hardware": "hardware",
    "plumbing": "hardware",
    "electrical": "electrical",
    "medical": "pharmacy",
    "clothing": "tailor",
    "stationery": "stationery",
    "mobile_electronics": "mobile",
    "repair": "mobile",
    "bakery_food": "dairy",
    "cosmetics": "other",
    "general_store": "kirana",
    "other": "other",
}

REQUEST_STATUS_FE = {
    RequestStatus.CREATED.value: "matching",
    RequestStatus.PROCESSING.value: "matching",
    RequestStatus.MATCHING.value: "matching",
    RequestStatus.OFFERED.value: "offers",
    RequestStatus.MATCHED.value: "offers",
    RequestStatus.COMPLETED.value: "completed",
    RequestStatus.EXPIRED.value: "no_match",
    RequestStatus.CANCELLED.value: "no_match",
}

MATCH_STATUS_FE = {
    MatchStatus.PENDING.value: "pending",
    MatchStatus.NOTIFIED.value: "pending",
    MatchStatus.ACCEPTED.value: "accepted",
    MatchStatus.DECLINED.value: "declined",
    MatchStatus.EXPIRED.value: "expired",
}


# ---------------------------------------------------------------- serializers

def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _oid(value) -> str:
    return str(value) if value is not None else ""


def shop_public(doc: dict, *, lat: Optional[float] = None, lng: Optional[float] = None,
                inventory_count: int = 0) -> dict:
    coords = from_geojson_point(doc.get("location"))
    distance = None
    if lat is not None and lng is not None and coords:
        distance = round(haversine_meters(lat, lng, coords[0], coords[1]))
    category = doc.get("category", "other")
    return {
        "id": _oid(doc.get("_id")),
        "name": doc.get("shop_name", ""),
        "categoryKey": FE_CATEGORY.get(category, "other"),
        "backendCategory": category,
        "categoryLabel": category_label(category),
        "subcategories": doc.get("subcategories") or [],
        "capabilities": doc.get("capabilities") or [],
        "address": doc.get("address"),
        "phone": doc.get("phone"),
        "lat": coords[0] if coords else None,
        "lng": coords[1] if coords else None,
        "isVerified": doc.get("is_verified", False),
        "isActive": doc.get("is_active", True),
        "description": doc.get("description"),
        "distanceMeters": distance,
        "inventoryCount": inventory_count,
        "createdAt": _iso(doc.get("created_at")),
    }


def inventory_public(doc: dict) -> dict:
    quantity = doc.get("quantity", 0)
    return {
        "id": _oid(doc.get("_id")),
        "shopId": _oid(doc.get("shop_id")),
        "name": doc.get("product", ""),
        "price": doc.get("price"),
        "quantity": quantity,
        "unit": doc.get("unit", "piece"),
        "inStock": bool(doc.get("in_stock", (quantity or 0) > 0)),
        "brand": doc.get("brand"),
        "createdAt": _iso(doc.get("created_at")),
        "updatedAt": _iso(doc.get("updated_at")),
    }


def request_public(doc: dict) -> dict:
    return {
        "id": doc.get("request_id"),
        "product": doc.get("product"),
        "categoryKey": FE_CATEGORY.get(doc.get("category"), "other"),
        "backendCategory": doc.get("category"),
        "subCategory": doc.get("sub_category"),
        "quantity": doc.get("quantity", 1),
        "unit": doc.get("unit", "piece"),
        "confidence": doc.get("confidence", 0.0),
        "status": REQUEST_STATUS_FE.get(doc.get("status"), "matching"),
        "backendStatus": doc.get("status"),
        "inputType": doc.get("input_type", "text"),
        "rawText": doc.get("raw_text"),
        "matchedCount": doc.get("matched_count", 0),
        "createdAt": _iso(doc.get("created_at")),
    }


def offer_public(match: dict, *, shop: Optional[dict] = None,
                 request: Optional[dict] = None, has_hint: bool = False) -> dict:
    out = {
        "id": _oid(match.get("_id")),
        "requestId": match.get("request_id"),
        "shopId": _oid(match.get("merchant_id")),
        "status": MATCH_STATUS_FE.get(match.get("status"), "pending"),
        "price": match.get("price"),
        "distanceMeters": round(match.get("distance_meters") or 0),
        "matchScore": match.get("match_score", 0.0),
        "hasInventoryHint": has_hint,
        "createdAt": _iso(match.get("created_at")),
        "respondedAt": _iso(match.get("responded_at")),
    }
    if shop is not None:
        out["shop"] = shop_public(shop)
    if request is not None:
        out["request"] = request_public(request)
    return out


# ------------------------------------------------------------------- security

async def require_user(request: Request) -> dict:
    user = await current_web_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


async def require_my_shop(user: dict = Depends(require_user)) -> dict:
    shop = await m.shops().find_one({"user_id": user["_id"]})
    if not shop:
        raise HTTPException(status_code=403, detail="No shop linked to this account")
    return shop


def _error(status: int, message: str):
    raise HTTPException(status_code=status, detail=message)


# ---------------------------------------------------------------------- auth

class LoginBody(BaseModel):
    email: str
    password: str


class RegisterBody(BaseModel):
    fullName: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=320)
    phone: str = Field(min_length=10, max_length=20)
    password: str = Field(min_length=8, max_length=128)
    role: Literal[UserRole.CUSTOMER.value, UserRole.SHOPKEEPER.value]


@router.post("/auth/register")
async def web_register(body: RegisterBody, request: Request):
    if not check_auth_rate_limit(request):
        _error(429, "Too many attempts. Please wait a minute and try again.")
    role = body.role
    try:
        user = await auth_service.register_user(
            full_name=body.fullName, email=body.email, phone=body.phone,
            password=body.password, role=role,
        )
        session_id = await auth_service.create_session(user)
    except AuthError as exc:
        _error(400, str(exc))
    except RuntimeError as exc:
        raise DatabaseError(
            "MongoDB is unavailable during web registration.",
            operation="web.register", cause=exc,
        ) from exc
    response = JSONResponse(jsonable_encoder({"user": auth_service.to_public(user)}))
    set_session_cookie(response, session_id)
    return response


@router.post("/auth/login")
async def web_login(body: LoginBody, request: Request):
    if not check_auth_rate_limit(request):
        _error(429, "Too many attempts. Please wait a minute and try again.")
    try:
        user = await auth_service.authenticate(body.email, body.password)
        session_id = await auth_service.create_session(user)
    except AuthError as exc:
        _error(401, str(exc))
    except RuntimeError as exc:
        raise DatabaseError(
            "MongoDB is unavailable during web login.",
            operation="web.login", cause=exc,
        ) from exc
    response = JSONResponse(jsonable_encoder({"user": auth_service.to_public(user)}))
    set_session_cookie(response, session_id)
    return response


@router.post("/auth/logout")
async def web_logout(request: Request):
    await auth_service.destroy_session(request.cookies.get(SESSION_COOKIE, ""))
    response = JSONResponse({"ok": True})
    clear_session_cookie(response)
    return response


@router.get("/auth/me")
async def web_me(request: Request):
    user = await current_web_user(request)
    return auth_service.to_public(user)  # null when not logged in


@router.get("/auth/telegram-link")
async def web_telegram_link(user: dict = Depends(require_user)):
    """Deep link that connects this web account to the user's Telegram.

    The bot's /start handler consumes the one-time token (``web_<raw>``).
    """
    if user.get("telegram_user_id"):
        return {"linked": True, "telegramUserId": user["telegram_user_id"]}
    if not settings.TELEGRAM_BOT_USERNAME:
        _error(503, "Telegram bot is not configured (TELEGRAM_BOT_USERNAME missing).")
    raw = await auth_service.create_web_link_token(user["_id"])
    bot = settings.TELEGRAM_BOT_USERNAME.lstrip("@")
    return {"linked": False, "url": f"https://t.me/{bot}?start=web_{raw}"}


# ------------------------------------------------------------------- profile

class CreateShopBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    categoryKey: str = Field(min_length=2, max_length=64)
    categoryLabel: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    lat: float
    lng: float


class ClaimShopBody(BaseModel):
    shopId: str


class UpdateShopLocationBody(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class UpdateCustomerLocationBody(UpdateShopLocationBody):
    pass


class ReserveBody(BaseModel):
    itemId: str
    quantity: Optional[float] = Field(default=None, gt=0)
    lat: float
    lng: float


@router.get("/profile")
async def web_profile(user: dict = Depends(require_user)):
    shop = await m.shops().find_one({"user_id": user["_id"]})
    customer = await m.customers().find_one({"user_id": user["_id"]})
    customer_location = from_geojson_point((customer or {}).get("location"))
    role = user.get("role")
    app_role = role if role in {UserRole.CUSTOMER.value, UserRole.SHOPKEEPER.value} else None
    return {
        "appRole": app_role,
        "shop": shop_public(shop, inventory_count=await inventory_service.count_items(shop["_id"]))
        if shop else None,
        "location": (
            {"lat": customer_location[0], "lng": customer_location[1]}
            if customer_location
            else None
        ),
    }


@router.post("/requests/reserve")
async def web_reserve_item(body: ReserveBody, user: dict = Depends(require_user)):
    """Reserve an in-stock catalogue item with its shopkeeper.

    This deliberately uses the same merchant confirmation flow as a free-text
    request. A stock row is not a payment or delivery promise; the shopkeeper
    must confirm that the item is still available.
    """
    try:
        item = await m.inventory_items().find_one({"_id": ObjectId(body.itemId)})
    except Exception:
        item = None
    if not item or (item.get("quantity") or 0) <= 0 or item.get("in_stock", True) is False:
        _error(409, "This item is no longer in stock")

    shop = await m.shops().find_one({
        "_id": item.get("shop_id"),
        "is_active": True,
        "description": {"$not": {"$regex": "demo merchant seeded", "$options": "i"}},
        "address": {"$not": {"$regex": "^Demo Market", "$options": "i"}},
    })
    if not shop:
        _error(404, "Shop not found")

    result = await search_service.create_reservation(
        item=item,
        shop=shop,
        customer_id=user["_id"],
        telegram_user_id=user.get("telegram_user_id"),
        customer_name=user.get("full_name") or "Customer",
        latitude=body.lat,
        longitude=body.lng,
        quantity=body.quantity,
    )
    return {
        "ok": True,
        "requestId": result["request"]["request_id"],
        "notified": result["notified"],
    }


@router.get("/profile/claimable-shops")
async def web_claimable_shops(user: dict = Depends(require_user)):
    """Shops with no owner account yet (e.g. seeded or bot-created listings)."""
    cursor = m.shops().find(
        {
            "is_active": True,
            "description": {"$not": {"$regex": "demo merchant seeded", "$options": "i"}},
            "address": {"$not": {"$regex": "^Demo Market", "$options": "i"}},
            "$or": [{"user_id": None}, {"user_id": {"$exists": False}}],
        }
    ).limit(50)
    shops = [doc async for doc in cursor]
    return [shop_public(doc) for doc in shops]


@router.post("/profile/claim-shop")
async def web_claim_shop(body: ClaimShopBody, user: dict = Depends(require_user)):
    try:
        shop = await m.shops().find_one({"_id": ObjectId(body.shopId)})
    except Exception:
        shop = None
    if not shop:
        _error(404, "Shop not found")
    if shop.get("user_id") and str(shop["user_id"]) != str(user["_id"]):
        _error(409, "Shop already claimed")
    await m.shops().update_one(
        {"_id": shop["_id"]},
        {"$set": {"user_id": user["_id"], "updated_at": utcnow()}},
    )
    await m.users().update_one(
        {"_id": user["_id"]},
        {"$set": {"role": UserRole.SHOPKEEPER.value, "updated_at": utcnow()}},
    )
    return {"ok": True}


@router.post("/profile/create-shop")
async def web_create_shop(body: CreateShopBody, user: dict = Depends(require_user)):
    existing = await m.shops().find_one({"user_id": user["_id"]})
    if existing:
        _error(409, "You already run a shop")
    await m.users().update_one(
        {"_id": user["_id"]},
        {"$set": {"role": UserRole.SHOPKEEPER.value, "updated_at": utcnow()}},
    )
    user = await auth_service.get_user_by_id(user["_id"])
    await auth_service.ensure_role_profile(
        user,
        shop_name=body.name,
        shop_category=normalize_category(body.categoryKey),
        latitude=body.lat,
        longitude=body.lng,
        address=body.address or "",
    )
    if body.phone:
        await m.shops().update_one(
            {"user_id": user["_id"]},
            {"$set": {"phone": body.phone.strip(), "updated_at": utcnow()}},
        )
    return {"ok": True}


@router.patch("/profile/shop/location")
async def web_update_shop_location(
    body: UpdateShopLocationBody, shop: dict = Depends(require_my_shop),
):
    await m.shops().update_one(
        {"_id": shop["_id"]},
        {"$set": {"location": {"type": "Point", "coordinates": [body.lng, body.lat]},
                  "updated_at": utcnow()}},
    )
    return {"ok": True}


@router.api_route("/profile/location", methods=["PATCH", "POST"])
async def web_update_customer_location(
    body: UpdateCustomerLocationBody, user: dict = Depends(require_user),
):
    if user.get("role") != UserRole.CUSTOMER.value:
        _error(403, "Only customer accounts have a personal location")
    await update_customer_location(user["_id"], body.lat, body.lng)
    return {"ok": True}


# ------------------------------------------------------------------- catalog

@router.get("/catalog/shops")
async def web_catalog_shops(
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    category: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
):
    # Demo seed records must never be presented as real local businesses.
    match: dict = {
        "is_active": True,
        "description": {"$not": {"$regex": "demo merchant seeded", "$options": "i"}},
        "address": {"$not": {"$regex": "^Demo Market", "$options": "i"}},
    }
    if category and category != "all":
        match["category"] = normalize_category(category)

    docs: List[dict]
    distances = {}
    if lat is not None and lng is not None:
        pipeline = [
            {"$geoNear": {
                "near": {"type": "Point", "coordinates": [lng, lat]},
                "distanceField": "distance_meters",
                "maxDistance": settings.SEARCH_RADIUS_MAX_METERS,
                "spherical": True,
                "query": match,
            }},
            {"$limit": limit},
        ]
        docs = [doc async for doc in m.shops().aggregate(pipeline)]
        distances = {doc["_id"]: doc.get("distance_meters") for doc in docs}
    else:
        docs = [doc async for doc in m.shops().find(match).limit(limit)]

    if query:
        q = query.strip().lower()
        docs = [
            d for d in docs
            if q in (d.get("shop_name") or "").lower()
            or q in category_label(d.get("category")).lower()
            or q in (d.get("category") or "").lower()
            or any(q in c.lower() for c in (d.get("capabilities") or []))
        ]

    out = []
    for doc in docs:
        coords = from_geojson_point(doc.get("location"))
        item = shop_public(
            doc, inventory_count=await inventory_service.count_items(doc["_id"], in_stock_only=True)
        )
        if doc["_id"] in distances and distances[doc["_id"]] is not None:
            item["distanceMeters"] = round(distances[doc["_id"]])
        elif lat is not None and lng is not None and coords:
            item["distanceMeters"] = round(haversine_meters(lat, lng, *coords))
        out.append(item)
    out.sort(key=lambda s: (s["distanceMeters"] is None, s["distanceMeters"] or 0))
    return out


@router.get("/catalog/shops/{shop_id}")
async def web_catalog_shop(shop_id: str, lat: Optional[float] = None, lng: Optional[float] = None):
    try:
        doc = await m.shops().find_one({"_id": ObjectId(shop_id)})
    except Exception:
        doc = None
    if not doc:
        _error(404, "Shop not found")
    if (
        "demo merchant seeded" in (doc.get("description") or "").lower()
        or (doc.get("address") or "").lower().startswith("demo market")
    ):
        _error(404, "Shop not found")
    items = await inventory_service.list_items(doc["_id"], limit=200, in_stock_only=True)
    out = shop_public(doc, lat=lat, lng=lng, inventory_count=len(items))
    out["inventory"] = [inventory_public(it) for it in items]
    return out


@router.get("/catalog/price-search")
async def web_price_search(query: str, lat: Optional[float] = None, lng: Optional[float] = None):
    """Cross-shop price comparison for a search term (stored inventory only —
    prices are never invented)."""
    terms = [t for t in query.lower().split() if len(t) > 1]
    if not terms:
        return []
    cursor = m.inventory_items().find({}).limit(500)
    hits = []
    async for item in cursor:
        name = (item.get("product") or "").lower()
        if item.get("price") is None or not any(t in name for t in terms):
            continue
        shop = await m.shops().find_one({"_id": item["shop_id"]})
        if (
            not shop
            or not shop.get("is_active", True)
            or "demo merchant seeded" in (shop.get("description") or "").lower()
            or (shop.get("address") or "").lower().startswith("demo market")
        ):
            continue
        coords = from_geojson_point(shop.get("location"))
        distance = None
        if lat is not None and lng is not None and coords:
            distance = round(haversine_meters(lat, lng, *coords))
        hits.append({
            "item": inventory_public(item),
            "shop": shop_public(shop, lat=lat, lng=lng),
            "distanceMeters": distance,
        })
    hits.sort(key=lambda h: (h["item"]["price"] is None, h["item"]["price"] or 0))
    return hits[:30]


async def _request_stats(days: int = 30, limit: int = 12):
    """Per-product request counts + 'unavailable' (nobody accepted) counts."""
    since = utcnow() - timedelta(days=days)
    cursor = m.product_requests().find({"created_at": {"$gte": since}}).limit(1000)
    by_product: dict = {}
    by_category: dict = {}
    total = 0
    async for doc in cursor:
        total += 1
        key = doc.get("product_key") or (doc.get("product") or "").strip().lower()
        if not key:
            continue
        available = doc.get("status") in {
            RequestStatus.MATCHED.value, RequestStatus.COMPLETED.value,
        }
        cur = by_product.setdefault(key, {
            "product": doc.get("product") or key,
            "categoryKey": FE_CATEGORY.get(doc.get("category"), "other"),
            "requests": 0,
            "unavailable": 0,
        })
        cur["requests"] += 1
        if not available:
            cur["unavailable"] += 1
        cat = FE_CATEGORY.get(doc.get("category"), "other")
        by_category[cat] = by_category.get(cat, 0) + 1
    products = sorted(by_product.values(), key=lambda p: -p["requests"])[:limit]
    categories = sorted(
        ({"categoryKey": k, "requests": v} for k, v in by_category.items()),
        key=lambda c: -c["requests"],
    )
    return products, categories, total


@router.get("/catalog/trending")
async def web_trending():
    products, _, _ = await _request_stats(days=30, limit=10)
    return products


# ------------------------------------------------------------------ requests

# Keyword hints for the rule-based fallback parser. Used ONLY when every AI
# provider is unavailable — it is honest pattern matching, not fabricated AI
# output, and the result is marked provider="rules" with low confidence.
_FALLBACK_CATEGORY_HINTS = {
    "kirana": {"atta", "rice", "dal", "sugar", "salt", "oil", "soap", "biscuit",
               "chawal", "cheeni", "namak", "tel", "kirana", "grocery", "maggi"},
    "medical": {"paracetamol", "dawai", "medicine", "tablet", "crocin", "bandage",
                "pharmacy", "syrup", "dolo", "vicks"},
    "hardware": {"pipe", "tape", "teflon", "screw", "hammer", "paint", "fitting",
                 "wrench", "nail", "hardware", "sealant", "adhesive", "fevicol"},
    "plumbing": {"tap", "nul", "leak", "plumber", "sanitary", "pipe leak"},
    "electrical": {"bulb", "led", "wire", "switch", "fan", "battery", "tape",
                   "charger", "bijli", "adapter", "extension"},
    "mobile_electronics": {"mobile", "phone", "charger", "earphone", "sim",
                           "screen", "headphone"},
    "stationery": {"pen", "notebook", "paper", "pencil", "book", "stationery",
                   "print", "xerox"},
    "clothing": {"shirt", "blouse", "kapda", "cloth", "tailor", "silwana",
                 "jeans", "saree"},
    "bakery_food": {"bread", "milk", "doodh", "egg", "anda", "cake", "bakery",
                    "butter", "dahi", "paneer"},
}

_FALLBACK_UNITS = ["kg", "g", "litre", "liter", "ml", "dozen", "packet", "pack",
                   "piece", "meter", "metre", "inch"]


def _rule_based_intent(raw_text: str) -> ProductIntent:
    """Last-resort parser when no AI provider is reachable.

    Takes the customer's words at face value (product = what they typed),
    guesses category from a keyword table and quantity/unit from the text.
    Marked provider="rules" so nothing pretends to be AI.
    """
    import re

    text = (raw_text or "").strip()
    lower = text.lower()

    category = "other"
    for cat, hints in _FALLBACK_CATEGORY_HINTS.items():
        if any(h in lower for h in hints):
            category = cat
            break

    quantity, unit = 1, "piece"
    match = re.search(r"(\d+(?:\.\d+)?)\s*(" + "|".join(_FALLBACK_UNITS) + r")", lower)
    if match:
        quantity = max(1, int(float(match.group(1))))
        unit = match.group(2)
    else:
        bare = re.search(r"\b(\d{1,4})\b", lower)
        if bare:
            quantity = max(1, int(bare.group(1)))

    # Strip filler words but keep the customer's own phrasing as the product.
    filler = {"chahiye", "milda", "milega", "hai", "kya", "please", "pls", "mujhe",
              "muje", "want", "need", "dijiye", "do", "bro", "yaar"}
    words = [w for w in re.split(r"\s+", text) if w.lower() not in filler]
    product = " ".join(words).strip() or text

    return ProductIntent(
        intent="find_product", product=product[:120], category=category,
        quantity=quantity, unit=unit, confidence=0.5, provider="rules",
        description="Parsed by keyword rules because AI providers were unavailable.",
    )


class CreateRequestBody(BaseModel):
    rawText: str = Field(min_length=2, max_length=500)
    inputType: str = "text"
    lat: float
    lng: float


class ChooseBody(BaseModel):
    offerId: str


@router.post("/requests")
async def web_create_request(body: CreateRequestBody, user: dict = Depends(require_user)):
    """Customer search from the web app.

    Runs the exact same pipeline as a Telegram search: intent extraction ->
    request document -> zero-inventory matching -> Telegram notifications to
    nearby merchants (when they linked Telegram).
    """
    try:
        intent = await intent_engine.extract_intent(body.rawText, input_type="text")
    except AIUnavailableError:
        logger.warning("AI unavailable for web request — using rule-based parser")
        intent = _rule_based_intent(body.rawText)
    except Exception as exc:  # provider bugs shouldn't 500 the customer
        logger.error("intent extraction failed (%s) — using rule-based parser", exc)
        intent = _rule_based_intent(body.rawText)

    if not intent.product:
        _error(422, "Could not identify a product from that text.")

    request_doc = await search_service.create_request(
        intent=intent, customer_id=user["_id"],
        telegram_user_id=user.get("telegram_user_id"),
        latitude=body.lat, longitude=body.lng,
        input_type=body.inputType if body.inputType in {"text", "voice", "image"} else "text",
        raw_text=body.rawText,
    )
    result = await search_service.run_matching(request_doc, notify=True)

    candidates = []
    for cand in result.candidates:
        shop = await m.shops().find_one({"_id": ObjectId(cand.merchant_id)})
        if not shop:
            continue
        candidates.append({
            "shopId": cand.merchant_id,
            "shop": shop_public(shop, lat=body.lat, lng=body.lng),
            "distanceMeters": round(cand.distance_meters),
            "matchScore": cand.match_score,
            "hasInventoryHint": cand.has_inventory_hint,
            "knownPrice": cand.known_price,
        })

    return {
        "requestId": request_doc["request_id"],
        "intent": {
            "product": intent.product,
            "categoryKey": FE_CATEGORY.get(intent.category, "other"),
            "backendCategory": intent.category,
            "subCategory": intent.sub_category,
            "quantity": intent.quantity,
            "unit": intent.unit,
            "confidence": intent.confidence,
        },
        "candidates": candidates,
    }


@router.get("/requests/mine")
async def web_my_requests(user: dict = Depends(require_user)):
    docs = await search_service.recent_requests(user["_id"], limit=50)
    return [request_public(d) for d in docs]


async def _offers_for_request(request_doc: dict) -> List[dict]:
    cursor = m.merchant_matches().find(
        {"request_id": request_doc["request_id"]}
    ).sort("match_score", -1)
    offers = []
    keys = [product_key(request_doc.get("product") or "")]
    async for match in cursor:
        shop = await m.shops().find_one({"_id": match["merchant_id"]})
        hint = False
        if shop:
            hint = await m.inventory_items().find_one(
                {
                    "shop_id": shop["_id"],
                    "product_key": {"$in": keys},
                    "quantity": {"$gt": 0},
                    "in_stock": {"$ne": False},
                }
            ) is not None
        offers.append(offer_public(match, shop=shop, has_hint=hint))
    return offers


@router.get("/requests/{request_id}")
async def web_request_detail(request_id: str, user: dict = Depends(require_user)):
    doc = await search_service.get_request(request_id)
    if not doc or str(doc.get("customer_id")) != str(user["_id"]):
        _error(404, "Request not found")
    offers = await _offers_for_request(doc)
    return {"request": request_public(doc), "offers": offers}


@router.post("/requests/choose")
async def web_choose_offer(body: ChooseBody, user: dict = Depends(require_user)):
    """Customer picks the winning shop. The request closes, other pending
    offers expire, and the shop gets a Telegram heads-up if it linked one."""
    match = await merchant_matching.get_match(body.offerId)
    if not match:
        _error(404, "Offer not found")
    request_doc = await search_service.get_request(match["request_id"])
    if not request_doc or str(request_doc.get("customer_id")) != str(user["_id"]):
        _error(403, "Not your request")
    if match.get("status") != MatchStatus.ACCEPTED.value:
        _error(400, "Shop has not confirmed yet")

    await m.product_requests().update_one(
        {"request_id": request_doc["request_id"]},
        {"$set": {"status": RequestStatus.COMPLETED.value, "updated_at": utcnow()}},
    )
    await m.merchant_matches().update_many(
        {
            "request_id": request_doc["request_id"],
            "_id": {"$ne": match["_id"]},
            "status": {"$in": [MatchStatus.PENDING.value, MatchStatus.NOTIFIED.value]},
        },
        {"$set": {"status": MatchStatus.EXPIRED.value}},
    )

    shop = await m.shops().find_one({"_id": match["merchant_id"]})
    if shop and shop.get("telegram_user_id"):
        await notification_service.send_message(
            shop["telegram_user_id"],
            "🎉 Customer ne aapko chuna!\n\n"
            f"📦 {request_doc.get('product') or 'Item'}"
            + (f" — ₹{match['price']:g}" if match.get("price") else "")
            + "\nCustomer dukaan par aa sakta hai. Stock taiyaar rakhiye.",
            kind="customer_chose_you",
        )
    return {"ok": True}


# ------------------------------------------------------------------ merchant

class RespondBody(BaseModel):
    offerId: str
    accept: bool
    price: Optional[float] = None


class AddItemBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    price: float = Field(gt=0)
    quantity: float = Field(ge=0)
    unit: str = Field(min_length=1, max_length=32)


class UpdateItemBody(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    price: Optional[float] = Field(default=None, gt=0)
    quantity: Optional[float] = Field(default=None, ge=0)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=32)


class AddKhataBody(BaseModel):
    customerName: str = Field(min_length=2, max_length=120)
    amount: float = Field(gt=0)
    direction: Literal["udhaar", "jama"]
    note: Optional[str] = Field(default=None, max_length=200)


@router.get("/merchant/shop")
async def web_my_shop(shop: dict = Depends(require_my_shop)):
    return shop_public(shop, inventory_count=await inventory_service.count_items(shop["_id"]))


@router.get("/merchant/inbox")
async def web_merchant_inbox(shop: dict = Depends(require_my_shop)):
    """Pending requests routed to this shop — the same list the bot pings about."""
    cursor = m.merchant_matches().find({
        "merchant_id": shop["_id"],
        "status": {"$in": [MatchStatus.PENDING.value, MatchStatus.NOTIFIED.value]},
    }).sort("created_at", -1).limit(50)
    inbox = []
    closed = {RequestStatus.COMPLETED.value, RequestStatus.CANCELLED.value,
              RequestStatus.EXPIRED.value}
    async for match in cursor:
        request_doc = await search_service.get_request(match["request_id"])
        if not request_doc or request_doc.get("status") in closed:
            continue
        inbox.append(offer_public(match, request=request_doc))
    return inbox


@router.post("/merchant/respond")
async def web_merchant_respond(body: RespondBody, shop: dict = Depends(require_my_shop)):
    """YES / NO from the web inbox — identical to the bot's inline buttons:
    records the response, writes the demand event, and notifies the customer
    on Telegram when their account is linked."""
    match = await merchant_matching.get_match(body.offerId)
    if not match or str(match.get("merchant_id")) != str(shop["_id"]):
        _error(404, "Offer not found")
    ok, _ctx = await search_service.handle_merchant_response(
        match["_id"], accepted=body.accept, price=body.price if body.accept else None,
    )
    if not ok:
        _error(400, "Already responded")
    return {"ok": True}


@router.get("/merchant/inventory")
async def web_merchant_inventory(shop: dict = Depends(require_my_shop)):
    items = await inventory_service.list_items(shop["_id"], limit=500)
    return [inventory_public(it) for it in items]


@router.post("/merchant/inventory")
async def web_add_inventory_item(body: AddItemBody, shop: dict = Depends(require_my_shop)):
    doc = await inventory_service.upsert_item(
        shop_id=shop["_id"], product=body.name, quantity=body.quantity,
        unit=body.unit, price=body.price, source="web",
    )
    await m.inventory_items().update_one(
        {"shop_id": doc["shop_id"], "product_key": doc["product_key"]},
        {"$set": {"in_stock": body.quantity > 0}},
    )
    return {"ok": True}


async def _my_item(item_id: str, shop: dict) -> dict:
    try:
        doc = await m.inventory_items().find_one({"_id": ObjectId(item_id)})
    except Exception:
        doc = None
    if not doc or str(doc.get("shop_id")) != str(shop["_id"]):
        _error(404, "Item not found")
    return doc


@router.patch("/merchant/inventory/{item_id}")
async def web_update_inventory_item(item_id: str, body: UpdateItemBody,
                                    shop: dict = Depends(require_my_shop)):
    await _my_item(item_id, shop)
    updates: dict = {}
    if body.name is not None:
        updates["product"] = body.name.strip()
        updates["product_key"] = product_key(body.name)
    if body.price is not None:
        updates["price"] = body.price
    if body.unit is not None:
        updates["unit"] = body.unit.strip().lower()
    if body.quantity is not None:
        updates["quantity"] = body.quantity
        updates["in_stock"] = body.quantity > 0
    if not updates:
        return {"ok": True}
    updates["updated_at"] = utcnow()
    await m.inventory_items().update_one({"_id": ObjectId(item_id)}, {"$set": updates})
    return {"ok": True}


@router.post("/merchant/inventory/{item_id}/toggle")
async def web_toggle_inventory_item(item_id: str, shop: dict = Depends(require_my_shop)):
    item = await _my_item(item_id, shop)
    current = bool(item.get("in_stock", (item.get("quantity") or 0) > 0))
    await m.inventory_items().update_one(
        {"_id": item["_id"]},
        {"$set": {"in_stock": not current, "updated_at": utcnow()}},
    )
    return {"ok": True, "inStock": not current}


@router.delete("/merchant/inventory/{item_id}")
async def web_remove_inventory_item(item_id: str, shop: dict = Depends(require_my_shop)):
    await _my_item(item_id, shop)
    await m.inventory_items().delete_one({"_id": ObjectId(item_id)})
    return {"ok": True}


@router.get("/merchant/khata")
async def web_merchant_khata(shop: dict = Depends(require_my_shop)):
    entries = await khata_service.recent_entries(shop["_id"], limit=200)
    summary = await khata_service.summary(shop["_id"])
    fe_entries = [{
        "id": _oid(e.get("_id")),
        "customerName": e.get("customer_name"),
        "amount": e.get("amount"),
        "direction": "udhaar" if e.get("entry_type") == EntryType.CREDIT.value else "jama",
        "note": e.get("description"),
        "createdAt": _iso(e.get("created_at")),
    } for e in entries]
    udhaar = sum(b.total_credit for b in summary.balances)
    jama = sum(b.total_paid for b in summary.balances)
    return {
        "entries": fe_entries,
        "udhaar": round(udhaar, 2),
        "jama": round(jama, 2),
        "outstanding": round(udhaar - jama, 2),
    }


@router.post("/merchant/khata")
async def web_add_khata(body: AddKhataBody, shop: dict = Depends(require_my_shop)):
    entry_type = EntryType.CREDIT.value if body.direction == "udhaar" else EntryType.PAYMENT.value
    try:
        await khata_service.add_entry(
            merchant_id=shop["_id"], customer_name=body.customerName,
            amount=body.amount, entry_type=entry_type,
            description=body.note or "", source="web",
        )
    except khata_service.KhataError as exc:
        _error(400, str(exc))
    return {"ok": True}


@router.get("/merchant/demand")
async def web_merchant_demand(shop: dict = Depends(require_my_shop)):
    products, categories, total = await _request_stats(days=30, limit=12)
    return {"products": products, "categories": categories, "total": total}
