"""Secure account linking from Telegram. No passwords ever pass through chat."""
from telegram import Update
from telegram.ext import ContextTypes

from app.bot import keyboards, states
from app.bot.handlers.start import _menu_for
from app.bot.middleware import current_user, require_db, telegram_id, with_request_id
from app.services import auth_service
from app.utils.security import auth_limiter


@with_request_id
@require_db
async def auth_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    tg_id = telegram_id(update)
    if not auth_limiter.allow(f"tg-auth:{tg_id}"):
        await query.message.reply_text("⏳ Bahut saare link requests. Ek minute baad try kijiye.")
        return

    user = await current_user(update)
    if user:
        await query.message.reply_text("✅ Account already linked hai.")
        await _menu_for(update, user)
        return

    role_hint = context.user_data.get(states.PENDING_ROLE)
    url = await auth_service.create_auth_link(tg_id, role_hint=role_hint)
    await query.message.reply_text(
        "🔐 Secure login/registration page:\n\n"
        "• Link 10 minute valid hai\n"
        "• Sirf ek baar use hoga\n"
        "• Password sirf website par daaliye",
        reply_markup=keyboards.auth_keyboard(url),
    )


@with_request_id
@require_db
async def auth_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = await current_user(update)
    if not user:
        await query.message.reply_text(
            "❌ Abhi tak link nahi hua. Upar wale link par login/register complete kijiye."
        )
        return
    await query.message.reply_text("✅ Account successfully connected.")
    await _menu_for(update, user)


@with_request_id
@require_db
async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = telegram_id(update)
    if not auth_limiter.allow(f"tg-auth:{tg_id}"):
        await update.effective_message.reply_text("⏳ Thodi der baad try kijiye.")
        return
    user = await current_user(update)
    if user:
        await update.effective_message.reply_text("✅ Aap already logged in hain.")
        return
    url = await auth_service.create_auth_link(
        tg_id, role_hint=context.user_data.get(states.PENDING_ROLE)
    )
    await update.effective_message.reply_text(
        "🔐 Secure login page:", reply_markup=keyboards.auth_keyboard(url)
    )


@with_request_id
@require_db
async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask before unlinking — an accidental tap should not cost a shopkeeper access."""
    user = await current_user(update)
    if not user:
        await update.effective_message.reply_text(
            "Aap abhi logged in nahi hain.", reply_markup=keyboards.role_keyboard()
        )
        return
    await update.effective_message.reply_text(
        "🚪 LOGOUT\n\n"
        f"👤 {user.get('full_name') or ''}\n\n"
        "Logout karne par yeh Telegram account unlink ho jayega aur menu band ho jayega.\n"
        "Aapka data safe rahega — shop, inventory, khata aur history sab waise hi milenge.\n\n"
        "Wapas aane ke liye /start dabakar dobara login kijiye.",
        reply_markup=keyboards.logout_confirm_keyboard(),
    )


@with_request_id
@require_db
async def logout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles logout:confirm and logout:cancel."""
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]

    if action == "cancel":
        await query.edit_message_text("↩️ Logout cancel ho gaya. Aap logged in hain.")
        user = await current_user(update)
        if user:
            await _menu_for(update, user)
        return

    tg_id = telegram_id(update)
    user = await auth_service.logout_telegram(tg_id) if tg_id else None
    context.user_data.clear()
    states.clear_mode(context)

    if not user:
        await query.edit_message_text("Aap already logged out hain.")
        return

    await query.edit_message_text(
        "✅ Logout ho gaya.\n\n"
        "Telegram account unlink kar diya gaya hai aur saare active sessions band ho gaye hain."
    )
    # Drop the role menu so the old buttons cannot be tapped by the next person.
    await query.message.reply_text(
        "Dobara shuru karne ke liye /start dabaiye.", reply_markup=keyboards.remove_keyboard()
    )
