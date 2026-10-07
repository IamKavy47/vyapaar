"""Digital Khata handlers — typed or spoken ledger entries."""
from telegram import Update
from telegram.ext import ContextTypes

from app.ai import khata_engine
from app.ai.intent_engine import AIUnavailableError
from app.bot import keyboards, states
from app.bot.middleware import require_db, require_linked, with_request_id
from app.services import email_service, khata_service
from app.services.khata_service import KhataError
from app.utils.logging import get_logger

logger = get_logger(__name__)

KHATA_PROMPT = (
    "📒 DIGITAL KHATA\n\n"
    "Bas likhiye ya bol dijiye:\n"
    "• \"Ramesh ne 500 rupaye udhaar liye\"\n"
    "• \"Ramesh ne 200 rupaye de diye\"\n\n"
    "Main automatically entry bana dunga."
)


@with_request_id
@require_db
@require_linked()
async def khata_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    states.set_mode(context, states.MODE_KHATA)
    await update.effective_message.reply_text(KHATA_PROMPT, reply_markup=keyboards.khata_menu())


@with_request_id
@require_db
@require_linked()
async def khata_summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    result = await khata_service.summary(user["_id"])
    await update.effective_message.reply_text(khata_service.format_summary(result))


@with_request_id
@require_db
@require_linked()
async def khata_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]

    if action == "summary":
        result = await khata_service.summary(user["_id"])
        await query.message.reply_text(khata_service.format_summary(result))
    elif action == "add":
        states.set_mode(context, states.MODE_KHATA)
        await query.message.reply_text(
            "✍️ Entry likhiye ya voice note bhejiye:\n\"Ramesh ne 500 rupaye udhaar liye\""
        )
    elif action == "remind":
        if not email_service.is_enabled():
            await query.message.reply_text(
                "📧 Email abhi configure nahi hai (SMTP settings missing).\n"
                "Telegram ka baaki sab kaam normal chalta rahega."
            )
            return
        states.set_mode(context, states.MODE_AWAIT_KHATA_REMINDER)
        await query.message.reply_text(
            "📧 Kis customer ko reminder bhejna hai?\n"
            "Format: <naam> <email>\nJaise: Ramesh ramesh@example.com"
        )


async def process_khata_text(update: Update, context: ContextTypes.DEFAULT_TYPE, user,
                             text: str, *, source: str = "text") -> None:
    message = update.effective_message
    try:
        parsed = await khata_engine.extract_khata_entry(text)
    except AIUnavailableError:
        await message.reply_text(
            "⚠️ AI service abhi unavailable hai, isliye entry nahi bana paaya.\n"
            "Thodi der baad try kijiye."
        )
        return

    if not parsed.customer_name or parsed.amount <= 0:
        await message.reply_text(
            "🤔 Entry samajh nahi aayi.\n\n"
            "Aise likhiye: \"Ramesh ne 500 rupaye udhaar liye\""
        )
        return

    try:
        entry = await khata_service.add_entry(
            merchant_id=user["_id"], customer_name=parsed.customer_name,
            amount=parsed.amount, entry_type=parsed.entry_type,
            description=parsed.description or text, source=source,
        )
    except KhataError as exc:
        await message.reply_text(f"⚠️ {exc}")
        return

    balance = await khata_service.balance_for(user["_id"], entry["customer_name"])
    verb = "udhaar" if entry["entry_type"] == "credit" else "payment"
    confidence_note = "\n\n⚠️ Confidence kam thi — check kar lijiye." if parsed.confidence < 0.6 else ""
    await message.reply_text(
        f"✅ Entry saved\n\n"
        f"👤 {entry['customer_name']}\n"
        f"💰 ₹{entry['amount']:g} ({verb})\n"
        f"📒 Outstanding: ₹{balance.outstanding:g}{confidence_note}"
    )


async def handle_reminder_request(update: Update, context: ContextTypes.DEFAULT_TYPE, user,
                                  text: str) -> bool:
    parts = text.split()
    if len(parts) < 2 or "@" not in parts[-1]:
        await update.effective_message.reply_text(
            "Format: <naam> <email>\nJaise: Ramesh ramesh@example.com"
        )
        return True
    email = parts[-1]
    name = " ".join(parts[:-1])
    balance = await khata_service.balance_for(user["_id"], name)
    if balance.outstanding <= 0:
        await update.effective_message.reply_text(
            f"ℹ️ {name} ka koi outstanding amount nahi hai. Reminder nahi bheja."
        )
        states.clear_mode(context)
        return True

    from app.bot.middleware import current_shop
    shop = await current_shop(user)
    sent = await email_service.send_khata_reminder(
        email, name, (shop or {}).get("shop_name", "the shop"), balance.outstanding
    )
    states.clear_mode(context)
    await update.effective_message.reply_text(
        f"📧 Reminder {'bhej diya' if sent else 'nahi ja paaya (SMTP issue)'}: "
        f"{name} — ₹{balance.outstanding:g}"
    )
    return True
