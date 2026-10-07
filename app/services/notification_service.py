"""Telegram delivery layer.

The bot instance is injected at startup so services stay free of Telegram imports
beyond this module.
"""
from typing import Dict, List, Optional

from app.database import mongo as m
from app.models.user import utcnow
from app.utils.geo import humanize_distance, navigation_link
from app.utils.logging import get_logger

logger = get_logger(__name__)

_bot = None


def set_bot(bot) -> None:
    global _bot
    _bot = bot


def get_bot():
    return _bot


def merchant_response_markup(match_id):
    """YES/NO buttons for a merchant request.

    Lives here rather than in the services that trigger it, so Telegram types
    stay confined to this delivery module.
    """
    from app.bot.keyboards import merchant_response_keyboard

    return merchant_response_keyboard(match_id)


async def send_location(telegram_user_id: Optional[int], latitude: float, longitude: float, *,
                        title: Optional[str] = None, address: Optional[str] = None,
                        kind: str = "shop_location") -> bool:
    """Drop a real Telegram map pin so the customer can tap straight into Maps.

    A venue is nicer than a bare location (it shows the shop name), but it needs
    both a title and an address, so we fall back to a plain pin when the shop
    never filled in an address.
    """
    if not telegram_user_id:
        return False
    if _bot is None:
        logger.warning("Telegram bot not initialised; location dropped (kind=%s)", kind)
        return False
    try:
        if title and address:
            await _bot.send_venue(
                chat_id=telegram_user_id, latitude=float(latitude), longitude=float(longitude),
                title=title, address=address,
            )
        else:
            await _bot.send_location(
                chat_id=telegram_user_id, latitude=float(latitude), longitude=float(longitude),
            )
        await _log(telegram_user_id, kind, "sent")
        return True
    except Exception as exc:
        logger.warning("Telegram location send failed (%s): %s | %s",
                       kind, exc.__class__.__name__, exc)
        await _log(telegram_user_id, kind, f"failed:{exc.__class__.__name__}")
        return False


async def send_message(telegram_user_id: Optional[int], text: str, *,
                       reply_markup=None, kind: str = "generic") -> bool:
    if not telegram_user_id:
        return False
    if _bot is None:
        logger.warning("Telegram bot not initialised; message dropped (kind=%s)", kind)
        return False
    try:
        await _bot.send_message(
            chat_id=telegram_user_id, text=text, reply_markup=reply_markup,
            parse_mode=None, disable_web_page_preview=True,
        )
        await _log(telegram_user_id, kind, "sent")
        logger.info("notification sent | kind=%s to=%s", kind, telegram_user_id)
        return True
    except Exception as exc:
        logger.warning("Telegram send failed (%s): %s", kind, exc.__class__.__name__)
        await _log(telegram_user_id, kind, f"failed:{exc.__class__.__name__}")
        return False


async def _log(telegram_user_id: int, kind: str, status: str) -> None:
    try:
        await m.notifications().insert_one({
            "telegram_user_id": telegram_user_id,
            "kind": kind,
            "status": status,
            "created_at": utcnow(),
        })
    except Exception:
        pass  # logging a notification must never break the flow


async def broadcast(telegram_user_ids: List[int], text: str, kind: str = "broadcast") -> int:
    sent = 0
    for uid in telegram_user_ids:
        if await send_message(uid, text, kind=kind):
            sent += 1
    return sent


def format_merchant_request(request: Dict, distance_text: str) -> str:
    product = request.get("product") or "Product"
    quantity = request.get("quantity", 1)
    unit = request.get("unit", "piece")
    lines = [
        "🛍️ NEW CUSTOMER REQUEST",
        "",
        f"📍 Approximately {distance_text} away",
        "",
        f"🔧 {product}",
        f"📦 Quantity: {quantity} {unit}",
    ]
    if request.get("brand"):
        lines.append(f"🏷️ Brand: {request['brand']}")
    if request.get("description"):
        lines.append(f"ℹ️ {request['description']}")
    if request.get("uncertain"):
        lines.append("\n⚠️ Customer ka description thoda unclear tha.")
    lines += ["", "Do you have it?"]
    return "\n".join(lines)


def format_customer_match(shop_name: str, distance_text: str, product: str,
                          price: Optional[float], phone: Optional[str] = None,
                          address: Optional[str] = None,
                          latitude: Optional[float] = None,
                          longitude: Optional[float] = None) -> str:
    lines = [
        "🎉 Nearby match found!",
        "",
        f"🏪 {shop_name}",
        f"📍 {distance_text} away",
        f"🔧 {product}",
    ]
    if price is not None:
        lines.append(f"💰 ₹{price:g}")
    if phone:
        lines.append(f"📞 {phone}")
    if address:
        lines.append(f"🏠 {address}")
    if latitude is not None and longitude is not None:
        lines += ["", f"🧭 Directions: {navigation_link(latitude, longitude)}"]
    lines += ["", "Please contact the merchant to purchase.",
              "(Shop ne availability confirm ki hai — order abhi place nahi hua hai.)"]
    return "\n".join(lines)


def format_customer_offers(*, product: str, offers: List[Dict],
                           public_base_url: str = "", request_id: str = "") -> str:
    """Batched 'you have N offers' notification — sent once when the offer
    window elapses so the customer can compare instead of taking the fastest gun.

    Each offer dict is the row returned by merchant_matching.accepted_offers().
    """
    n = len(offers)
    if n == 0:
        return f"📭 Abhi tak koi offer nahi aaya — {product} ke liye."
    if n == 1:
        head = f"📨 1 dukaan ne {product} ke liye haan bola!"
    else:
        head = f"📨 {n} dukaano ne {product} ke liye haan bola!"
    lines = [head, ""]
    for offer in offers:
        price = f" · ₹{offer['price']:g}" if offer.get("price") is not None else ""
        lines.append(
            f"✅ {offer.get('shop_name', 'Shop')}"
            f" — {humanize_distance(offer.get('distance_meters') or 0)} door{price}"
        )
    lines += ["", "Sabhi offers compare karke best dukaan chunein:"]
    if public_base_url and request_id:
        lines.append(f"{public_base_url}/search?q={product}&type=text&rid={request_id}")
    lines += ["", "(Order abhi place nahi hua — dukaan ne sirf availability confirm ki hai.)"]
    return "\n".join(lines)


def format_customer_selection(*, shop_name: str, product: str,
                              price: Optional[float], phone: Optional[str] = None,
                              address: Optional[str] = None,
                              latitude: Optional[float] = None,
                              longitude: Optional[float] = None,
                              distance_meters: float = 0.0) -> str:
    """Final message the customer sees AFTER picking a shop — gives them the
    full shop details + a map pin so they can walk over / call."""
    lines = [
        "✅ Deal pakki! Aapki choice:",
        "",
        f"🏪 {shop_name}",
        f"📍 {humanize_distance(distance_meters or 0)} away",
        f"🔧 {product}",
    ]
    if price is not None:
        lines.append(f"💰 ₹{price:g}")
    if phone:
        lines.append(f"📞 {phone}")
    if address:
        lines.append(f"🏠 {address}")
    if latitude is not None and longitude is not None:
        lines += ["", f"🧭 Directions: {navigation_link(latitude, longitude)}"]
    lines += ["", "Dukaan pe jaake le lo — ya call karke rakhwa lo.",
              "(Order formalise nahi hua hai — sirf availability pakki hui.)"]
    return "\n".join(lines)


def compare_offers_markup(web_url: str):
    """Single 'Compare offers' URL button — opens the web compare screen."""
    from app.bot.keyboards import compare_offers_keyboard
    return compare_offers_keyboard(web_url)
