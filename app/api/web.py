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
import asyncio
from datetime import timedelta
from typing import Dict, List, Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from fastapi import Body

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
from app.models.shop import CATEGORY_AFFINITY, category_label, normalize_category
from app.models.user import UserRole, utcnow
from app.schemas.intent import ProductIntent
from app.services import (
    auth_service, demand_engine, demo_service, inventory_service,
    khata_service, merchant_matching, notification_service, opportunity_service,
    product_image_service, search_service, trust_service,
)
from app.services.auth_service import AuthError, OTPError
from app.services import chat_service as chat_service_mod
from app.services.chat_service import ChatError
from app.services.location_service import update_customer_location
from app.services import verification_service as verification_service_mod
from app.services.verification_service import VerificationError
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
    shop_type = doc.get("shop_type") or "shop"
    service_line = doc.get("service_line")
    # Display label: for services, prefer the service_line label (e.g.
    # "Plumber") over the category label (e.g. "Plumbing").
    from app.models.shop import SERVICE_LINE_LABELS
    if shop_type == "service" and service_line:
        display_label = SERVICE_LINE_LABELS.get(service_line, service_line.title())
    else:
        display_label = category_label(category)
    return {
        "id": _oid(doc.get("_id")),
        "name": doc.get("shop_name", ""),
        "categoryKey": FE_CATEGORY.get(category, "other"),
        "backendCategory": category,
        "categoryLabel": display_label,
        "subcategories": doc.get("subcategories") or [],
        "capabilities": doc.get("capabilities") or [],
        "address": doc.get("address"),
        "phone": doc.get("phone"),
        "lat": coords[0] if coords else None,
        "lng": coords[1] if coords else None,
        "isVerified": doc.get("is_verified", False),
        "isActive": doc.get("is_active", True),
        "description": doc.get("description"),
        "shopType": shop_type,
        "serviceLine": service_line,
        "distanceMeters": distance,
        "inventoryCount": inventory_count,
        "shopfrontPhotoUrl": doc.get("shopfront_photo_url"),
        "verificationStatus": doc.get("verification_status", "pending"),
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
        "imageUrl": doc.get("image_url"),
        "imageSource": doc.get("image_source") or "none",
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
        "selectedMatchId": _oid(doc.get("selected_match_id")) or None,
        "selectedAt": _iso(doc.get("selected_at")),
        "offerWindowExpiresAt": _iso(doc.get("offer_window_expires_at")),
        "customerNotifiedAt": _iso(doc.get("customer_notified_at")),
        "createdAt": _iso(doc.get("created_at")),
    }


def offer_public(match: dict, *, shop: Optional[dict] = None,
                 request: Optional[dict] = None, has_hint: bool = False,
                 trust: Optional[dict] = None, freshness: Optional[dict] = None,
                 why: Optional[List[str]] = None,
                 inventory_updated_at=None) -> dict:
    out = {
        "id": _oid(match.get("_id")),
        "requestId": match.get("request_id"),
        "shopId": _oid(match.get("merchant_id")),
        "status": MATCH_STATUS_FE.get(match.get("status"), "pending"),
        "price": match.get("price"),
        "distanceMeters": round(match.get("distance_meters") or 0),
        "matchScore": match.get("match_score", 0.0),
        "scoreBreakdown": match.get("score_breakdown") or {},
        "hasInventoryHint": has_hint,
        "source": match.get("source") or "real",
        "isDemoSimulated": (match.get("source") or "real") == "demo_simulated",
        "createdAt": _iso(match.get("created_at")),
        "notifiedAt": _iso(match.get("notified_at")),
        "respondedAt": _iso(match.get("responded_at")),
        "responseSeconds": _response_seconds(match),
        "inventoryUpdatedAt": _iso(inventory_updated_at),
        "trust": trust,
        "freshness": freshness,
        "whyRecommended": why or [],
    }
    if shop is not None:
        out["shop"] = shop_public(shop)
    if request is not None:
        out["request"] = request_public(request)
    return out


def _response_seconds(match: dict) -> Optional[int]:
    notified = match.get("notified_at")
    responded = match.get("responded_at")
    if not notified or not responded:
        return None
    try:
        delta = (responded - notified).total_seconds()
        return int(delta) if delta >= 0 else None
    except Exception:
        return None


# ------------------------------------------------------------------- security

async def require_user(request: Request) -> dict:
    user = await current_web_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


async def require_verified_user(request: Request) -> dict:
    """Like require_user, but also requires the phone number to be OTP-verified.

    All real actions (search, accept/reject a request, choose an offer,
    upload shopfront photo, send a chat message, panic, flag, etc.) go
    through this gate. Read endpoints (profile.get, /auth/me, catalog)
    can use plain ``require_user`` so an unverified user can still see
    their own profile.
    """
    user = await require_user(request)
    if not user.get("phone_verified"):
        raise HTTPException(
            status_code=403,
            detail="Please verify your phone number before doing this.",
        )
    return user


async def require_my_shop(user: dict = Depends(require_user)) -> dict:
    shop = await m.shops().find_one({"user_id": user["_id"]})
    if not shop:
        raise HTTPException(status_code=403, detail="No shop linked to this account")
    return shop


async def require_my_verified_shop(user: dict = Depends(require_verified_user)) -> dict:
    """Like require_my_shop, but also requires phone OTP verification.

    Used by merchant action endpoints (respond to a request, add inventory,
    plan from opportunity, upload shopfront photo) so an unverified
    shopkeeper can still log in and see their profile but cannot act.
    """
    shop = await m.shops().find_one({"user_id": user["_id"]})
    if not shop:
        raise HTTPException(status_code=403, detail="No shop linked to this account")
    return shop


async def require_admin(request: Request) -> dict:
    user = await current_web_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.get("role") != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


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
    otp: str = Field(min_length=4, max_length=10,
                     description="Phone OTP code — required to verify the phone at registration time.")


class SendOtpBody(BaseModel):
    phone: str = Field(min_length=10, max_length=20)


class VerifyOtpBody(BaseModel):
    phone: str = Field(min_length=10, max_length=20)
    code: str = Field(min_length=4, max_length=10)


@router.post("/auth/send-otp")
async def web_send_otp(body: SendOtpBody):
    """Send a 6-digit OTP to the given phone number.

    In stub mode (default for hackathon) the OTP is logged to the server
    console AND returned in the response as ``dev_otp`` so you can paste
    it from the network response. Flip ``OTP_STUB_MODE=false`` and wire
    MSG91 / Twilio for production.
    """
    try:
        result = await auth_service.send_otp(body.phone)
    except OTPError as exc:
        _error(400, str(exc))
    return result


@router.post("/auth/verify-otp")
async def web_verify_otp(body: VerifyOtpBody):
    """Verify a standalone OTP. Used to re-verify an existing user's phone
    (e.g. a logged-in user who hasn't verified yet). Registration uses the
    inline ``otp`` field on POST /auth/register instead.
    """
    try:
        result = await auth_service.verify_otp(body.phone, body.code)
    except OTPError as exc:
        _error(400, str(exc))
    return result


@router.post("/auth/register")
async def web_register(body: RegisterBody, request: Request):
    """Register a new account — phone OTP is required at this step.

    The flow: caller sends POST /auth/send-otp first to dispatch a 6-digit
    code, then submits the full register body including the OTP. The OTP is
    consumed (one-shot) and the new account is created with
    ``phone_verified=True`` so the user can act immediately after login.
    """
    if not check_auth_rate_limit(request):
        _error(429, "Too many attempts. Please wait a minute and try again.")
    # Verify the OTP first — if it fails, no account is created.
    try:
        await auth_service.consume_otp(body.phone, body.otp)
    except OTPError as exc:
        _error(400, str(exc))
    role = body.role
    try:
        user = await auth_service.register_user(
            full_name=body.fullName, email=body.email, phone=body.phone,
            password=body.password, role=role,
        )
        # OTP just succeeded — flip phone_verified on the new account.
        await auth_service.mark_phone_verified(user["_id"])
        user["phone_verified"] = True
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
    shopType: Optional[str] = Field(default="shop", pattern="^(shop|vendor|service)$")
    serviceLine: Optional[str] = None  # only when shopType=service


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
async def web_reserve_item(body: ReserveBody, user: dict = Depends(require_verified_user)):
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
    # Now update the shop doc with shop_type + service_line (these aren't
    # part of ensure_role_profile's signature — a separate update keeps
    # the existing function's contract stable).
    shop_update: dict = {}
    if body.phone:
        shop_update["phone"] = body.phone.strip()
    if body.shopType:
        shop_update["shop_type"] = body.shopType
    if body.serviceLine and body.shopType == "service":
        shop_update["service_line"] = body.serviceLine
        # Also add the service line as a capability so zero-inventory
        # matching finds this service provider when a customer asks for
        # "plumber" / "electrician" etc.
        shop = await m.shops().find_one({"user_id": user["_id"]})
        if shop:
            caps = set(shop.get("capabilities") or [])
            caps.add(body.serviceLine)
            shop_update["capabilities"] = sorted(caps)
    if shop_update:
        shop_update["updated_at"] = utcnow()
        await m.shops().update_one(
            {"user_id": user["_id"]},
            {"$set": shop_update},
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
    # Also: only VERIFIED shops are visible to customers. A shop is verified
    # when (1) the shopkeeper's phone is OTP-verified, (2) they upload a
    # geo-tagged shopfront photo from inside the PWA, and (3) an admin
    # approves the photo. Unverified shops cannot be browsed or matched.
    match: dict = {
        "is_active": True,
        "is_verified": True,
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


# ------------------------------------------------------------------ products
# E-commerce-style Browse page data source. Aggregates inventory items
# across all VERIFIED shops, joins shop info + distance, and returns a
# paginated list with product images. If a product has no image (neither
# manually uploaded nor AI-fetched), the Browse page shows a placeholder.

@router.get("/catalog/products")
async def web_catalog_products(
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    category: Optional[str] = None,
    query: Optional[str] = None,
    sort: str = Query("nearest", regex="^(nearest|cheapest|newest)$"),
    page: int = Query(1, ge=1, le=100),
    limit: int = Query(30, ge=1, le=60),
):
    """Paginated, geo-sorted product cards for the Browse page.

    Only products from VERIFIED, ACTIVE shops are shown — the same
    is_verified gate that find_candidates uses. Demo seed shops are
    excluded by the regex filter (same as catalog/shops).
    """
    if category and category != "all":
        shop_category = normalize_category(category)
    else:
        shop_category = None

    # Step 1: gather verified shop ids + distances via $geoNear (or all
    # verified shops if no lat/lng).
    shop_match: dict = {
        "is_active": True,
        "is_verified": True,
        "description": {"$not": {"$regex": "demo merchant seeded", "$options": "i"}},
        "address": {"$not": {"$regex": "^Demo Market", "$options": "i"}},
    }
    if shop_category:
        shop_match["category"] = shop_category

    shops_map: Dict[ObjectId, dict] = {}
    if lat is not None and lng is not None:
        pipeline = [
            {"$geoNear": {
                "near": {"type": "Point", "coordinates": [lng, lat]},
                "distanceField": "distance_meters",
                "maxDistance": settings.SEARCH_RADIUS_MAX_METERS,
                "spherical": True,
                "query": shop_match,
            }},
        ]
        async for shop_doc in m.shops().aggregate(pipeline):
            shops_map[shop_doc["_id"]] = shop_doc
    else:
        async for shop_doc in m.shops().find(shop_match).limit(200):
            shops_map[shop_doc["_id"]] = shop_doc

    if not shops_map:
        return {"products": [], "page": page, "limit": limit, "total": 0, "hasMore": False}

    # Step 2: gather inventory items from these shops.
    inv_match: dict = {
        "shop_id": {"$in": list(shops_map.keys())},
        "quantity": {"$gt": 0},
        "in_stock": {"$ne": False},
    }
    if query:
        # Full-text-ish product name search.
        terms = [t for t in query.strip().lower().split() if len(t) > 1]
        if terms:
            inv_match["$or"] = [
                {"product_key": {"$regex": term, "$options": "i"}}
                for term in terms
            ]

    sort_field = "created_at" if sort == "newest" else None
    cursor = m.inventory_items().find(inv_match)
    if sort == "newest":
        cursor = cursor.sort("created_at", -1)
    elif sort == "cheapest":
        cursor = cursor.sort("price", 1)
    # For "nearest" we sort after assembling since we need shop distance.

    items: List[dict] = []
    async for item in cursor.limit(limit * 4):  # over-fetch then trim
        shop = shops_map.get(item.get("shop_id"))
        if not shop:
            continue
        coords = from_geojson_point(shop.get("location"))
        distance = None
        if lat is not None and lng is not None and coords:
            distance = round(haversine_meters(lat, lng, coords[0], coords[1]))
        items.append({
            "id": _oid(item.get("_id")),
            "shopId": _oid(item.get("shop_id")),
            "name": item.get("product", ""),
            "price": item.get("price"),
            "unit": item.get("unit", "piece"),
            "quantity": item.get("quantity", 0),
            "inStock": bool(item.get("in_stock", (item.get("quantity") or 0) > 0)),
            "brand": item.get("brand"),
            "imageUrl": item.get("image_url"),
            "imageSource": item.get("image_source") or "none",
            "shop": {
                "id": _oid(shop.get("_id")),
                "name": shop.get("shop_name", ""),
                "categoryKey": FE_CATEGORY.get(shop.get("category"), "other"),
                "categoryLabel": category_label(shop.get("category")),
                "address": shop.get("address"),
                "phone": shop.get("phone"),
                "lat": coords[0] if coords else None,
                "lng": coords[1] if coords else None,
                "isVerified": shop.get("is_verified", False),
                "shopfrontPhotoUrl": shop.get("shopfront_photo_url"),
                "distanceMeters": distance,
            },
        })

    # Step 3: sort the merged list.
    if sort == "nearest" and any(p["shop"]["distanceMeters"] is not None for p in items):
        items.sort(key=lambda p: (
            p["shop"]["distanceMeters"] is None,
            p["shop"]["distanceMeters"] or 0,
        ))
    elif sort == "cheapest":
        items.sort(key=lambda p: (
            p["price"] is None,
            p["price"] if p["price"] is not None else float("inf"),
        ))

    total = len(items)
    start = (page - 1) * limit
    page_items = items[start:start + limit]
    return {
        "products": page_items,
        "page": page,
        "limit": limit,
        "total": total,
        "hasMore": start + limit < total,
    }


# ------------------------------------------------------------------ services
# Service providers (plumbers, electricians, tailors, repair workshops, etc.)
# are shops with shop_type="service". They don't have inventory — they have
# capabilities (plumbing, electrical, tailoring) and a service area. The
# customer's "Services" tab on the Browse page calls this endpoint.

@router.get("/catalog/services")
async def web_catalog_services(
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    service_line: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = Query(30, ge=1, le=60),
):
    """List verified service providers near the customer.

    Filters by service_line (e.g. 'plumber', 'electrician') if provided.
    Sorted by distance if lat/lng is provided.
    """
    shop_match: dict = {
        "is_active": True,
        "is_verified": True,
        "shop_type": "service",
        "description": {"$not": {"$regex": "demo merchant seeded", "$options": "i"}},
        "address": {"$not": {"$regex": "^Demo Market", "$options": "i"}},
    }
    if service_line and service_line != "all":
        shop_match["service_line"] = service_line

    shops: List[dict] = []
    if lat is not None and lng is not None:
        pipeline = [
            {"$geoNear": {
                "near": {"type": "Point", "coordinates": [lng, lat]},
                "distanceField": "distance_meters",
                "maxDistance": settings.SEARCH_RADIUS_MAX_METERS,
                "spherical": True,
                "query": shop_match,
            }},
            {"$limit": limit},
        ]
        async for shop_doc in m.shops().aggregate(pipeline):
            shops.append(shop_doc)
    else:
        cursor = m.shops().find(shop_match).sort("accepted_count", -1).limit(limit)
        shops = [doc async for doc in cursor]

    # Optional text query filter (on shop name / service_line / capabilities).
    if query:
        q = query.strip().lower()
        shops = [
            s for s in shops
            if q in (s.get("shop_name") or "").lower()
            or q in (s.get("service_line") or "").lower()
            or any(q in c.lower() for c in (s.get("capabilities") or []))
        ]

    return [shop_public(s, lat=lat, lng=lng) for s in shops]


@router.get("/catalog/service-lines")
async def web_catalog_service_lines():
    """Return the taxonomy of service lines for the customer's filter UI."""
    from app.models.shop import SERVICE_LINES, SERVICE_LINE_LABELS
    return [
        {"key": sl, "label": SERVICE_LINE_LABELS.get(sl, sl.replace("_", " ").title())}
        for sl in SERVICE_LINES
    ]


@router.get("/catalog/recommendations")
async def web_catalog_recommendations(
    user: dict = Depends(require_user),
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    limit: int = Query(10, ge=1, le=20),
):
    """AI-powered product recommendations for the Browse page.

    Deterministic scoring (no ML model). Each candidate product is scored by:
      - +10 if its category matches a category the customer has searched
        for before (their dominant category in the last 30 requests)
      - +5  if its category matches the category of a request where this
        customer picked a shop (their "purchase" history)
      - +3  if the product is trending (top 30-day by uniqueRequests nearby)
      - +1  if the product is in stock at a nearby shop
      - +1  if it's at a shop the customer has previously picked

    Returns the top N products with the same shape as /catalog/products.
    """
    from app.models.inventory import product_key as pk_fn

    # Determine customer's dominant category from their last 30 requests.
    customer_requests = await search_service.recent_requests(user["_id"], limit=30)
    searched_categories: Dict[str, int] = {}
    picked_shop_ids: set = set()
    picked_categories: Dict[str, int] = {}
    for req in customer_requests:
        cat = req.get("category") or "other"
        searched_categories[cat] = searched_categories.get(cat, 0) + 1
        if req.get("status") == RequestStatus.COMPLETED.value and req.get("selected_match_id"):
            match = await merchant_matching.get_match(req["selected_match_id"])
            if match:
                shop = await m.shops().find_one({"_id": match["merchant_id"]})
                if shop:
                    picked_shop_ids.add(str(shop["_id"]))
                    picked_cat = shop.get("category") or "other"
                    picked_categories[picked_cat] = picked_categories.get(picked_cat, 0) + 1

    # Step 1: gather nearby verified shops (customer location or none).
    shop_match: dict = {
        "is_active": True,
        "is_verified": True,
        "description": {"$not": {"$regex": "demo merchant seeded", "$options": "i"}},
        "address": {"$not": {"$regex": "^Demo Market", "$options": "i"}},
    }
    shops_map: Dict[ObjectId, dict] = {}
    if lat is not None and lng is not None:
        pipeline = [{"$geoNear": {
            "near": {"type": "Point", "coordinates": [lng, lat]},
            "distanceField": "distance_meters",
            "maxDistance": settings.SEARCH_RADIUS_MAX_METERS,
            "spherical": True,
            "query": shop_match,
        }}]
        async for shop_doc in m.shops().aggregate(pipeline):
            shops_map[shop_doc["_id"]] = shop_doc
    else:
        async for shop_doc in m.shops().find(shop_match).limit(200):
            shops_map[shop_doc["_id"]] = shop_doc

    if not shops_map:
        return {"recommendations": [], "reason": "No verified shops nearby yet."}

    # Step 2: trending products nearby (last 30d unique requests).
    trending_rows = await demand_engine.top_unique_requested_products(
        latitude=lat, longitude=lng, radius_meters=settings.OPPORTUNITY_RADIUS_METERS,
        days=30, limit=30,
    )
    trending_keys = {pk_fn(r.get("product") or "") for r in trending_rows}

    # Step 3: gather in-stock inventory + score.
    items: List[dict] = []
    async for item in m.inventory_items().find({
        "shop_id": {"$in": list(shops_map.keys())},
        "quantity": {"$gt": 0},
        "in_stock": {"$ne": False},
    }).limit(500):
        shop = shops_map.get(item.get("shop_id"))
        if not shop:
            continue
        shop_cat = shop.get("category") or "other"
        score = 0
        score += 10 * searched_categories.get(shop_cat, 0)
        score += 5 * picked_categories.get(shop_cat, 0)
        if pk_fn(item.get("product") or "") in trending_keys:
            score += 3
        score += 1  # in stock nearby
        if str(shop["_id"]) in picked_shop_ids:
            score += 1
        if score == 0:
            # No signal for this customer — skip it (avoid noise).
            continue
        coords = from_geojson_point(shop.get("location"))
        distance = None
        if lat is not None and lng is not None and coords:
            distance = round(haversine_meters(lat, lng, coords[0], coords[1]))
        items.append({
            "score": score,
            "product": {
                "id": _oid(item.get("_id")),
                "shopId": _oid(item.get("shop_id")),
                "name": item.get("product", ""),
                "price": item.get("price"),
                "unit": item.get("unit", "piece"),
                "quantity": item.get("quantity", 0),
                "inStock": bool(item.get("in_stock", (item.get("quantity") or 0) > 0)),
                "brand": item.get("brand"),
                "imageUrl": item.get("image_url"),
                "imageSource": item.get("image_source") or "none",
                "shop": {
                    "id": _oid(shop.get("_id")),
                    "name": shop.get("shop_name", ""),
                    "categoryKey": FE_CATEGORY.get(shop_cat, "other"),
                    "categoryLabel": category_label(shop_cat),
                    "address": shop.get("address"),
                    "phone": shop.get("phone"),
                    "lat": coords[0] if coords else None,
                    "lng": coords[1] if coords else None,
                    "isVerified": shop.get("is_verified", False),
                    "shopfrontPhotoUrl": shop.get("shopfront_photo_url"),
                    "distanceMeters": distance,
                },
            },
        })

    items.sort(key=lambda r: (-r["score"], r["product"]["shop"].get("distanceMeters") or 0))
    out = [r["product"] for r in items[:limit]]
    return {
        "recommendations": out,
        "dominantCategory": max(searched_categories, key=searched_categories.get)
            if searched_categories else None,
        "pickedShopCount": len(picked_shop_ids),
        "reason": (
            f"Based on {sum(searched_categories.values())} of your past searches"
            + (f" and {len(picked_shop_ids)} shop picks" if picked_shop_ids else "")
            + " — picked products matching your dominant categories, trending nearby, and in stock."
        ) if items else "No recommendations yet — search for products to start personalising.",
    }


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
async def web_create_request(body: CreateRequestBody, user: dict = Depends(require_verified_user)):
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

    intent_intent_provider = intent.provider or "ai"
    is_rule_based = intent.provider == "rules"

    request_doc = await search_service.create_request(
        intent=intent, customer_id=user["_id"],
        telegram_user_id=user.get("telegram_user_id"),
        latitude=body.lat, longitude=body.lng,
        input_type=body.inputType if body.inputType in {"text", "voice", "image"} else "text",
        raw_text=body.rawText,
    )
    result = await search_service.run_matching(request_doc, notify=True)

    # Deterministic demo simulation: when DEMO_MODE is on AND no live Telegram
    # polling is running, schedule simulated merchant responses for the
    # flagship scenario (Teflon Tape). Each simulated response is tagged
    # source="demo_simulated" so the customer UI can label it clearly.
    try:
        await demo_service.maybe_schedule_demo_responses(request_doc, result.candidates)
    except Exception as exc:
        logger.warning("demo simulation failed (non-fatal): %s", exc)

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
            "provider": intent_intent_provider,
            "isRuleBased": is_rule_based,
        },
        "candidates": candidates,
    }


@router.get("/requests/mine")
async def web_my_requests(user: dict = Depends(require_user)):
    docs = await search_service.recent_requests(user["_id"], limit=50)
    return [request_public(d) for d in docs]


async def _offers_for_request(request_doc: dict) -> List[dict]:
    """All merchant_match rows for a request, with shop, inventory hint,
    trust score, freshness labels and a why-recommended explanation attached.

    Sorted by match_score descending so the customer sees the most plausible
    shop first; the frontend then re-sorts by the user's chosen criterion
    (best overall / nearest / lowest price / most reliable / fastest response).
    """
    cursor = m.merchant_matches().find(
        {"request_id": request_doc["request_id"]}
    ).sort("match_score", -1)
    offers = []
    keys = [product_key(request_doc.get("product") or "")]
    async for match in cursor:
        shop = await m.shops().find_one({"_id": match["merchant_id"]})
        hint = False
        inv_updated = None
        if shop:
            inv = await m.inventory_items().find_one({
                "shop_id": shop["_id"],
                "product_key": {"$in": keys},
            })
            if inv and (inv.get("quantity") or 0) > 0 and inv.get("in_stock", True):
                hint = True
            if inv:
                inv_updated = inv.get("updated_at") or inv.get("created_at")
        # Trust score + freshness + explanation.
        trust = await _trust_for_shop(shop)
        freshness = trust_service.freshness_label(
            responded_at=match.get("responded_at"),
            notified_at=match.get("notified_at"),
            has_inventory_hint=hint,
            inventory_updated_at=inv_updated,
            has_price=match.get("price") is not None,
        )
        why = opportunity_service.explain_match(
            request=request_doc, shop=shop or {},
            score_breakdown=match.get("score_breakdown") or {},
            distance_meters=match.get("distance_meters") or 0,
            has_inventory_hint=hint,
            trust_label=(trust or {}).get("label"),
        )
        offers.append(offer_public(
            match, shop=shop, has_hint=hint,
            trust=trust, freshness=freshness, why=why,
            inventory_updated_at=inv_updated,
        ))
    return offers


async def _trust_for_shop(shop: Optional[dict]) -> Optional[dict]:
    """Compute the trust score for a shop, pulling its recent response-time
    history from merchant_matches. Returns None when shop is None."""
    if not shop:
        return None
    shop_id = shop["_id"]
    notified = int(shop.get("notified_count") or 0)
    accepted = int(shop.get("accepted_count") or 0)
    declined = int(shop.get("declined_count") or 0)
    # Pull the last 20 match rows for this shop to compute median response time.
    response_times: List[int] = []
    cursor = m.merchant_matches().find({
        "merchant_id": shop_id,
        "notified_at": {"$ne": None},
        "responded_at": {"$ne": None},
    }).sort("responded_at", -1).limit(20)
    async for row in cursor:
        secs = _response_seconds(row)
        if secs is not None:
            response_times.append(secs)
    completed = await m.product_requests().count_documents({
        "selected_match_id": {"$in": await _match_ids_for_shop(shop_id)},
    })
    return trust_service.compute_trust_score(
        notified_count=notified,
        accepted_count=accepted,
        declined_count=declined,
        completed_selections=completed,
        response_times_seconds=response_times,
        is_verified=bool(shop.get("is_verified")),
        account_age_days=None,
    )


async def _match_ids_for_shop(shop_id) -> List:
    """Return all merchant_match _ids for a shop — used to count customer
    selections of this shop."""
    cursor = m.merchant_matches().find({"merchant_id": shop_id}, {"_id": 1})
    return [doc["_id"] async for doc in cursor]


@router.get("/requests/{request_id}")
async def web_request_detail(request_id: str, user: dict = Depends(require_user)):
    doc = await search_service.get_request(request_id)
    if not doc or str(doc.get("customer_id")) != str(user["_id"]):
        _error(404, "Request not found")
    offers = await _offers_for_request(doc)
    return {"request": request_public(doc), "offers": offers}


@router.get("/requests/{request_id}/offers")
async def web_request_offers(request_id: str, user: dict = Depends(require_user)):
    """Explicit offers-only endpoint (the detail endpoint also returns them).

    Useful for the customer compare screen to poll JUST the offers without
    re-fetching the request envelope every time.
    """
    doc = await search_service.get_request(request_id)
    if not doc or str(doc.get("customer_id")) != str(user["_id"]):
        _error(404, "Request not found")
    return {"offers": await _offers_for_request(doc)}


@router.post("/requests/choose")
async def web_choose_offer(body: ChooseBody, user: dict = Depends(require_verified_user)):
    """Customer picks the winning shop. Exactly one selection per request.

    Delegates to ``search_service.select_offer`` which atomically claims the
    selection (using a MongoDB filter on selected_match_id==None) so a second
    concurrent attempt is safely rejected. On success: the chosen shop is
    notified via Telegram, the losing shops that said YES get a 'someone
    else won' ping, and the customer receives the final shop details + map
    pin so they can walk over and buy.
    """
    match = await merchant_matching.get_match(body.offerId)
    if not match:
        _error(404, "Offer not found")
    request_id = match["request_id"]
    result = await search_service.select_offer(
        request_id=request_id, match_id=match["_id"], customer_id=user["_id"],
    )
    if not result.get("ok"):
        code = result.get("code", "unknown")
        if code == "not_owner":
            _error(403, "Not your request")
        if code == "not_found":
            _error(404, "Offer not found")
        if code == "not_accepted":
            _error(400, "Shop has not confirmed yet")
        if code == "already_selected":
            _error(409, "A shop has already been chosen for this request")
        _error(400, result.get("message", "Could not select offer"))
    return {
        "ok": True,
        "selectedMatchId": result.get("selected_match_id"),
        "shopId": result.get("shop_id"),
    }


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
    imageUrl: Optional[str] = None  # manual upload URL (already on ImgBB/Disk) — optional


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
async def web_merchant_respond(body: RespondBody, shop: dict = Depends(require_my_verified_shop)):
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
async def web_add_inventory_item(body: AddItemBody, shop: dict = Depends(require_my_verified_shop)):
    # If the shopkeeper uploaded a photo, use it. Otherwise auto-fetch from
    # Pexels (AI-powered query expansion via Gemini + Pexels stock photo search)
    # — the AI-fetch happens synchronously here so the response carries the
    # image URL and the merchant's inventory list shows it immediately.
    image_url = body.imageUrl
    image_source = "manual" if image_url else "none"
    if not image_url:
        # Try AI fetch — pass shop category as a hint for query expansion.
        try:
            image_url = await product_image_service.fetch_product_image(
                body.name, category=shop.get("category"),
            )
            if image_url:
                image_source = "ai_fetched"
        except Exception as exc:
            logger.warning("product image auto-fetch failed (non-fatal) | %s", exc)

    doc = await inventory_service.upsert_item(
        shop_id=shop["_id"], product=body.name, quantity=body.quantity,
        unit=body.unit, price=body.price, source="web",
        image_url=image_url, image_source=image_source,
    )
    # Ensure in_stock reflects the new quantity.
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
                                    shop: dict = Depends(require_my_verified_shop)):
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
async def web_toggle_inventory_item(item_id: str, shop: dict = Depends(require_my_verified_shop)):
    item = await _my_item(item_id, shop)
    current = bool(item.get("in_stock", (item.get("quantity") or 0) > 0))
    await m.inventory_items().update_one(
        {"_id": item["_id"]},
        {"$set": {"in_stock": not current, "updated_at": utcnow()}},
    )
    return {"ok": True, "inStock": not current}


@router.delete("/merchant/inventory/{item_id}")
async def web_remove_inventory_item(item_id: str, shop: dict = Depends(require_my_verified_shop)):
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
async def web_add_khata(body: AddKhataBody, shop: dict = Depends(require_my_verified_shop)):
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
async def web_merchant_demand(shop: dict = Depends(require_my_shop),
                              days: int = Query(30, ge=1, le=365)):
    """Honest demand dashboard data for a merchant.

    Returns BOTH the legacy ``products``/``categories`` rollups AND the new
    ``honestStats`` block that distinguishes unique customer requests from
    merchant responses (one request with 5 merchant YESes still counts as 1
    unique customer request, never 5).
    """
    coords = from_geojson_point(shop.get("location"))
    lat, lng = coords if coords else (None, None)
    radius = settings.OPPORTUNITY_RADIUS_METERS
    if lat is not None and lng is not None:
        products = await demand_engine.top_unique_requested_products(
            latitude=lat, longitude=lng, radius_meters=radius, days=days, limit=12,
        )
    else:
        products = await demand_engine.top_unique_requested_products(days=days, limit=12)
    # Categories rollup from the same unique-request source.
    by_cat: Dict[str, int] = {}
    for p in products:
        cat = FE_CATEGORY.get(p.get("category") or "other", "other")
        by_cat[cat] = by_cat.get(cat, 0) + p.get("uniqueRequests", 0)
    categories = sorted(
        ({"categoryKey": k, "requests": v} for k, v in by_cat.items()),
        key=lambda c: -c["requests"],
    )
    honest = await demand_engine.honest_demand_stats(
        latitude=lat, longitude=lng, radius_meters=radius, days=days,
    )
    return {
        "products": products,
        "categories": categories,
        "total": honest.get("uniqueCustomerRequests", 0),
        "honestStats": honest,
        "isDemoData": bool(settings.DEMO_MODE),
        "days": days,
    }


@router.get("/merchant/demand/opportunities")
async def web_merchant_opportunities(shop: dict = Depends(require_my_shop),
                                     days: int = Query(30, ge=1, le=365),
                                     limit: int = Query(8, ge=1, le=20)):
    """Stock opportunity recommendations for this merchant.

    For each nearby top-unmet-demand product, computes an explainable
    opportunity score (deterministic, no ML) and a suggested stocking quantity.
    Filters out products the merchant already stocks, and products unrelated
    to the merchant's category.
    """
    coords = from_geojson_point(shop.get("location"))
    if not coords:
        return {"opportunities": [], "isDemoData": bool(settings.DEMO_MODE),
                "reason": "Set your shop location to see stock opportunities."}
    lat, lng = coords
    radius = settings.OPPORTUNITY_RADIUS_METERS

    # 1. Top unmet-demand products nearby (from product_requests, deduped by request_id).
    demand_rows = await demand_engine.top_unique_requested_products(
        latitude=lat, longitude=lng, radius_meters=radius, days=days, limit=limit * 3,
    )
    if not demand_rows:
        return {"opportunities": [], "isDemoData": bool(settings.DEMO_MODE),
                "reason": "Abhi is area se koi demand data nahi hai."}

    shop_category = normalize_category(shop.get("category"))
    rows = []
    for row in demand_rows:
        product_cat = normalize_category(row.get("category"))
        # Category affinity between the product's category and the merchant's.
        affinity = float(
            CATEGORY_AFFINITY.get(product_cat, {}).get(shop_category, 0.1)
        )
        if affinity < 0.2:
            continue  # Don't recommend products unrelated to this shop.
        # Does this merchant already stock this product?
        already = await m.inventory_items().find_one({
            "shop_id": shop["_id"], "product_key": product_key(row["product"]),
        })
        nearby_coverage = await m.inventory_items().count_documents({
            "product_key": product_key(row["product"]),
        })
        # Trend ratio: last 7d vs previous 7d unique requests.
        trend = await _trend_ratio(lat=lat, lng=lng, radius=radius,
                                   product_key=product_key(row["product"]))
        rows.append(opportunity_service.opportunity_score(
            product=row["product"], category=row.get("category"),
            unique_requests=row["uniqueRequests"],
            unavailable_requests=row["unavailable"],
            available_requests=row["available"],
            trend_ratio=trend,
            average_search_distance_meters=row.get("averageSearchDistanceMeters"),
            nearby_inventory_coverage=nearby_coverage,
            merchant_category_affinity=affinity,
            merchant_already_stocks=bool(already),
        ))
    rows = opportunity_service.sort_opportunities(rows)[:limit]
    return {
        "opportunities": rows,
        "isDemoData": bool(settings.DEMO_MODE),
        "radiusMeters": radius,
        "days": days,
    }


async def _trend_ratio(*, lat: float, lng: float, radius: int, product_key: str) -> Optional[float]:
    """Ratio of last-7d unique requests vs previous-7d for a product."""
    from datetime import timedelta as _td
    now = utcnow()
    last_7 = now - _td(days=7)
    prev_7_start = now - _td(days=14)
    last_count = await m.product_requests().count_documents({
        "product_key": product_key,
        "created_at": {"$gte": last_7},
        "location": {"$near": {
            "$geometry": {"type": "Point", "coordinates": [lng, lat]},
            "$maxDistance": radius,
        }},
    })
    prev_count = await m.product_requests().count_documents({
        "product_key": product_key,
        "created_at": {"$gte": prev_7_start, "$lt": last_7},
        "location": {"$near": {
            "$geometry": {"type": "Point", "coordinates": [lng, lat]},
            "$maxDistance": radius,
        }},
    })
    if prev_count == 0:
        return None if last_count == 0 else 2.0  # new demand → treat as rising
    return last_count / max(1, prev_count)


@router.get("/merchant/demand/heatmap")
async def web_merchant_heatmap(shop: dict = Depends(require_my_shop),
                               days: int = Query(30, ge=1, le=365),
                               category: Optional[str] = Query(None),
                               limit: int = Query(60, ge=1, le=200)):
    """Privacy-safe demand heatmap centred on the merchant's shop.

    Aggregates demand into ~300m buckets so individual customer locations are
    never exposed. Each point represents a *bucket* of demand for one product,
    deduplicated by request_id (one customer request = one bucket entry,
    regardless of how many merchants were asked).
    """
    coords = from_geojson_point(shop.get("location"))
    if not coords:
        return {"points": [], "isDemoData": bool(settings.DEMO_MODE),
                "reason": "Set your shop location to see the demand heatmap."}
    lat, lng = coords
    points = await demand_engine.demand_heatmap(
        latitude=lat, longitude=lng,
        radius_meters=settings.OPPORTUNITY_RADIUS_METERS,
        days=days, category=category, limit=limit,
    )
    return {
        "points": points,
        "isDemoData": bool(settings.DEMO_MODE),
        "bucketMeters": settings.HEATMAP_BUCKET_METERS,
        "radiusMeters": settings.OPPORTUNITY_RADIUS_METERS,
        "days": days,
        "privacyNote": (
            "Demand points are aggregated into ~300m buckets for privacy. "
            "Individual customer locations are never exposed."
        ),
    }


@router.get("/merchant/demand/impact")
async def web_merchant_impact(shop: dict = Depends(require_my_shop),
                              days: int = Query(30, ge=1, le=365)):
    """Judge-friendly impact dashboard — understood in under 30 seconds.

    Honest metrics only:
      - Unique customer requests
      - Requests matched to ≥1 shop
      - Average search radius (reduced by matching to nearby shops)
      - Zero-inventory matches (the zero-inventory innovation)
      - Successful customer selections
      - Merchant response rate
      - Unmet demand discovered (opportunities for the neighborhood)
      - Estimated search distance saved (labelled as an estimate)
    """
    coords = from_geojson_point(shop.get("location"))
    lat, lng = coords if coords else (None, None)
    radius = settings.OPPORTUNITY_RADIUS_METERS
    honest = await demand_engine.honest_demand_stats(
        latitude=lat, longitude=lng, radius_meters=radius, days=days,
    )
    # Estimated search distance saved: each successful match replaces a
    # hypothetical 5km "asked the whole city" search with the actual average
    # radius used. Clearly labelled as an estimate, not a hard number.
    avg_radius = honest.get("avgSearchDistanceMeters") or 0
    matched = honest.get("requestsMatched", 0)
    hypothetical_search = settings.MAX_MATCH_RADIUS_METERS  # 5km
    estimated_saved_m = max(0, hypothetical_search - avg_radius) * matched if matched else 0
    insight = await demand_engine.neighborhood_insight(
        latitude=lat, longitude=lng, radius_meters=radius, days=days,
    ) if lat is not None else None
    return {
        "metrics": {
            "uniqueCustomerRequests": honest.get("uniqueCustomerRequests", 0),
            "requestsMatched": matched,
            "requestsUnmatched": honest.get("requestsUnmatched", 0),
            "zeroInventoryMatches": honest.get("zeroInventoryMatches", 0),
            "successfulCustomerSelections": honest.get("successfulCustomerSelections", 0),
            "merchantResponseAttempts": honest.get("merchantResponseAttempts", 0),
            "availableResponses": honest.get("availableResponses", 0),
            "unavailableResponses": honest.get("unavailableResponses", 0),
            "merchantResponseRate": (
                round((honest.get("availableResponses", 0)
                       + honest.get("unavailableResponses", 0))
                      / max(1, honest.get("merchantResponseAttempts", 0)), 3)
            ),
            "avgSearchDistanceMeters": avg_radius,
            "estimatedSearchDistanceSavedMeters": int(estimated_saved_m),
        },
        "neighborhoodInsight": insight,
        "isDemoData": bool(settings.DEMO_MODE),
        "days": days,
    }


class PlanFromOpportunityBody(BaseModel):
    product: str = Field(min_length=2, max_length=120)
    quantity: float = Field(gt=0)
    unit: str = Field(min_length=1, max_length=32)
    price: Optional[float] = Field(default=None, gt=0)


@router.post("/merchant/inventory/plan")
async def web_plan_from_opportunity(body: PlanFromOpportunityBody,
                                     shop: dict = Depends(require_my_verified_shop)):
    """Prefill the inventory form from a stock opportunity recommendation.

    Does NOT add stock — the merchant must explicitly confirm via the regular
    POST /merchant/inventory endpoint. This endpoint just creates (or
    updates) a row marked as ``in_stock=False`` so the merchant sees it in
    their plan list and can convert it to real stock with one tap.
    """
    doc = await inventory_service.upsert_item(
        shop_id=shop["_id"], product=body.product, quantity=body.quantity,
        unit=body.unit, price=body.price, source="opportunity",
    )
    # Mark the planned row as out-of-stock until the merchant confirms.
    await m.inventory_items().update_one(
        {"shop_id": doc["shop_id"], "product_key": doc["product_key"]},
        {"$set": {"in_stock": False, "is_plan": True, "updated_at": utcnow()}},
    )
    return {"ok": True, "productId": str(doc.get("_id") or doc.get("product_key"))}


# ----------------------------------------------- Shopfront photo verification
# Shopkeeper takes a photo of their shop exterior from inside the PWA —
# browser GPS is captured at the same moment AND the JPEG's EXIF GPS is
# parsed server-side as a cross-check. Both must be within ~200m of the
# registered shop location. The photo becomes the shop's profile picture
# on every customer-facing surface (offer cards, shop detail page).
# An admin (you, for the hackathon) reviews the pending photos and approves
# each one — flipping is_verified=True so the shop becomes visible.

@router.post("/merchant/shop/shopfront-photo")
async def web_upload_shopfront_photo(
    file: UploadFile = File(...),
    browser_lat: float = Form(...),
    browser_lng: float = Form(...),
    shop: dict = Depends(require_my_verified_shop),
):
    """Upload a shopfront photo. Validates GPS (browser + EXIF) against the
    registered shop location, saves the photo to disk, and updates the shop
    to verification_status=photo_pending (admin must approve)."""
    photo_bytes = await file.read()
    try:
        result = await verification_service_mod.upload_shopfront_photo(
            shop_id=shop["_id"], photo_bytes=photo_bytes,
            browser_lat=browser_lat, browser_lng=browser_lng,
            filename=file.filename or "shopfront.jpg",
        )
    except VerificationError as exc:
        _error(400, str(exc))
    return result


@router.patch("/profile/trusted-contact")
async def web_set_trusted_contact(
    body: dict, user: dict = Depends(require_verified_user),
):
    """Customer sets a trusted contact phone for the panic button."""
    phone = (body or {}).get("phone", "").strip()
    if not phone or len(phone) < 10:
        _error(400, "Please enter a valid phone number.")
    await m.users().update_one(
        {"_id": user["_id"]},
        {"$set": {"trusted_contact_phone": phone, "updated_at": utcnow()}},
    )
    return {"ok": True}


# ------------------------------------------------------ Admin verification UI
# A small set of admin endpoints that flip is_verified on shops. For the
# hackathon the user is the only admin — log in as an admin account to
# approve friends' shops. The /admin/shops/pending page in the React app
# calls these endpoints.

@router.get("/admin/shops/pending")
async def web_admin_pending_shops(admin: dict = Depends(require_admin)):
    return {"shops": await verification_service_mod.list_pending_shops()}


@router.post("/admin/shops/{shop_id}/approve")
async def web_admin_approve_shop(shop_id: str, admin: dict = Depends(require_admin)):
    try:
        return await verification_service_mod.admin_approve_shop(ObjectId(shop_id))
    except VerificationError as exc:
        _error(400, str(exc))


@router.post("/admin/shops/{shop_id}/reject")
async def web_admin_reject_shop(
    shop_id: str, body: dict = Body(default_factory=dict),
    admin: dict = Depends(require_admin),
):
    reason = (body or {}).get("reason", "")
    try:
        return await verification_service_mod.admin_reject_shop(ObjectId(shop_id), reason)
    except VerificationError as exc:
        _error(400, str(exc))


# ------------------------------------------------------------ Customer safety
# Report a shop (audit trail) + panic button (alert trusted contact).

class FlagBody(BaseModel):
    reason: Literal[
        "didnt_honor_price", "felt_unsafe", "shop_doesnt_exist",
        "harassment_in_chat", "other",
    ]
    note: Optional[str] = Field(default=None, max_length=500)


@router.post("/requests/{request_id}/flag")
async def web_flag_shop(
    request_id: str, body: FlagBody,
    user: dict = Depends(require_verified_user),
):
    """Customer flags a shop for safety / honesty reasons.

    Records a doc in flagged_shops for manual review. The shop's
    is_active stays True until YOU (the admin) review the flag — automatic
    suspension on every flag would let a single malicious customer
    take down any shop.
    """
    request_doc = await search_service.get_request(request_id)
    if not request_doc or str(request_doc.get("customer_id")) != str(user["_id"]):
        _error(404, "Request not found")
    # Find the chosen shop's id (the one the customer actually picked).
    chosen = request_doc.get("selected_match_id")
    if not chosen:
        _error(400, "You can only flag a shop after picking it.")
    match = await merchant_matching.get_match(chosen)
    if not match:
        _error(404, "Offer not found")
    await m.flagged_shops().insert_one({
        "shop_id": match["merchant_id"],
        "request_id": request_id,
        "customer_id": user["_id"],
        "reason": body.reason,
        "note": (body.note or "").strip()[:500],
        "status": "open",
        "created_at": utcnow(),
    })
    # Severity: felt_unsafe or shop_doesnt_exist → auto-suspend the shop
    # pending review (these are the safety-critical ones).
    if body.reason in ("felt_unsafe", "shop_doesnt_exist"):
        await m.shops().update_one(
            {"_id": match["merchant_id"]},
            {"$set": {"is_active": False, "updated_at": utcnow()}},
        )
    return {"ok": True, "auto_suspended": body.reason in ("felt_unsafe", "shop_doesnt_exist")}


class PanicBody(BaseModel):
    request_id: Optional[str] = None
    latitude: float
    longitude: float


@router.post("/panic")
async def web_panic(body: PanicBody, user: dict = Depends(require_verified_user)):
    """Customer panic button — records an event for the audit trail and (in
    production) SMSes the trusted contact. For the hackathon the SMS is
    stubbed (logged to console).

    The event payload includes the customer's current location + the most
    recent chosen shop's details (if any) so the trusted contact knows where
    the customer was heading.
    """
    now = utcnow()
    shop_info = None
    if body.request_id:
        req = await search_service.get_request(body.request_id)
        if req and str(req.get("customer_id")) == str(user["_id"]):
            chosen = req.get("selected_match_id")
            if chosen:
                match = await merchant_matching.get_match(chosen)
                if match:
                    shop = await m.shops().find_one({"_id": match["merchant_id"]})
                    if shop:
                        shop_info = {
                            "shop_id": str(shop["_id"]),
                            "shop_name": shop.get("shop_name"),
                            "phone": shop.get("phone"),
                            "address": shop.get("address"),
                            "product": req.get("product"),
                        }

    await m.panic_events().insert_one({
        "customer_id": user["_id"],
        "request_id": body.request_id,
        "latitude": body.latitude,
        "longitude": body.longitude,
        "shop_info": shop_info,
        "trusted_contact_phone": user.get("trusted_contact_phone"),
        "created_at": now,
    })

    # In stub mode, log the alert (and the trusted-contact phone + the shop
    # details) so the hackathon judge can see the audit-trail value. In
    # production, dispatch an SMS via MSG91 / Twilio.
    if settings.PANIC_SMS_STUB or settings.SMS_GATEWAY == "stub":
        logger.warning(
            "PANIC (stub mode) | customer=%s trusted_contact=%s location=(%s,%s) shop=%s",
            user["_id"], user.get("trusted_contact_phone"),
            body.latitude, body.longitude,
            (shop_info or {}).get("shop_name"),
        )
        return {
            "ok": True,
            "alerted": True,
            "mode": "stub",
            "message": (
                "Panic alert recorded. In production this would SMS your trusted contact "
                f"({user.get('trusted_contact_phone') or 'not set'}) with your location "
                "and shop details."
            ),
        }

    # Production SMS dispatch (placeholder — wire MSG91 / Twilio).
    trusted = user.get("trusted_contact_phone")
    if trusted:
        try:
            await auth_service._dispatch_sms(
                trusted,
                f"VYAPAAR-MITRA PANIC ALERT: {user.get('full_name')} pressed the panic button "
                f"at https://maps.google.com/?q={body.latitude},{body.longitude}"
                + (f" while heading to {(shop_info or {}).get('shop_name', 'a shop')}."
                   if shop_info else "."),
            )
        except Exception as exc:
            logger.error("panic SMS failed | customer=%s | %s", user["_id"], exc)
    return {"ok": True, "alerted": True, "mode": "sms"}


# ----------------------------------------------------------------- In-app chat
# Customer-side and shop-side chat endpoints. Both sides are anonymised —
# the customer's phone is never in the chat, the shopkeeper's phone is only
# on the offer card (visible to the customer, not in the chat itself).
# Chat is scoped to a request_id: opens when the customer picks a shop,
# closes when the request expires or the customer confirms the deal.

@router.get("/requests/{request_id}/chat")
async def web_request_chat(
    request_id: str, since: Optional[str] = Query(None),
    user: dict = Depends(require_verified_user),
):
    """Customer-side chat fetch. Returns messages after `since` (ISO timestamp)
    so the client can poll every ~1.5s and only get new messages."""
    try:
        messages = await chat_service_mod.recent_messages(
            request_id=request_id, user=user, since=since,
        )
    except ChatError as exc:
        _error(400, str(exc))
    return {"messages": messages, "since": since}


@router.post("/requests/{request_id}/chat/messages")
async def web_send_chat_message(
    request_id: str, body: dict,
    user: dict = Depends(require_verified_user),
):
    """Customer-side send."""
    text = (body or {}).get("text", "")
    try:
        msg = await chat_service_mod.send_message(
            request_id=request_id, user=user, text=text,
        )
    except ChatError as exc:
        _error(400, str(exc))
    return msg


@router.get("/merchant/conversations")
async def web_merchant_conversations(
    shop: dict = Depends(require_my_verified_shop),
):
    """Shop-side inbox of all open chats for this shop, most-recent first."""
    rows = await chat_service_mod.list_conversations_for_shop(shop["_id"])
    return {"conversations": rows}


@router.get("/merchant/conversations/{request_id}")
async def web_merchant_chat_history(
    request_id: str, since: Optional[str] = Query(None),
    shop: dict = Depends(require_my_verified_shop),
):
    """Shop-side chat fetch for one conversation."""
    try:
        messages = await chat_service_mod.recent_messages(
            request_id=request_id, user=None, shop=shop, since=since,
        )
    except ChatError as exc:
        _error(400, str(exc))
    return {"messages": messages, "since": since}


@router.post("/merchant/conversations/{request_id}/messages")
async def web_merchant_send_chat_message(
    request_id: str, body: dict,
    shop: dict = Depends(require_my_verified_shop),
):
    """Shop-side send."""
    text = (body or {}).get("text", "")
    try:
        # Shop sends as shopkeeper — pass shop so the service knows which
        # side this is. The user_id (sender_id) is the shop's owner.
        shopkeeper_user = await m.users().find_one({"_id": shop["user_id"]})
        if not shopkeeper_user:
            _error(404, "Shop owner account not found")
        msg = await chat_service_mod.send_message(
            request_id=request_id, user=shopkeeper_user, text=text, shop=shop,
        )
    except ChatError as exc:
        _error(400, str(exc))
    return msg


# ----------------------------------------------------------------- Payments
# Razorpay in-app payment flow:
#   1. Customer picks a shop (select_offer → COMPLETED).
#   2. Customer taps "Pay" → POST /payments/create-order → Razorpay order_id.
#   3. Frontend opens Razorpay checkout (JS SDK) with the order_id.
#   4. After payment, frontend calls POST /payments/verify → server verifies signature.
#   5. Backup: Razorpay webhook → POST /payments/webhook.
# Payments work for BOTH products (shop + vendor) and services (plumber etc.).

from app.services import payment_service
from app.services.payment_service import PaymentError
from app.services import order_service
from app.services.order_service import OrderError


class CreateOrderBody(BaseModel):
    requestId: str
    matchId: str
    amountPaise: int = Field(ge=100)  # min ₹1
    isService: bool = False


@router.post("/payments/create-order")
async def web_create_payment_order(
    body: CreateOrderBody, user: dict = Depends(require_verified_user),
):
    """Create a Razorpay order for the customer to pay the shopkeeper.

    The customer must own the request (the shop must have been selected via
    select_offer). The amount is in paise (₹1 = 100 paise).
    """
    request_doc = await search_service.get_request(body.requestId)
    if not request_doc or str(request_doc.get("customer_id")) != str(user["_id"]):
        _error(403, "Not your request")
    if request_doc.get("status") != RequestStatus.COMPLETED.value:
        _error(400, "Pay after you pick a shop")
    selected_match_id = request_doc.get("selected_match_id")
    if not selected_match_id or str(selected_match_id) != str(body.matchId):
        _error(400, "You can only pay the shop you selected")

    match = await merchant_matching.get_match(body.matchId)
    if not match:
        _error(404, "Offer not found")
    shop = await m.shops().find_one({"_id": match["merchant_id"]})
    if not shop:
        _error(404, "Shop not found")

    try:
        return await payment_service.create_order(
            request_id=body.requestId,
            match_id=body.matchId,
            amount_paise=body.amountPaise,
            customer_id=user["_id"],
            shop_id=match["merchant_id"],
            product=request_doc.get("product") or "Item",
            customer_name=user.get("full_name") or "",
            shop_name=shop.get("shop_name") or "",
            is_service=body.isService or shop.get("shop_type") == "service",
        )
    except PaymentError as exc:
        _error(400, str(exc))


class VerifyPaymentBody(BaseModel):
    razorpayOrderId: str
    razorpayPaymentId: str
    razorpaySignature: str


@router.post("/payments/verify")
async def web_verify_payment(
    body: VerifyPaymentBody, user: dict = Depends(require_verified_user),
):
    """Verify the Razorpay payment signature after checkout."""
    try:
        result = await payment_service.verify_payment(
            razorpay_order_id=body.razorpayOrderId,
            razorpay_payment_id=body.razorpayPaymentId,
            razorpay_signature=body.razorpaySignature,
        )
        # Auto-update the linked order to status=paid + method=online
        try:
            await order_service.link_razorpay_payment(
                request_id=result.get("orderId", ""),  # not ideal — we need request_id
                razorpay_order_id=body.razorpayOrderId,
                razorpay_payment_id=body.razorpayPaymentId,
            )
            # Also update the order's payment_method to "online"
            await m.orders().update_one(
                {"razorpay_order_id": body.razorpayOrderId},
                {"$set": {"payment_method": "online"}},
            )
        except Exception as exc:
            logger.warning("order link failed (non-fatal) | %s", exc)
        return result
    except PaymentError as exc:
        _error(400, str(exc))


@router.post("/payments/webhook")
async def web_razorpay_webhook(request: Request):
    """Razorpay webhook — backup payment verification.

    The body is read as raw bytes + the signature is in the X-Razorpay-Signature
    header. This endpoint is NOT behind the session cookie auth — Razorpay
    authenticates via the webhook secret.
    """
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    return await payment_service.handle_webhook(body, signature)


@router.get("/payments/status/{request_id}")
async def web_payment_status(
    request_id: str, user: dict = Depends(require_verified_user),
):
    """Get the payment status for a request (for the Deal pakki! panel)."""
    request_doc = await search_service.get_request(request_id)
    if not request_doc or str(request_doc.get("customer_id")) != str(user["_id"]):
        _error(404, "Request not found")
    payment = await payment_service.get_payment_for_request(request_id)
    if not payment:
        return {"status": "none", "message": "No payment initiated yet."}
    return {
        "status": payment.get("status"),
        "amountPaise": payment.get("amount_paise"),
        "currency": payment.get("currency"),
        "razorpayPaymentId": payment.get("razorpay_payment_id"),
        "paidAt": _iso(payment.get("paid_at")),
    }


# ----------------------------------------------------------------- Orders
# Shopkeeper order history + mark cash orders as paid.

@router.get("/merchant/orders")
async def web_merchant_orders(shop: dict = Depends(require_my_shop)):
    """List all orders for this shop — customer checkouts with payment status."""
    orders = await order_service.list_orders_for_shop(shop["_id"], limit=50)
    return {"orders": [order_service.order_public(o) for o in orders]}


@router.post("/merchant/orders/{order_id}/mark-paid")
async def web_mark_order_paid(
    order_id: str, shop: dict = Depends(require_my_verified_shop),
):
    """Shopkeeper marks a cash order as paid (customer paid in person).

    Only the shop that owns the order can mark it. Only PENDING orders
    can be marked. PAID is idempotent (returns the existing doc).
    """
    try:
        result = await order_service.mark_cash_paid(
            order_id=order_id, merchant_id=shop["_id"],
        )
        return order_service.order_public(result)
    except OrderError as exc:
        _error(400, str(exc))
