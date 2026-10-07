"""Search orchestration: intent -> request -> matching -> notification -> result.

Every input type (text, voice, image) funnels through create_request(). Telegram
handlers contain no business logic; they call into here.
"""
import asyncio
from datetime import timedelta
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
                                   price: Optional[float] = None,
                                   source: str = "real") -> Tuple[bool, Optional[Dict]]:
    """Record YES/NO, write the demand event, and decide when to notify the customer.

    Multi-offer flow (Priority 1):
      - The first YES starts an "offer window" (OFFER_WINDOW_SECONDS). The
        customer is NOT pinged immediately — we want several merchants to
        reply first so the customer can compare, not just take the fastest gun.
      - When the window elapses (or a later YES arrives after the window
        elapsed), the customer receives ONE batched "you have N offers"
        notification with a button to open the compare screen.
      - If OFFER_WINDOW_SECONDS == 0, the legacy per-YES behaviour is used
        (one notification per accepted offer) so demos / tests stay snappy.

    ``source`` is persisted on the match so the UI can label demo-simulated
    responses clearly ("Demo-simulated merchant response").
    """
    match = await merchant_matching.record_response(match_id, accepted=accepted, price=price)
    if not match:
        return False, None

    if source and source != "real":
        await m.merchant_matches().update_one(
            {"_id": match["_id"]},
            {"$set": {"source": source}},
        )
        match["source"] = source

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

    if not accepted:
        await merchant_matching.set_cooldown(match["merchant_id"], request.get("product") or "")
        # A NO never triggers the customer notification path.
        return True, {"match": match, "request": request, "shop": shop}

    # ----- Multi-offer window logic -----
    window = int(settings.OFFER_WINDOW_SECONDS or 0)
    if window <= 0:
        # Legacy: notify immediately, one message per YES.
        await _send_per_yes_customer_notification(request, match, shop)
        await m.product_requests().update_one(
            {"request_id": request["request_id"]},
            {"$set": {"status": RequestStatus.MATCHED.value, "updated_at": utcnow()}},
        )
        return True, {"match": match, "request": request, "shop": shop}

    # Windowed: only the FIRST YES starts the timer; later YES within the
    # window are silently accumulated. The customer sees them via the live
    # web polling, then gets the batched Telegram notification when the
    # window elapses.
    expires_at = request.get("offer_window_expires_at")
    now = utcnow()
    if not expires_at:
        # First YES — start the window.
        new_expires = now + timedelta(seconds=window)
        await m.product_requests().update_one(
            {"request_id": request["request_id"],
             "$or": [{"offer_window_expires_at": None},
                     {"offer_window_expires_at": {"$exists": False}}]},
            {"$set": {
                "offer_window_expires_at": new_expires,
                "status": RequestStatus.OFFERED.value,
                "updated_at": now,
            }},
        )
        # Schedule the flush. The task survives even if no more YES arrive.
        asyncio.create_task(_flush_offers_after_delay(request["request_id"], window))
        logger.info("offer window started | request=%s expires_in=%ds",
                    request["request_id"], window)
        return True, {"match": match, "request": request, "shop": shop}

    # Window already running or already elapsed.
    if expires_at <= now:
        # Window elapsed but customer hasn't been notified yet (e.g. the
        # scheduled task was lost). Flush right now.
        await flush_offers_to_customer(request["request_id"])
    # else: window still running; the scheduled task will fire when ready.
    return True, {"match": match, "request": request, "shop": shop}


async def _send_per_yes_customer_notification(request: Dict, match: Dict, shop: Optional[Dict]) -> None:
    """Legacy per-YES customer notification (used when OFFER_WINDOW_SECONDS=0)."""
    coordinates = from_geojson_point((shop or {}).get("location"))
    latitude, longitude = coordinates if coordinates else (None, None)
    text = notification_service.format_customer_match(
        (shop or {}).get("shop_name", "Shop"),
        humanize_distance(match.get("distance_meters") or 0),
        request.get("product") or "Product",
        match.get("price"),
        (shop or {}).get("phone"),
        address=(shop or {}).get("address"),
        latitude=latitude,
        longitude=longitude,
    )
    await notification_service.send_message(
        request.get("telegram_user_id"), text, kind="customer_match"
    )
    if latitude is not None and longitude is not None:
        await notification_service.send_location(
            request.get("telegram_user_id"), latitude, longitude,
            title=(shop or {}).get("shop_name", "Shop"),
            address=(shop or {}).get("address"),
        )


async def _flush_offers_after_delay(request_id: str, delay_seconds: int) -> None:
    """Asyncio task: sleep, then flush accumulated offers to the customer.

    Idempotent — flush_offers_to_customer itself refuses to double-notify,
    so even if multiple tasks end up scheduled for the same request, only
    one notification goes out.
    """
    try:
        await asyncio.sleep(max(1, delay_seconds))
        await flush_offers_to_customer(request_id)
    except Exception as exc:  # the scheduled flush must never break a request
        logger.warning("scheduled offer flush failed | %s | %s", request_id, exc)


async def flush_offers_to_customer(request_id: str) -> Optional[Dict]:
    """Send the batched 'you have N offers' notification, exactly once.

    - Reads all currently ACCEPTED offers for the request.
    - If the customer has already been notified (customer_notified_at set),
      does nothing (idempotent — safe to call from multiple paths).
    - Sends a single Telegram message with a button to open the web compare
      screen, where the customer can sort, compare, and pick.
    - Sets customer_notified_at and flips the request status to MATCHED.

    A late merchant response (after the customer has been notified) does
    NOT re-trigger this — the new YES still gets recorded and shown via the
    web polling, but no second Telegram message is sent.
    """
    request = await get_request(request_id)
    if not request:
        return None
    if request.get("customer_notified_at"):
        return None  # already notified — never double-ping
    if request.get("status") == RequestStatus.COMPLETED.value:
        return None  # customer already picked before the window elapsed

    offers = await merchant_matching.accepted_offers(request_id)
    if not offers:
        return None

    text = notification_service.format_customer_offers(
        product=request.get("product") or "Item",
        offers=offers,
        public_base_url=settings.PUBLIC_BASE_URL,
        request_id=request_id,
    )
    web_url = (
        f"{settings.PUBLIC_BASE_URL}/search"
        f"?q={request.get('product') or ''}&type=text&rid={request_id}"
    )
    await notification_service.send_message(
        request.get("telegram_user_id"), text,
        reply_markup=notification_service.compare_offers_markup(web_url),
        kind="customer_offers",
    )
    await m.product_requests().update_one(
        {"request_id": request_id},
        {"$set": {
            "customer_notified_at": utcnow(),
            "status": RequestStatus.MATCHED.value,
            "updated_at": utcnow(),
        }},
    )
    logger.info("offers flushed | request=%s offers=%d", request_id, len(offers))
    return {"notified": True, "offers": len(offers)}


async def select_offer(*, request_id: str, match_id, customer_id) -> Dict:
    """Customer picks the winning shop. Exactly-one, owner-only, persist-on-refresh.

    Returns a dict with the selected offer's shop details for the API layer to
    relay back to the customer (Telegram + web).

    Rules enforced here:
      - Request must belong to this customer (owner check).
      - The chosen match must belong to this request.
      - The chosen match must be ACCEPTED.
      - If a previous selection exists (selected_match_id is set), refuse.
      - On success: expire all other PENDING/NOTIFIED matches, set
        COMPLETED + selected_match_id + selected_at, notify the winning shop
        and the losing shops.
    """
    request = await get_request(request_id)
    if not request or str(request.get("customer_id")) != str(customer_id):
        return {"ok": False, "code": "not_owner", "message": "Not your request"}

    if request.get("status") == RequestStatus.COMPLETED.value and request.get("selected_match_id"):
        return {"ok": False, "code": "already_selected",
                "message": "You already picked a shop for this request",
                "selected_match_id": str(request["selected_match_id"])}

    match = await merchant_matching.get_match(match_id)
    if not match or match.get("request_id") != request_id:
        return {"ok": False, "code": "not_found", "message": "Offer not found"}
    if match.get("status") != MatchStatus.ACCEPTED.value:
        return {"ok": False, "code": "not_accepted",
                "message": "Shop has not confirmed yet"}

    # Atomically claim the selection. The filter on selected_match_id==None
    # means a concurrent second selection attempt is rejected safely.
    result = await m.product_requests().update_one(
        {"request_id": request_id,
         "$or": [{"selected_match_id": None}, {"selected_match_id": {"$exists": False}}]},
        {"$set": {
            "status": RequestStatus.COMPLETED.value,
            "selected_match_id": match["_id"],
            "selected_at": utcnow(),
            "updated_at": utcnow(),
        }},
    )
    if result.modified_count == 0:
        # Someone else won the race — re-read to surface the real winner.
        fresh = await get_request(request_id)
        return {"ok": False, "code": "already_selected",
                "message": "A shop has already been chosen for this request",
                "selected_match_id": str(fresh.get("selected_match_id")) if fresh else None}

    # Expire other pending offers (a late merchant can still reply, but their
    # offer won't be selectable anymore).
    await m.merchant_matches().update_many(
        {"request_id": request_id,
         "_id": {"$ne": match["_id"]},
         "status": {"$in": [MatchStatus.PENDING.value, MatchStatus.NOTIFIED.value]}},
        {"$set": {"status": MatchStatus.EXPIRED.value}},
    )

    shop = await m.shops().find_one({"_id": match["merchant_id"]})
    if shop and shop.get("telegram_user_id"):
        await notification_service.send_message(
            shop["telegram_user_id"],
            "🎉 Customer ne aapko chuna!\n\n"
            f"📦 {request.get('product') or 'Item'}"
            + (f" — ₹{match['price']:g}" if match.get("price") is not None else "")
            + "\nCustomer dukaan par aa sakta hai. Stock taiyaar rakhiye.",
            kind="customer_chose_you",
        )

    # Losing merchants who said YES get a single "customer chose another shop"
    # ping so they don't keep stock reserved.
    async for other in m.merchant_matches().find({
        "request_id": request_id,
        "_id": {"$ne": match["_id"]},
        "status": MatchStatus.ACCEPTED.value,
    }):
        other_shop = await m.shops().find_one({"_id": other["merchant_id"]})
        if other_shop and other_shop.get("telegram_user_id"):
            await notification_service.send_message(
                other_shop["telegram_user_id"],
                "📋 Customer ne kisi aur dukaan se kharid liya.\n\n"
                f"📦 {request.get('product') or 'Item'}\n"
                "Dhanyavaad — aapka YES demand data mein save hua hai.",
                kind="customer_chose_other",
            )

    # Final customer notification: full shop details + map pin.
    if request.get("telegram_user_id") and shop:
        coords = from_geojson_point(shop.get("location"))
        if coords:
            text = notification_service.format_customer_selection(
                shop_name=shop.get("shop_name", "Shop"),
                product=request.get("product") or "Item",
                price=match.get("price"),
                phone=shop.get("phone"),
                address=shop.get("address"),
                latitude=coords[0], longitude=coords[1],
                distance_meters=match.get("distance_meters") or 0,
            )
            await notification_service.send_message(
                request["telegram_user_id"], text,
                kind="customer_selection",
            )
            await notification_service.send_location(
                request["telegram_user_id"], coords[0], coords[1],
                title=shop.get("shop_name", "Shop"),
                address=shop.get("address"),
                kind="shop_location",
            )

    return {
        "ok": True,
        "selected_match_id": str(match["_id"]),
        "shop_id": str(match["merchant_id"]),
        "shop": shop,
        "match": match,
    }


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
