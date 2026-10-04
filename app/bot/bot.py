"""Telegram application wiring.

Telegram is only an interface. Every handler delegates to the service layer, so a
WhatsApp or web front-end can be added later without touching business logic.
"""
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)

from app.bot.handlers import (
    admin, auth, browse, customer, demand, inventory, khata, merchant, router, search, start,
)
from app.config.settings import settings
from app.services import notification_service
from app.utils.errors import (
    GENERIC_USER_MESSAGE, AppError, describe_unexpected, new_error_ref,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

_application: Optional[Application] = None


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Last line of defence: anything @handle_errors did not catch.

    Handlers should catch their own failures, so arriving here means either a
    handler without the decorator or a failure in the framework itself. Both are
    worth a loud log with the update that caused them.
    """
    error = context.error
    ref = new_error_ref()
    details = {"ref": ref}
    if isinstance(update, Update):
        details["telegram_user_id"] = update.effective_user.id if update.effective_user else None
        details["chat_id"] = update.effective_chat.id if update.effective_chat else None
        details["update_id"] = update.update_id
        if update.callback_query:
            details["callback_data"] = update.callback_query.data
        elif update.effective_message and update.effective_message.text:
            details["message_text"] = update.effective_message.text[:80]
    else:
        details["update_type"] = type(update).__name__

    if isinstance(error, AppError):
        error.context.update(details)
        logger.error("bot error | %s", error.debug_line(), exc_info=error.cause or error)
        message = error.user_text()
    else:
        logger.exception(
            "bot error | %s",
            describe_unexpected(error or Exception("unknown"),
                                operation="telegram.dispatch", context=details),
        )
        message = f"{GENERIC_USER_MESSAGE}\n\n🔎 Reference: {ref}"

    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(message)
    except Exception as exc:
        logger.warning("could not deliver error message: %s", exc.__class__.__name__)


def build_application() -> Optional[Application]:
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN missing — Telegram bot will not start")
        return None

    application = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # Commands
    application.add_handler(CommandHandler("start", start.start_command))
    application.add_handler(CommandHandler("menu", start.menu_command))
    application.add_handler(CommandHandler("help", start.help_command))
    application.add_handler(CommandHandler("login", auth.login_command))
    application.add_handler(CommandHandler("register", auth.login_command))
    application.add_handler(CommandHandler("logout", auth.logout_command))
    application.add_handler(CommandHandler("browse", browse.browse_command))
    application.add_handler(CommandHandler("range", customer.range_command))
    application.add_handler(CommandHandler("history", customer.history_command))
    application.add_handler(CommandHandler("khata", khata.khata_command))
    application.add_handler(CommandHandler("khata_summary", khata.khata_summary_command))
    application.add_handler(CommandHandler("inventory", inventory.inventory_command))
    application.add_handler(CommandHandler("demand", demand.demand_command))
    application.add_handler(CommandHandler("compare", demand.compare_command))
    application.add_handler(CommandHandler("category", merchant.category_command))
    application.add_handler(CommandHandler("shop", merchant.my_shop))
    application.add_handler(CommandHandler("admin", admin.admin_command))
    application.add_handler(CommandHandler("admin_demand", admin.admin_demand))

    # Callback queries
    application.add_handler(CallbackQueryHandler(start.role_callback, pattern=r"^role:"))
    application.add_handler(CallbackQueryHandler(start.help_callback, pattern=r"^nav:help$"))
    application.add_handler(CallbackQueryHandler(auth.auth_link_callback, pattern=r"^auth:link$"))
    application.add_handler(CallbackQueryHandler(auth.auth_check_callback, pattern=r"^auth:check$"))
    application.add_handler(
        CallbackQueryHandler(auth.logout_callback, pattern=r"^logout:(confirm|cancel)$")
    )
    application.add_handler(CallbackQueryHandler(browse.browse_callback, pattern=r"^brs:"))
    application.add_handler(CallbackQueryHandler(customer.range_callback, pattern=r"^rng:"))
    application.add_handler(
        CallbackQueryHandler(merchant.merchant_response_callback, pattern=r"^mr:(yes|no):")
    )
    application.add_handler(CallbackQueryHandler(merchant.category_callback, pattern=r"^cat:"))
    application.add_handler(CallbackQueryHandler(search.clarification_callback, pattern=r"^clar:"))
    application.add_handler(CallbackQueryHandler(search.repeat_callback, pattern=r"^rep:"))
    application.add_handler(CallbackQueryHandler(inventory.inventory_callback, pattern=r"^inv:"))
    application.add_handler(CallbackQueryHandler(khata.khata_callback, pattern=r"^khata:"))

    # Media and text
    application.add_handler(MessageHandler(filters.LOCATION, customer.location_handler))
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, router.voice_router))
    application.add_handler(MessageHandler(filters.PHOTO, router.photo_router))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, router.text_router)
    )

    application.add_error_handler(error_handler)
    return application


async def start_bot() -> Optional[Application]:
    """Start long polling in the background of the FastAPI event loop."""
    global _application
    application = build_application()
    if application is None:
        return None

    await application.initialize()
    await application.start()
    await application.updater.start_polling(
        allowed_updates=Update.ALL_TYPES, drop_pending_updates=True
    )
    notification_service.set_bot(application.bot)
    _application = application
    logger.info("Telegram bot started (long polling)")
    return application


async def stop_bot() -> None:
    global _application
    if _application is None:
        return
    try:
        if _application.updater and _application.updater.running:
            await _application.updater.stop()
        await _application.stop()
        await _application.shutdown()
        logger.info("Telegram bot stopped")
    except Exception as exc:
        logger.warning("Error while stopping bot: %s", exc)
    finally:
        _application = None
        notification_service.set_bot(None)


def get_application() -> Optional[Application]:
    return _application
