"""Search orchestration: intent -> request -> matching -> notification -> result.

Every input type (text, voice, image) funnels through create_request(). Telegram
handlers contain no business logic; they call into here.
"""
from typing import Dict, List, Optional, Tuple

from bson import ObjectId
from app.config.settings import settings
from app.database import mongo as m
from app.models.merchant_match import MatchStatus, build_match_document
from app.models.product_request import RequestStatus, build_request_document
from app.models.user import utcnow
from app.schemas.intent import ProductIntent
from app.schemas.match import MatchResult
from app.services import browse_service, demand_engine, merchant_matching, notification_service
from app.utils.geo import from_geojson_point, haversine_meters, humanize_distance
from app.utils.logging import get_logger, new_request_id

logger = get_logger(__name__)


async def create_request(*, intent: ProductIntent, customer_id, telegram_user_id: Optional[int],
                         latitude: float, longitude: float, input_type: str = "text",
                         raw_text: str = "", transcript: str = "",
                         max_radius_meters: Optional[int] = None) -> Dict:
    if max_radius_meters is None:
        # customer_id here is the user id (see recent_requests / history_command),
        # which is exactly what get_search_radius expects.
        from app.services.location_service import get_search_radius
        max_radius_meters = await get_search_radius(customer_id)
    request_id = new_request_id()
    doc = build_request_document(
        request_id=request_id, customer_id=ObjectId(str(customer_id)),
        telegram_user_id=telegram_user_id, intent=intent.model_dump(),
        latitude=latitude, longitude=longitude, input_type=input_type,
        raw_text=raw_text, transcript=transcript, max_radius_meters=max_radius_meters,
    )
    await m.product_requests().insert_one(doc)
    logger.info("request created | %s product=%s radius=%sm", request_id, doc.get("product"),
                doc.get("max_radius_meters"))
    return doc


async def create_reservation(*, item: Dict, shop: Dict, customer_id, telegram_user_id: Optional[int],
                             customer_name: str, latitude: float, longitude: float,
                             quantity: Optional[float] = None) -> Dict:
    """A customer picked a specific item off a specific shop's shelf listing.

    This is still a request, not an order. Vyapaar-Mitra takes no payment and
    places no order: the merchant confirms the item is genuinely there, and the
    customer walks over and buys it. Routing it through the same request/match
    objects means one YES/NO loop, one demand signal and one audit trail for both
    search and browse.
    """
    intent = ProductIntent(
        intent="find_product",
        product=item.get("product"),
        category=shop.get("category") or "other",
        quantity=int(quantity or item.get("quantity") or 1) or 1,
        unit=item.get("unit") or "piece",
        brand=item.get("brand"),
        description="Reserved from the shop's own stock listing.",
        confidence=1.0,          # the customer chose it by hand — nothing was inferred
        provider="browse",
    )
    request = await create_request(
        intent=intent, customer_id=customer_id, telegram_user_id=telegram_user_id,
        latitude=latitude, longitude=longitude, input_type="browse",
        raw_text=f"reserve:{item.get('product')}",
    )
    await m.product_requests().update_one(
        {"request_id": request["request_id"]},
        {"$set": {"source": "browse", "reserved_item_id": item.get("_id"),
                  "reserved_shop_id": shop.get("_id")}},
    )

    distance = haversine_meters(
        latitude, longitude,
        *(from_geojson_point(shop.get("location")) or (latitude, longitude))
    )
    match_doc = build_match_document(
        request_id=request["request_id"], merchant_id=shop["_id"],
        distance_meters=distance, match_score=1.0,
        score_breakdown={"source": "browse_reservation"},
    )
    result = await m.merchant_matches().insert_one(match_doc)
    match_doc["_id"] = result.inserted_id

    text = browse_service.reservation_message(
        product=item.get("product") or "Item",
        quantity=float(intent.quantity), unit=intent.unit,
        customer_name=customer_name or "Ek customer",
        distance_text=humanize_distance(distance),
        price=item.get("price"),
    )
    sent = await notification_service.send_message(
        shop.get("telegram_user_id"), text,
        reply_markup=notification_service.merchant_response_markup(match_doc["_id"]),
        kind="reservation_request",
    )
    if sent:
        await merchant_matching.mark_notified(match_doc["_id"])
        await m.shops().update_one({"_id": shop["_id"]}, {"$inc": {"notified_count": 1}})
    await m.product_requests().update_one(
        {"request_id": request["request_id"]},
        {"$set": {
            "status": RequestStatus.OFFERED.value if sent else RequestStatus.MATCHING.value,
            "matched_count": 1, "updated_at": utcnow(),
        }},
    )
    logger.info("reservation created | %s shop=%s item=%s notified=%s",
                request["request_id"], shop.get("shop_name"), item.get("product"), sent)
    return {"request": request, "match": match_doc, "notified": sent}


async def get_request(request_id: str) -> Optional[Dict]:
    return await m.product_requests().find_one({"request_id": request_id})


async def set_status(request_id: str, status: str) -> None:
    await m.product_requests().update_one(
        {"request_id": request_id},
        {"$set": {"status": status, "updated_at": utcnow()}},
    )


async def run_matching(request: Dict, *, notify: bool = True) -> MatchResult:
    """Find plausible merchants and (optionally) notify them on Telegram."""
    await set_status(request["request_id"], RequestStatus.MATCHING.value)
    found = await merchant_matching.find_candidates(request)
    candidates = found["candidates"]

    if not candidates:
        await set_status(request["request_id"], RequestStatus.EXPIRED.value)
        return MatchResult(
            request_id=request["request_id"], product=request.get("product"),
            radius_used_meters=found["radius_used_meters"], candidates=[], notified=0,
            message="no_merchants",
        )

    matches = await merchant_matching.persist_matches(request["request_id"], candidates)
    by_merchant = {str(doc["merchant_id"]): doc for doc in matches}

    notified = 0
    if notify:
        for candidate in candidates:
            match_doc = by_merchant.get(candidate.merchant_id)
            if not match_doc or not candidate.telegram_user_id:
                continue
            text = notification_service.format_merchant_request(
                request, humanize_distance(candidate.distance_meters)
            )
            ok = await notification_service.send_message(
                candidate.telegram_user_id, text,
                reply_markup=notification_service.merchant_response_markup(match_doc["_id"]),
                kind="merchant_request",
            )
            if ok:
                notified += 1
                await merchant_matching.mark_notified(match_doc["_id"])
                await m.shops().update_one(
                    {"_id": ObjectId(candidate.merchant_id)}, {"$inc": {"notified_count": 1}}
                )

    await m.product_requests().update_one(
        {"request_id": request["request_id"]},
        {"$set": {
            "status": RequestStatus.OFFERED.value if notified else RequestStatus.MATCHING.value,
            "matched_count": len(candidates),
            "radius_used_meters": found["radius_used_meters"],
            "updated_at": utcnow(),
        }},
    )
    logger.info("matching done | %s candidates=%d notified=%d",
                request["request_id"], len(candidates), notified)
    return MatchResult(
        request_id=request["request_id"], product=request.get("product"),
        radius_used_meters=found["radius_used_meters"], candidates=candidates, notified=notified,
    )


async def handle_merchant_response(match_id, *, accepted: bool,
                                   price: Optional[float] = None) -> Tuple[bool, Optional[Dict]]:
    """Record YES/NO, write the demand event, and notify the customer on YES."""
    match = await merchant_matching.record_response(match_id, accepted=accepted, price=price)
    if not match:
        return False, None

    request = await get_request(match["request_id"])
    shop = await m.shops().find_one({"_id": match["merchant_id"]})
    if not request:
        return True, None

    await demand_engine.record_event(
        request=request, merchant_id=match["merchant_id"],
        response="available" if accepted else "unavailable", price=price,
    )
    await m.shops().update_one(
        {"_id": match["merchant_id"]},
        {"$inc": {"accepted_count" if accepted else "declined_count": 1}},
    )

    if accepted:
        await set_status(match["request_id"], RequestStatus.MATCHED.value)
        coordinates = from_geojson_point((shop or {}).get("location"))
        latitude, longitude = coordinates if coordinates else (None, None)
        text = notification_service.format_customer_match(
            (shop or {}).get("shop_name", "Shop"),
            humanize_distance(match.get("distance_meters") or 0),
            request.get("product") or "Product",
            price,
            (shop or {}).get("phone"),
            address=(shop or {}).get("address"),
            latitude=latitude,
            longitude=longitude,
        )
        await notification_service.send_message(
            request.get("telegram_user_id"), text, kind="customer_match"
        )
        # A tappable pin in the chat beats a URL for a first-time smartphone user.
        if latitude is not None and longitude is not None:
            await notification_service.send_location(
                request.get("telegram_user_id"), latitude, longitude,
                title=(shop or {}).get("shop_name", "Shop"),
                address=(shop or {}).get("address"),
            )
    else:
        await merchant_matching.set_cooldown(match["merchant_id"], request.get("product") or "")

    return True, {"match": match, "request": request, "shop": shop}


async def recent_requests(customer_id, limit: int = 10) -> List[Dict]:
    cursor = m.product_requests().find(
        {"customer_id": ObjectId(str(customer_id))}
    ).sort("created_at", -1).limit(limit)
    return [doc async for doc in cursor]


async def compare_prices(request: Dict, *, radius_meters: Optional[int] = None) -> List[Dict]:
    """Smart deal comparison.

    Only merchant-confirmed prices and stored inventory prices are shown, and the
    two are clearly distinguished. Prices are never invented.
    """
    from app.models.inventory import product_key

    product = request.get("product") or ""
    radius = radius_meters or settings.MAX_MATCH_RADIUS_METERS
    offers: List[Dict] = []

    # 1. Prices merchants confirmed in earlier accepted matches for this product.
    pipeline = [
        {"$match": {"product_key": product_key(product), "response": "available",
                    "price": {"$ne": None}}},
        {"$group": {"_id": "$merchant_id", "price": {"$last": "$price"},
                    "last_seen": {"$max": "$created_at"}}},
        {"$limit": 20},
    ]
    async for row in m.demand_events().aggregate(pipeline):
        shop = await m.shops().find_one({"_id": row["_id"]})
        if not shop:
            continue
        offers.append({
            "shop_name": shop.get("shop_name"), "price": row["price"],
            "source": "confirmed", "last_seen": row.get("last_seen"),
            "phone": shop.get("phone"),
        })

    # 2. Prices stored on optional inventory rows.
    cursor = m.inventory_items().find(
        {"product_key": product_key(product), "price": {"$ne": None}}
    ).limit(20)
    async for item in cursor:
        shop = await m.shops().find_one({"_id": item["shop_id"]})
        if not shop:
            continue
        if any(o["shop_name"] == shop.get("shop_name") for o in offers):
            continue
        offers.append({
            "shop_name": shop.get("shop_name"), "price": item["price"],
            "source": "stored", "last_seen": item.get("updated_at"),
            "phone": shop.get("phone"),
        })

    offers.sort(key=lambda o: o["price"])
    return offers[:10]


def format_price_comparison(product: str, offers: List[Dict]) -> str:
    if not offers:
        return (f"💰 {product}\n\nAbhi koi confirmed price available nahi hai.\n"
                "Main nearby shops se pooch sakta hoon — request bhejun?")
    lines = [f"💰 Nearby Prices — {product}", ""]
    for offer in offers:
        tag = "✅ confirmed" if offer["source"] == "confirmed" else "🗂️ shop record"
        lines.append(f"🏪 {offer['shop_name']} — ₹{offer['price']:g}  ({tag})")
    lines += ["", "Prices shops se aaye hain. Kharidne se pehle confirm kar lijiye."]
    return "\n".join(lines)


async def expire_stale_requests() -> int:
    """Housekeeping: close requests nobody answered."""
    from datetime import timedelta
    cutoff = utcnow() - timedelta(minutes=settings.REQUEST_EXPIRY_MINUTES)
    result = await m.product_requests().update_many(
        {"status": {"$in": [RequestStatus.OFFERED.value, RequestStatus.MATCHING.value]},
         "created_at": {"$lt": cutoff}},
        {"$set": {"status": RequestStatus.EXPIRED.value, "updated_at": utcnow()}},
    )
    await m.merchant_matches().update_many(
        {"status": {"$in": [MatchStatus.PENDING.value, MatchStatus.NOTIFIED.value]},
         "created_at": {"$lt": cutoff}},
        {"$set": {"status": MatchStatus.EXPIRED.value}},
    )
    return result.modified_count
