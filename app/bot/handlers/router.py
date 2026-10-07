"""Single text entry point. Decides what a plain message means, then delegates.

No business logic lives here — only routing.
"""
from telegram import Update
from telegram.ext import ContextTypes

from app.bot import states
from app.bot.handlers import auth, browse, customer, demand, inventory, khata, merchant, search
from app.bot.handlers.start import _menu_for
from app.bot.middleware import (
    current_user, handle_errors, require_db, send_link_prompt, with_request_id,
)
from app.models.user import UserRole
from app.utils.logging import get_logger

logger = get_logger(__name__)

CUSTOMER_BUTTONS = {
    "🔎 Find Product": customer.prompt_find_product,
    "🛒 Browse Nearby": browse.browse_command,
    "🎤 Voice Search": customer.prompt_voice_search,
    "📷 Photo Search": customer.prompt_photo_search,
    "📏 Range": customer.range_command,
}

MERCHANT_BUTTONS = {
    "🏪 My Shop": merchant.my_shop,
    "📦 Inventory": inventory.inventory_command,
    "🔔 Requests": merchant.requests_command,
    "📊 Demand": demand.demand_command,
    "📒 Khata": khata.khata_command,
    "⚙️ Settings": merchant.settings_command,
}


@with_request_id
@require_db
@handle_errors("router.text")
async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    text = (message.text or "").strip()
    if not text:
        return

    user = await current_user(update)
    if not user:
        await send_link_prompt(update, role_hint=context.user_data.get(states.PENDING_ROLE))
        return

    if text == "⬅️ Back":
        states.clear_mode(context)
        await _menu_for(update, user)
        return

    role = user.get("role")
    mode = states.get_mode(context)

    # ---- Shared buttons ----
    if text == "📍 My Location" or text == "📍 Location":
        await customer.ask_location(update, context)
        return
    if text == "🧾 My Requests":
        await customer.my_requests(update, context)
        return
    if text == "⚙️ Profile":
        await customer.profile_command(update, context)
        return
    if text == "📒 My Khata":
        await customer.customer_khata(update, context)
        return
    if text == "🚪 Logout":
        await auth.logout_command(update, context)
        return

    # ---- Merchant ----
    if role == UserRole.SHOPKEEPER.value:
        if mode == states.MODE_AWAIT_PRICE and await merchant.handle_price_reply(
            update, context, user, text
        ):
            return
        if mode == states.MODE_AWAIT_KHATA_REMINDER and await khata.handle_reminder_request(
            update, context, user, text
        ):
            return

        handler = MERCHANT_BUTTONS.get(text)
        if handler:
            await handler(update, context)
            return

        if await merchant.handle_pause_resume(update, user, text):
            return
        if await merchant.handle_shop_text_commands(update, context, user, text):
            return

        if mode == states.MODE_KHATA:
            await khata.process_khata_text(update, context, user, text)
            return
        if mode == states.MODE_INVENTORY:
            await inventory.process_inventory_text(update, context, user, text)
            return

        await message.reply_text(
            "🤔 Samajh nahi aaya. Neeche menu use kijiye, ya:\n"
            "• 📒 Khata dabakar entry likhiye\n"
            "• 📦 Inventory dabakar stock bataiye"
        )
        return

    # ---- Customer ----
    if mode == states.MODE_AWAIT_RADIUS and await customer.handle_range_text(
        update, context, user, text
    ):
        return

    handler = CUSTOMER_BUTTONS.get(text)
    if handler:
        await handler(update, context)
        return

    await search.handle_text_search(update, context)


@with_request_id
@require_db
@handle_errors("router.voice")
async def voice_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await search.handle_voice_search(update, context)


@with_request_id
@require_db
@handle_errors("router.photo")
async def photo_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await search.handle_photo_search(update, context)
