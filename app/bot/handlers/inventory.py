"""Optional inventory: voice notes, invoice photos, shelf photos."""
from telegram import Update
from telegram.ext import ContextTypes

from app.ai import khata_engine, vision_engine
from app.ai.intent_engine import AIUnavailableError
from app.bot import keyboards, states
from app.bot.middleware import (
    current_shop, rate_limit_ai, require_db, require_linked, with_request_id,
)
from app.models.user import UserRole
from app.services import inventory_service
from app.utils.logging import get_logger

logger = get_logger(__name__)


@with_request_id
@require_db
@require_linked(role=UserRole.SHOPKEEPER.value)
async def inventory_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    states.set_mode(context, states.MODE_INVENTORY)
    await update.effective_message.reply_text(
        "📦 INVENTORY (optional)\n\n"
        "Yaad rahe: inventory ke bina bhi aapko customer requests milti rehengi.\n"
        "Inventory sirf matching ko aur behtar banati hai.",
        reply_markup=keyboards.inventory_menu(),
    )


@with_request_id
@require_db
@require_linked(role=UserRole.SHOPKEEPER.value)
async def inventory_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    shop = await current_shop(user)

    if action == "list":
        items = await inventory_service.list_items(shop["_id"])
        await query.message.reply_text(inventory_service.format_inventory(items))
    elif action == "voice":
        states.set_mode(context, states.MODE_INVENTORY)
        await query.message.reply_text(
            "🎤 Voice note bhejiye:\n\"Bhai 20 Fevicol ke bottle aaye hain\""
        )
    elif action == "photo":
        states.set_mode(context, states.MODE_INVENTORY)
        await query.message.reply_text(
            "📷 Wholesale invoice ya shelf ki photo bhejiye. "
            "Main products nikaal kar inventory mein daal dunga."
        )


async def process_inventory_text(update: Update, context: ContextTypes.DEFAULT_TYPE, user,
                                 text: str) -> None:
    message = update.effective_message
    shop = await current_shop(user)
    if not shop:
        await message.reply_text("Shop profile nahi mila.")
        return
    try:
        extraction = await khata_engine.extract_inventory_from_text(text)
    except AIUnavailableError:
        await message.reply_text("⚠️ AI service abhi unavailable hai. Thodi der baad try kijiye.")
        return
    if not extraction.items:
        await message.reply_text(
            "🤔 Stock note samajh nahi aaya.\nJaise bolein: \"20 Fevicol ke bottle aaye hain\""
        )
        return
    stored = await inventory_service.bulk_store(shop["_id"], extraction, source="voice")
    lines = [f"✅ {stored} item(s) inventory mein add hue:", ""]
    for item in extraction.items:
        lines.append(f"• {item.product} — {item.quantity:g} {item.unit}")
    await message.reply_text("\n".join(lines))


@rate_limit_ai
async def process_inventory_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    message = update.effective_message
    shop = await current_shop(user)
    if not shop:
        await message.reply_text("Shop profile nahi mila.")
        return
    await message.reply_text("📷 Photo padh raha hoon...")
    try:
        telegram_file = await message.photo[-1].get_file()
        image_bytes = bytes(await telegram_file.download_as_bytearray())
    except Exception:
        await message.reply_text("📷 Photo download nahi ho paayi. Dobara bhejiye.")
        return
    try:
        extraction = await vision_engine.extract_inventory_from_image(
            image_bytes, hint=message.caption or ""
        )
    except AIUnavailableError:
        await message.reply_text(
            "⚠️ Vision service abhi unavailable hai. Aap voice note se bhi stock bata sakte hain."
        )
        return
    if not extraction.items:
        await message.reply_text(
            "🤔 Is photo se koi product clearly nahi padha ja saka.\n"
            "Thoda saaf/close photo bhejiye."
        )
        return
    stored = await inventory_service.bulk_store(
        shop["_id"], extraction, source=f"{extraction.source_type}_image"
    )
    lines = [f"✅ {stored} item(s) add hue ({extraction.source_type}):", ""]
    for item in extraction.items[:15]:
        confidence = " ⚠️" if item.confidence < 0.5 else ""
        lines.append(f"• {item.product} — {item.quantity:g} {item.unit}{confidence}")
    lines += ["", "⚠️ = kam confidence, ek baar check kar lijiye."]
    await message.reply_text("\n".join(lines))
