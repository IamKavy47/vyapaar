"""Admin-only diagnostics."""
from telegram import Update
from telegram.ext import ContextTypes

from app.ai.providers import provider_status
from app.config.settings import settings
from app.database import mongo as m
from app.database.mongo import mongo
from app.bot.middleware import telegram_id, with_request_id
from app.services import demand_engine
from app.utils.security import password_backend


def _is_admin(update: Update) -> bool:
    return telegram_id(update) in settings.admin_ids


@with_request_id
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await update.effective_message.reply_text("🚫 Yeh command sirf admins ke liye hai.")
        return
    if not mongo.connected:
        await update.effective_message.reply_text("⚠️ MongoDB connected nahi hai.")
        return

    counts = {
        "users": await m.users().count_documents({}),
        "shops": await m.shops().count_documents({}),
        "shops_without_inventory": 0,
        "requests": await m.product_requests().count_documents({}),
        "matches": await m.merchant_matches().count_documents({}),
        "demand_events": await m.demand_events().count_documents({}),
        "khata_entries": await m.khata_entries().count_documents({}),
    }
    shop_ids = [doc["_id"] async for doc in m.shops().find({}, {"_id": 1})]
    with_inventory = await m.inventory_items().distinct("shop_id")
    counts["shops_without_inventory"] = len(
        [sid for sid in shop_ids if sid not in set(with_inventory)]
    )

    providers = provider_status()
    lines = ["🛠️ ADMIN STATUS", ""]
    lines += [f"{key}: {value}" for key, value in counts.items()]
    lines += ["", "AI providers:"]
    lines += [f"• {name}: {'✅' if ok else '❌ not configured'}" for name, ok in providers.items()]
    lines += [
        "", f"Password hashing: {password_backend()}",
        f"Demo mode: {settings.DEMO_MODE}",
        f"Match radius: {settings.MATCH_RADIUS_METERS}m -> {settings.MAX_MATCH_RADIUS_METERS}m",
        f"Email configured: {settings.email_enabled}",
    ]
    await update.effective_message.reply_text("\n".join(lines))


@with_request_id
async def admin_demand(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await update.effective_message.reply_text("🚫 Yeh command sirf admins ke liye hai.")
        return
    rows = await demand_engine.top_products(limit=15)
    await update.effective_message.reply_text(
        demand_engine.format_demand_report(rows, title="PLATFORM DEMAND")
    )
