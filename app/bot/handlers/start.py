"""/start, role selection and help."""
from telegram import Update
from telegram.ext import ContextTypes

from app.bot import keyboards, states
from app.bot.middleware import current_user, require_db, send_link_prompt, with_request_id
from app.models.user import UserRole

WELCOME = "Welcome to Vyapaar-Mitra 🛍️\n\nWho are you?"

HELP_TEXT = """❓ VYAPAAR-MITRA HELP

👤 Customer
• Type what you need: "1 inch PVC pipe chahiye"
• Or send a voice note in Hindi/Hinglish
• Or send a photo of the product
• Share your location once, and nearby shops get asked directly

🏪 Shopkeeper
• Aapko customer requests Telegram par milengi
• YES / NO dabaiye — bas itna hi
• Inventory upload karna ZAROORI NAHI hai
• 📒 Khata: "Ramesh ne 500 rupaye udhaar liye"
• 📊 Demand: aapke area mein kya maang hai

Commands:
/start  — role selection
/menu   — your menu
/history— recent searches
/khata  — digital ledger
/khata_summary — outstanding balances
/demand — local demand report
/help   — this message

🔐 Login/registration hamesha secure web page par hota hai.
Password kabhi Telegram par mat bhejiye."""


async def _menu_for(update: Update, user) -> None:
    role = (user or {}).get("role")
    if role == UserRole.SHOPKEEPER.value:
        await update.effective_message.reply_text(
            f"🏪 Namaste {user.get('full_name', '')}!\nAapka merchant menu:",
            reply_markup=keyboards.merchant_menu(),
        )
    else:
        await update.effective_message.reply_text(
            f"👤 Namaste {user.get('full_name', '')}!\nAap kya dhoondh rahe hain?",
            reply_markup=keyboards.customer_menu(),
        )


async def _handle_web_link(update: Update, raw_token: str) -> None:
    """``/start web_<token>`` — a logged-in web user connecting their Telegram.

    The token is created by the web app (GET /api/v1/auth/telegram-link) and
    carries the web account's user id; here we attach this Telegram account to
    it. Passwords still never pass through chat.
    """
    from app.services import auth_service, notification_service  # avoid cycle

    tg_id = update.effective_user.id if update.effective_user else None
    try:
        token_doc = await auth_service.consume_web_link_token(raw_token)
        user = await auth_service.link_telegram_account(
            token_doc["web_user_id"], tg_id,
        )
    except auth_service.AuthError as exc:
        await update.effective_message.reply_text(f"⚠️ {exc}")
        return
    await notification_service.send_message(
        tg_id,
        "✅ Telegram connected to your web account!\n\n"
        f"👤 {user.get('full_name')}\n"
        "Ab aapko requests aur jawab yahan bhi milenge.",
        kind="account_linked",
    )
    await _menu_for(update, user)


@with_request_id
@require_db
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    states.clear_mode(context)
    args = getattr(context, "args", None) or []
    if args and str(args[0]).startswith("web_"):
        await _handle_web_link(update, str(args[0])[4:])
        return
    user = await current_user(update)
    if user:
        await _menu_for(update, user)
        return
    await update.effective_message.reply_text(WELCOME, reply_markup=keyboards.role_keyboard())


@with_request_id
@require_db
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await current_user(update)
    if not user:
        await send_link_prompt(update)
        return
    await _menu_for(update, user)


@with_request_id
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT)


@with_request_id
@require_db
async def role_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    role = query.data.split(":", 1)[1]
    context.user_data[states.PENDING_ROLE] = role

    user = await current_user(update)
    if user:
        await query.edit_message_text("✅ Aapka account already linked hai.")
        await _menu_for(update, user)
        return

    label = "Customer 👤" if role == UserRole.CUSTOMER.value else "Shopkeeper 🏪"
    await query.edit_message_text(
        f"{label} selected.\n\nAb ek baar account link kar lijiye — 30 second ka kaam hai."
    )
    await send_link_prompt(update, role_hint=role)


@with_request_id
async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(HELP_TEXT)
