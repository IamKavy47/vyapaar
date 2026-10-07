"""Merchant menu, YES/NO responses and price capture."""
from typing import Optional

from bson import ObjectId

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import keyboards, states
from app.config.settings import settings
from app.bot.middleware import current_shop, handle_errors, require_db, require_linked, with_request_id
from app.database import mongo as m
from app.models.merchant_match import MatchStatus
from app.models.shop import CATEGORY_CAPABILITIES, category_label, normalize_category
from app.models.user import UserRole, utcnow
from app.services import inventory_service, merchant_matching, search_service
from app.utils.geo import humanize_distance
from app.utils.logging import get_logger
from app.utils.parsing import parse_price

logger = get_logger(__name__)


@with_request_id
@require_db
@require_linked(role=UserRole.SHOPKEEPER.value)
async def my_shop(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    shop = await current_shop(user)
    if not shop:
        await update.effective_message.reply_text("Shop profile nahi mila. /start dobara kijiye.")
        return
    item_count = await inventory_service.count_items(shop["_id"])
    has_location = bool(shop.get("location"))
    lines = [
        "🏪 MY SHOP", "",
        f"📛 {shop.get('shop_name')}",
        f"🏷️ Category: {category_label(shop.get('category'))}",
        f"🔧 Capabilities: {', '.join(shop.get('capabilities') or []) or '—'}",
        f"📞 {shop.get('phone') or '—'}",
        f"📍 Location: {'saved ✅' if has_location else 'NOT SET ❌'}",
        f"📦 Inventory items: {item_count} (optional)",
        f"✅ Accepted: {shop.get('accepted_count', 0)} · ❌ Declined: {shop.get('declined_count', 0)}",
        "",
        "Naam badalna ho to likhiye: name <new name>",
        "Category badalne ke liye: /category",
    ]
    if not has_location:
        lines.append("\n⚠️ Location ke bina requests nahi mil paayengi.")
    await update.effective_message.reply_text("\n".join(lines))


@with_request_id
@require_db
@require_linked(role=UserRole.SHOPKEEPER.value)
async def category_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    await update.effective_message.reply_text(
        "🏷️ Apni shop ki category chuniye:", reply_markup=keyboards.category_keyboard()
    )


@with_request_id
@require_db
@require_linked(role=UserRole.SHOPKEEPER.value)
async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    query = update.callback_query
    await query.answer()
    category = normalize_category(query.data.split(":", 1)[1])
    capabilities = CATEGORY_CAPABILITIES.get(category, [])
    await m.shops().update_one(
        {"user_id": user["_id"]},
        {"$set": {"category": category, "capabilities": capabilities, "updated_at": utcnow()}},
    )
    await query.edit_message_text(
        f"✅ Category set: {category_label(category)}\n"
        f"🔧 Default capabilities: {', '.join(capabilities)}\n\n"
        "Capabilities badalne ke liye likhiye:\ncapabilities pipes, tools, sealants"
    )


@with_request_id
@require_db
@require_linked(role=UserRole.SHOPKEEPER.value)
async def requests_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    shop = await current_shop(user)
    if not shop:
        return
    cursor = m.merchant_matches().find(
        {"merchant_id": shop["_id"]}
    ).sort("created_at", -1).limit(8)
    rows = [doc async for doc in cursor]
    if not rows:
        await update.effective_message.reply_text(
            "🔔 Abhi tak koi request nahi aayi.\n\n"
            "Jaise hi aas-paas koi customer kuch dhoondhega, aapko message milega — "
            "inventory upload kiye bina bhi."
        )
        return
    lines = ["🔔 RECENT REQUESTS", ""]
    for match in rows:
        request = await search_service.get_request(match["request_id"])
        product = (request or {}).get("product") or "(unknown)"
        price = f" · ₹{match['price']:g}" if match.get("price") is not None else ""
        lines.append(
            f"🔧 {product} — {match.get('status')}{price}\n"
            f"   📍 {humanize_distance(match.get('distance_meters') or 0)}"
        )
    await update.effective_message.reply_text("\n".join(lines))


@with_request_id
@require_db
@require_linked(role=UserRole.SHOPKEEPER.value)
@handle_errors("merchant.response_callback")
async def merchant_response_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    """Handles mr:yes:<match_id> and mr:no:<match_id>."""
    query = update.callback_query
    _, answer, match_id = query.data.split(":", 2)

    match = await merchant_matching.get_match(match_id)
    if not match:
        await query.answer("Yeh request ab available nahi hai.", show_alert=True)
        return

    shop = await current_shop(user)
    if not shop or str(match["merchant_id"]) != str(shop["_id"]):
        await query.answer("Yeh request aapki shop ke liye nahi hai.", show_alert=True)
        return

    if match.get("status") in {MatchStatus.ACCEPTED.value, MatchStatus.DECLINED.value}:
        await query.answer("Aap pehle hi jawab de chuke hain.", show_alert=True)
        return

    await query.answer()

    if answer == "yes":
        context.user_data[states.PENDING_PRICE_MATCH] = str(match["_id"])
        states.set_mode(context, states.MODE_AWAIT_PRICE)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "💰 What is your price?\n\nSirf amount likhiye, jaise: 30"
        )
        return

    ok, payload = await search_service.handle_merchant_response(match["_id"], accepted=False)
    await query.edit_message_reply_markup(reply_markup=None)
    product = ((payload or {}).get("request") or {}).get("product") or "yeh item"
    await query.message.reply_text(
        f"❌ Noted — {product} available nahi hai.\n\n"
        f"Agle {settings.MERCHANT_COOLDOWN_HOURS} ghante tak isi product ke liye "
        "aapko dobara message nahi jaayega.\n\n"
        "📊 Yeh jaankari aapki demand report mein add ho gayi hai."
    )


async def handle_price_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, user,
                             text: str) -> bool:
    """Merchant typed a price after pressing YES."""
    match_id = context.user_data.get(states.PENDING_PRICE_MATCH)
    if not match_id:
        return False
    price: Optional[float] = parse_price(text)
    if price is None:
        await update.effective_message.reply_text(
            "💰 Amount samajh nahi aaya. Sirf number likhiye, jaise: 30"
        )
        return True

    ok, payload = await search_service.handle_merchant_response(
        ObjectId(match_id), accepted=True, price=price
    )
    states.clear_mode(context)
    if not ok:
        await update.effective_message.reply_text("Yeh request ab active nahi hai.")
        return True

    product = ((payload or {}).get("request") or {}).get("product") or "Item"
    await update.effective_message.reply_text(
        f"✅ Dhanyavaad! Customer ko bata diya gaya hai:\n\n"
        f"🔧 {product}\n💰 ₹{price:g}\n\n"
        "Customer aapse sampark karega. (Sale abhi confirm nahi hui hai.)",
        reply_markup=keyboards.merchant_menu(),
    )
    return True


async def handle_shop_text_commands(update: Update, context: ContextTypes.DEFAULT_TYPE, user,
                                    text: str) -> bool:
    """Simple 'name ...' / 'capabilities ...' / 'phone ...' edits."""
    lowered = text.strip().lower()
    if lowered.startswith("name "):
        new_name = text.strip()[5:].strip()
        if new_name:
            await m.shops().update_one({"user_id": user["_id"]},
                                       {"$set": {"shop_name": new_name, "updated_at": utcnow()}})
            await update.effective_message.reply_text(f"✅ Shop name updated: {new_name}")
        return True
    if lowered.startswith("capabilities "):
        caps = [c.strip().lower() for c in text.split(" ", 1)[1].split(",") if c.strip()]
        if caps:
            await m.shops().update_one({"user_id": user["_id"]},
                                       {"$set": {"capabilities": caps, "updated_at": utcnow()}})
            await update.effective_message.reply_text(f"✅ Capabilities updated: {', '.join(caps)}")
        return True
    if lowered.startswith("phone "):
        phone = text.split(" ", 1)[1].strip()
        await m.shops().update_one({"user_id": user["_id"]},
                                   {"$set": {"phone": phone, "updated_at": utcnow()}})
        await update.effective_message.reply_text(f"✅ Phone updated: {phone}")
        return True
    return False


@with_request_id
@require_db
@require_linked(role=UserRole.SHOPKEEPER.value)
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    shop = await current_shop(user)
    active = (shop or {}).get("is_active", True)
    await update.effective_message.reply_text(
        "⚙️ SETTINGS\n\n"
        f"Shop status: {'🟢 Active' if active else '🔴 Paused'}\n\n"
        "Commands:\n"
        "• pause — requests aana band\n"
        "• resume — requests dobara shuru\n"
        "• name <new name>\n"
        "• phone <number>\n"
        "• capabilities <comma separated>\n"
        "• /category — category badliye"
    )


async def handle_pause_resume(update: Update, user, text: str) -> bool:
    lowered = text.strip().lower()
    if lowered in {"pause", "band"}:
        await m.shops().update_one({"user_id": user["_id"]}, {"$set": {"is_active": False}})
        await update.effective_message.reply_text("🔴 Shop paused. Ab requests nahi aayengi.")
        return True
    if lowered in {"resume", "chalu"}:
        await m.shops().update_one({"user_id": user["_id"]}, {"$set": {"is_active": True}})
        await update.effective_message.reply_text("🟢 Shop active. Requests dobara aayengi.")
        return True
    return False
