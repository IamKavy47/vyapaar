"""Browse nearby shops and their listed stock, then reserve an item.

Search pushes a question out to merchants. Browsing pulls back what merchants
have already published. Both end at the same place — a merchant confirming
availability — because a stored inventory row is a record, not a live promise.

Both also respect the same customer-controlled search radius (see
location_service.get_search_radius / range handling in customer.py): a shop
list that silently used a different distance than the one the customer set
under 📏 Range would be confusing and hard to reason about.
"""
from typing import Dict, Optional, Tuple

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import keyboards, states
from app.bot.middleware import (
    handle_errors, require_db, require_linked, with_request_id,
)
from app.services import browse_service, search_service
from app.services.location_service import get_customer_location, get_search_radius
from app.utils.geo import humanize_distance
from app.utils.logging import get_logger

logger = get_logger(__name__)

NEED_LOCATION = (
    "📍 Aas-paas ka saaman dekhne ke liye pehle apni location share kijiye.\n\n"
    "Neeche button dabaiye — ek baar bhejne par yaad rakh li jaayegi."
)


async def _customer_point(user: Dict) -> Optional[Tuple[float, float]]:
    return await get_customer_location(user["_id"])


async def _require_location(update: Update, user: Dict) -> Optional[Tuple[float, float]]:
    location = await _customer_point(user)
    if not location:
        await update.effective_message.reply_text(
            NEED_LOCATION, reply_markup=keyboards.location_request_keyboard()
        )
        return None
    return location


@with_request_id
@require_db
@require_linked()
@handle_errors("browse.menu")
async def browse_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    location = await _require_location(update, user)
    if not location:
        return
    states.clear_mode(context)
    radius = await get_search_radius(user["_id"])
    await update.effective_message.reply_text(
        "🛒 BROWSE NEARBY\n\n"
        "Aas-paas ki shops ne jo stock list kiya hai, woh yahan dikhta hai.\n"
        f"📏 Current range: {humanize_distance(radius)}\n\n"
        "Kya dekhna chahenge?",
        reply_markup=keyboards.browse_menu(),
    )


@with_request_id
@require_db
@require_linked()
@handle_errors("browse.callback")
async def browse_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    """Every brs:* callback lands here and fans out by action."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else "menu"
    argument = parts[2] if len(parts) > 2 else None

    location = await _customer_point(user)
    if not location:
        await query.message.reply_text(
            NEED_LOCATION, reply_markup=keyboards.location_request_keyboard()
        )
        return
    latitude, longitude = location
    radius = await get_search_radius(user["_id"])

    if action == "menu":
        await query.message.reply_text(
            f"🛒 BROWSE NEARBY\n📏 Range: {humanize_distance(radius)}",
            reply_markup=keyboards.browse_menu(),
        )
        return

    if action == "stock":
        await _show_products(query, latitude, longitude, radius, category=None,
                             heading=f"🧺 IN STOCK — within {humanize_distance(radius)}")
        return

    if action == "cats":
        categories = await browse_service.nearby_categories(latitude, longitude,
                                                             radius_meters=radius)
        if not categories:
            await query.message.reply_text(
                "😕 Abhi aapke is range mein koi registered shop nahi mili.\n"
                "📏 Range badhaiye, ya 🔎 Find Product try kijiye.",
                reply_markup=keyboards.browse_menu(),
            )
            return
        await query.message.reply_text(
            "🏷️ Aas-paas ki shop categories:",
            reply_markup=keyboards.browse_category_keyboard(categories),
        )
        return

    if action == "cat" and argument:
        await _show_products(query, latitude, longitude, radius, category=argument,
                             heading=f"🧺 IN STOCK — {argument.replace('_', ' ').title()}")
        return

    if action == "shops":
        await _show_shops(query, latitude, longitude, radius, category=None)
        return

    if action == "shop" and argument:
        await _show_shop_card(query, argument, latitude, longitude)
        return

    if action == "stock_shop" and argument:
        await _show_shop_card(query, argument, latitude, longitude, stock_only=True)
        return

    if action == "buy" and argument:
        await _reserve(query, context, user, argument, latitude, longitude)
        return

    logger.warning("unknown browse callback | data=%s", query.data)
    await query.message.reply_text(
        "🤔 Yeh option samajh nahi aaya.", reply_markup=keyboards.browse_menu()
    )


async def _show_products(query, latitude: float, longitude: float, radius: int, *,
                         category: Optional[str], heading: str,
                         search_query: Optional[str] = None) -> None:
    products = await browse_service.nearby_products(
        latitude, longitude, query=search_query, category=category, radius_meters=radius
    )
    text = browse_service.format_product_list(products, heading=heading)
    if not products:
        await query.message.reply_text(text, reply_markup=keyboards.browse_menu())
        return
    await query.message.reply_text(
        text, reply_markup=keyboards.browse_products_keyboard(products)
    )


async def _show_shops(query, latitude: float, longitude: float, radius: int, *,
                      category: Optional[str]) -> None:
    shops = await browse_service.nearby_shops(latitude, longitude, category=category,
                                              radius_meters=radius)
    if not shops:
        await query.message.reply_text(
            f"😕 {humanize_distance(radius)} ke andar koi shop nahi mili.\n"
            "📏 Range badhaiye, ya 🔎 Find Product dabaiye — wahan radius apne aap badhta hai.",
            reply_markup=keyboards.browse_menu(),
        )
        return
    lines = [f"🏪 SHOPS AROUND YOU · within {humanize_distance(radius)}", ""]
    for shop in shops:
        stock = (f"{shop['item_count']} items listed" if shop["item_count"]
                 else "inventory not listed")
        lines.append(f"• {shop['shop_name']} — {shop['category_label']}")
        lines.append(f"   📍 {humanize_distance(shop['distance_meters'])} · {stock}")
    lines += ["", "Shop par tap karke details aur directions dekhiye."]
    await query.message.reply_text(
        "\n".join(lines), reply_markup=keyboards.browse_shops_keyboard(shops)
    )


async def _show_shop_card(query, shop_id: str, latitude: float, longitude: float,
                          *, stock_only: bool = False) -> None:
    data = await browse_service.shop_with_stock(
        shop_id, customer_latitude=latitude, customer_longitude=longitude
    )
    shop, items = data["shop"], data["items"]

    if stock_only and items:
        await query.message.reply_text(
            browse_service.format_product_list(
                items, heading=f"📦 {shop['shop_name']} — IN STOCK"
            ),
            reply_markup=keyboards.browse_products_keyboard(items),
        )
        return

    await query.message.reply_text(
        browse_service.format_shop_card(shop, items),
        reply_markup=keyboards.shop_actions_keyboard(shop),
        disable_web_page_preview=True,
    )
    # A real map pin, so the customer can tap straight through to navigation.
    if shop.get("latitude") is not None:
        await query.message.reply_location(
            latitude=shop["latitude"], longitude=shop["longitude"]
        )


async def _reserve(query, context: ContextTypes.DEFAULT_TYPE, user, item_id: str,
                   latitude: float, longitude: float) -> None:
    """Customer tapped a listed item: ask that one shop to confirm it's still there."""
    item = await browse_service.get_item(item_id)
    shop = await browse_service.get_shop(item["shop_id"])

    if not shop.get("is_active", True):
        await query.message.reply_text("🔴 Yeh shop abhi requests nahi le rahi hai.")
        return

    # search_service keys every request/reservation by the *user* id (see
    # recent_requests / history_command) — not the customer profile's own _id,
    # which is a different document. Using the profile id here would silently
    # orphan reservations from "My Requests".
    result = await search_service.create_reservation(
        item=item, shop=shop, customer_id=user["_id"],
        telegram_user_id=query.from_user.id if query.from_user else None,
        customer_name=user.get("full_name") or "Customer",
        latitude=latitude, longitude=longitude,
    )
    context.user_data[states.LAST_REQUEST_ID] = result["request"]["request_id"]

    price = f"₹{item['price']:g}" if item.get("price") is not None else "price not listed"
    lines = [
        "🛒 Reservation request bhej di gayi!",
        "",
        f"🔧 {item.get('product')}",
        f"🏪 {shop.get('shop_name')} · {price}",
        "",
    ]
    if result["notified"]:
        lines.append("Shopkeeper confirm karte hi aapko message mil jaayega.")
    else:
        lines.append("⚠️ Shopkeeper ko abhi Telegram par nahi pahuncha ja saka. "
                     "Aap seedha phone kar sakte hain.")
    if shop.get("phone"):
        lines.append(f"📞 {shop['phone']}")
    lines += ["", "ℹ️ Yeh sirf availability request hai — payment shop par hi hoti hai. "
                  "Vyapaar-Mitra koi order ya payment handle nahi karta."]

    summary = await browse_service.shop_with_stock(
        shop["_id"], customer_latitude=latitude, customer_longitude=longitude
    )
    navigation = summary["shop"].get("navigation_url")
    await query.message.reply_text(
        "\n".join(lines),
        reply_markup=keyboards.navigation_keyboard(navigation) if navigation else None,
        disable_web_page_preview=True,
    )


@with_request_id
@require_db
@require_linked()
@handle_errors("browse.search_stock")
async def browse_search(update: Update, context: ContextTypes.DEFAULT_TYPE, user,
                        query_text: str) -> None:
    """'Is X available nearby?' answered from listed stock only."""
    location = await _require_location(update, user)
    if not location:
        return
    latitude, longitude = location
    radius = await get_search_radius(user["_id"])
    products = await browse_service.nearby_products(
        latitude, longitude, query=query_text, radius_meters=radius
    )
    text = browse_service.format_product_list(
        products, heading=f"🧺 '{query_text}' — within {humanize_distance(radius)}"
    )
    markup = (keyboards.browse_products_keyboard(products) if products
              else keyboards.browse_menu())
    await update.effective_message.reply_text(text, reply_markup=markup)
