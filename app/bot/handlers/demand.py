"""Demand intelligence reports for merchants and customers."""
from telegram import Update
from telegram.ext import ContextTypes

from app.bot.middleware import current_shop, require_db, require_linked, with_request_id
from app.models.user import UserRole
from app.services import demand_engine, search_service
from app.services.location_service import location_of


@with_request_id
@require_db
@require_linked()
async def demand_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    message = update.effective_message

    if user.get("role") == UserRole.SHOPKEEPER.value:
        shop = await current_shop(user)
        own = await demand_engine.top_products(merchant_id=shop["_id"], limit=8)
        if own:
            await message.reply_text(
                demand_engine.format_demand_report(own, title="AAPKI SHOP KI DEMAND")
            )
        location = location_of(shop or {})
        if location:
            nearby = await demand_engine.nearby_demand(location[0], location[1],
                                                       radius_meters=2000, limit=8)
            await message.reply_text(
                demand_engine.format_demand_report(nearby, title="AAS-PAAS KI DEMAND (2km)")
            )
        elif not own:
            await message.reply_text(
                "📊 Abhi koi demand data nahi hai. Pehle apni shop location set kijiye."
            )
        return

    rows = await demand_engine.top_products(limit=8)
    await message.reply_text(demand_engine.format_demand_report(rows))


@with_request_id
@require_db
@require_linked()
async def compare_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    """/compare <product> — only real, merchant-confirmed or stored prices."""
    message = update.effective_message
    product = " ".join(context.args or []).strip()
    if not product:
        await message.reply_text("Likhiye: /compare electrical tape")
        return
    offers = await search_service.compare_prices({"product": product})
    await message.reply_text(search_service.format_price_comparison(product, offers))
