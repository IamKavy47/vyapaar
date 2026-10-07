"""Cross-cutting bot concerns: request ids, account resolution, role guards."""
from functools import wraps
from typing import Dict, Optional, Tuple

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.keyboards import auth_keyboard
from app.database.mongo import mongo
from app.models.user import UserRole
from app.services import auth_service
from app.utils.errors import (
    GENERIC_USER_MESSAGE, AppError, describe_unexpected, new_error_ref,
)
from app.utils.logging import bind_request_id, get_logger, new_request_id
from app.utils.security import ai_limiter

logger = get_logger(__name__)

LINK_PROMPT = (
    "🔐 Pehle apna account link kijiye.\n\n"
    "Neeche diye secure link par click karke login ya register kariye. "
    "Link 10 minute ke liye valid hai.\n\n"
    "(Password kabhi Telegram par mat bhejiye.)"
)


def telegram_id(update: Update) -> Optional[int]:
    user = update.effective_user
    return user.id if user else None


async def current_user(update: Update) -> Optional[Dict]:
    tg_id = telegram_id(update)
    if not tg_id or not mongo.connected:
        return None
    return await auth_service.get_user_by_telegram_id(tg_id)


async def current_shop(user: Dict) -> Optional[Dict]:
    from app.database import mongo as m
    if not user:
        return None
    return await m.shops().find_one({"user_id": user["_id"]})


async def current_customer(user: Dict) -> Optional[Dict]:
    from app.database import mongo as m
    if not user:
        return None
    return await m.customers().find_one({"user_id": user["_id"]})


async def send_link_prompt(update: Update, role_hint: Optional[str] = None) -> None:
    tg_id = telegram_id(update)
    if not tg_id:
        return
    url = await auth_service.create_auth_link(tg_id, role_hint=role_hint)
    target = update.effective_message
    if target:
        await target.reply_text(LINK_PROMPT, reply_markup=auth_keyboard(url))


def with_request_id(func):
    """Give every Telegram interaction a correlation id for the logs."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        bind_request_id(new_request_id("TG"))
        logger.info("Telegram message received | handler=%s user=%s",
                    func.__name__, telegram_id(update))
        return await func(update, context, *args, **kwargs)

    return wrapper


def require_db(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not mongo.connected:
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⚠️ Service abhi thodi der ke liye unavailable hai. "
                    "Kripya kuch minute baad try kijiye."
                )
            return None
        return await func(update, context, *args, **kwargs)

    return wrapper


def require_linked(role: Optional[str] = None):
    """Ensure the Telegram account is linked, and optionally check the role."""

    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user = await current_user(update)
            if not user:
                await send_link_prompt(update, role_hint=role)
                return None
            if role and user.get("role") not in {role, UserRole.ADMIN.value}:
                if update.effective_message:
                    await update.effective_message.reply_text(
                        "🚫 Yeh option aapke account role ke liye available nahi hai."
                    )
                return None
            context.user_data["account"] = str(user["_id"])
            return await func(update, context, user, *args, **kwargs)

        return wrapper

    return decorator


def rate_limit_ai(func):
    """Protect the expensive AI paths from accidental spamming."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        tg_id = telegram_id(update)
        if tg_id and not ai_limiter.allow(f"ai:{tg_id}"):
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⏳ Thoda dheere! Ek minute mein bahut requests aa gayi. "
                    "Kuch second baad try kijiye."
                )
            return None
        return await func(update, context, *args, **kwargs)

    return wrapper


def handle_errors(operation: str = ""):
    """Turn any exception inside a handler into a reply the user can act on.

    Without this, one bad callback payload kills the handler silently and the
    customer is left staring at a chat that stopped responding. With it:

    * an ``AppError`` shows its own message (plus a reference id when the user
      cannot fix it themselves);
    * anything else is a bug — the user gets a generic apology with a reference,
      and the log gets the full traceback, the handler name, the Telegram id and
      the callback payload that triggered it.

    Apply it *below* ``@require_linked`` so the ``user`` argument still threads
    through.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            op = operation or func.__name__
            try:
                return await func(update, context, *args, **kwargs)
            except AppError as exc:
                exc.operation = exc.operation or op
                exc.context.setdefault("telegram_user_id", telegram_id(update))
                exc.context.setdefault("handler", func.__name__)
                if exc.actionable:
                    logger.warning("handled error | %s", exc.debug_line())
                else:
                    logger.error("handled error | %s", exc.debug_line(), exc_info=exc.cause or exc)
                await _reply_safely(update, exc.user_text())
                return None
            except Exception as exc:
                ref = new_error_ref()
                logger.exception(
                    "unhandled handler error | %s",
                    describe_unexpected(exc, operation=op, context={
                        "ref": ref,
                        "handler": func.__name__,
                        "telegram_user_id": telegram_id(update),
                        "callback_data": _callback_data(update),
                        "message_text": _message_preview(update),
                    }),
                )
                await _reply_safely(
                    update,
                    f"{GENERIC_USER_MESSAGE}\n\n🔎 Reference: {ref}",
                )
                return None

        return wrapper

    return decorator


def _callback_data(update: Update) -> str:
    query = getattr(update, "callback_query", None)
    return getattr(query, "data", "") if query else ""


def _message_preview(update: Update, limit: int = 80) -> str:
    message = update.effective_message if hasattr(update, "effective_message") else None
    text = (getattr(message, "text", "") or "") if message else ""
    return text[:limit]


async def _reply_safely(update: Update, text: str) -> None:
    """Telling the user we failed must not itself fail."""
    try:
        if update.effective_message:
            await update.effective_message.reply_text(text)
    except Exception as exc:
        logger.warning("could not deliver error message to user: %s", exc.__class__.__name__)


async def resolve_actor(update: Update) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Returns (user, profile) where profile is the shop or customer document."""
    user = await current_user(update)
    if not user:
        return None, None
    if user.get("role") == UserRole.SHOPKEEPER.value:
        return user, await current_shop(user)
    return user, await current_customer(user)
