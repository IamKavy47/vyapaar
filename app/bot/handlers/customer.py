"""Customer menu, location sharing and search history."""
from telegram import Update
from telegram.ext import ContextTypes

from app.bot import keyboards, states
from app.bot.middleware import handle_errors, require_db, require_linked, with_request_id
from app.config.settings import settings
from app.models.user import UserRole
from app.services import khata_service, merchant_matching, search_service
from app.services.location_service import (
    InvalidLocationError, clamp_search_radius, get_search_radius, set_search_radius,
    update_customer_location, update_shop_location,
)
from app.utils.geo import humanize_distance


@with_request_id
@require_db
@require_linked()
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    """Telegram location messages work for both roles."""
    message = update.effective_message
    location = message.location
    if not location:
        await message.reply_text("📍 Location nahi mili. Dobara bhejiye.")
        return
    try:
        if user.get("role") == UserRole.SHOPKEEPER.value:
            await update_shop_location(user["_id"], location.latitude, location.longitude)
            await message.reply_text(
                "✅ Shop location save ho gayi. Ab aas-paas ke customers ki requests aapko milengi.",
                reply_markup=keyboards.merchant_menu(),
            )
        else:
            await update_customer_location(user["_id"], location.latitude, location.longitude)
            await message.reply_text(
                "✅ Location save ho gayi!", reply_markup=keyboards.customer_menu()
            )
            from app.bot.handlers.search import resume_pending_search
            await resume_pending_search(update, context, user)
    except InvalidLocationError:
        await message.reply_text("⚠️ Yeh location valid nahi lagi. Dobara bhejiye.")


@with_request_id
@require_db
@require_linked()
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    requests = await search_service.recent_requests(user["_id"], limit=5)
    if not requests:
        await update.effective_message.reply_text(
            "🔎 Abhi tak koi search nahi hui.\nBataiye, aapko kya chahiye?"
        )
        return
    lines = ["🔎 Recent Searches", ""]
    ids, labels = [], []
    for doc in requests:
        product = doc.get("product") or "(unknown)"
        lines.append(f"• {product} — {doc.get('status', '').lower()}")
        ids.append(doc["request_id"])
        labels.append(product)
    await update.effective_message.reply_text(
        "\n".join(lines), reply_markup=keyboards.repeat_request_keyboard(ids, labels)
    )


@with_request_id
@require_db
@require_linked()
async def my_requests(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    requests = await search_service.recent_requests(user["_id"], limit=5)
    if not requests:
        await update.effective_message.reply_text("🧾 Abhi koi request nahi hai.")
        return
    lines = ["🧾 MY REQUESTS", ""]
    for doc in requests:
        lines.append(f"🔧 {doc.get('product') or '(unknown)'}")
        lines.append(f"   Status: {doc.get('status')} · {doc.get('matched_count', 0)} shops asked")
        offers = await merchant_matching.accepted_offers(doc["request_id"])
        for offer in offers:
            price = f" — ₹{offer['price']:g}" if offer.get("price") is not None else ""
            lines.append(f"   ✅ {offer['shop_name']} "
                         f"({humanize_distance(offer.get('distance_meters') or 0)}){price}")
        lines.append("")
    await update.effective_message.reply_text("\n".join(lines))


@with_request_id
@require_db
@require_linked()
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    from app.services.location_service import get_customer_location
    location = await get_customer_location(user["_id"])
    radius = await get_search_radius(user["_id"])
    lines = [
        "⚙️ PROFILE", "",
        f"👤 {user.get('full_name')}",
        f"📧 {user.get('email')}",
        f"📞 {user.get('phone')}",
        f"🎭 Role: {user.get('role')}",
        f"📍 Location: {'saved ✅' if location else 'not set ❌'}",
        f"📏 Search range: {humanize_distance(radius)}",
    ]
    await update.effective_message.reply_text("\n".join(lines))


@with_request_id
@require_db
@require_linked()
async def ask_location(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    await update.effective_message.reply_text(
        "📍 Apni current location share kijiye:",
        reply_markup=keyboards.location_request_keyboard(),
    )


@with_request_id
@require_db
@require_linked()
async def customer_khata(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    """Customers see what they owe across shops that recorded them by name."""
    result = await khata_service.summary(user["_id"])
    if not result.balances:
        await update.effective_message.reply_text(
            "📒 Aapka koi khata record nahi hai.\n"
            "Shopkeepers jab entry karte hain, tab yahan dikhta hai."
        )
        return
    await update.effective_message.reply_text(khata_service.format_summary(result))


async def prompt_find_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    states.set_mode(context, states.MODE_SEARCH)
    await update.effective_message.reply_text(
        "🔎 Bataiye aapko kya chahiye?\n\n"
        "Jaise: \"1 inch PVC pipe chahiye\"\n"
        "Ya seedha voice note / photo bhej dijiye."
    )


async def prompt_voice_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    states.set_mode(context, states.MODE_SEARCH)
    await update.effective_message.reply_text(
        "🎤 Voice note record kijiye — Hindi, Hinglish ya English, jo comfortable ho.\n\n"
        "Jaise: \"Mere sink ke niche pipe leak ho raha hai, usko rokne wala safed tape chahiye.\""
    )


async def prompt_photo_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    states.set_mode(context, states.MODE_SEARCH)
    await update.effective_message.reply_text(
        "📷 Product ki photo bhejiye — packet, part ya jo item chahiye uski tasveer."
    )


@with_request_id
@require_db
@require_linked()
@handle_errors("customer.range_command")
async def range_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    """Shows the customer's current search/browse range and lets them change it.

    Search and Browse both read this same setting (location_service.get_search_radius),
    so widening it here immediately affects both — one range, not two to keep in sync.
    """
    states.clear_mode(context)
    current = await get_search_radius(user["_id"])
    await update.effective_message.reply_text(
        "📏 SEARCH RANGE\n\n"
        f"Abhi aapki range: {humanize_distance(current)}\n\n"
        "Yeh range 🔎 Find Product aur 🛒 Browse Nearby dono mein use hoti hai. "
        "Bada shehar? Chhota rakhiye. Gaon mein rehte hain? Zyada rakhiye — "
        f"{humanize_distance(settings.SEARCH_RADIUS_MIN_METERS)} se "
        f"{humanize_distance(settings.SEARCH_RADIUS_MAX_METERS)} tak set kar sakte hain.",
        reply_markup=keyboards.range_keyboard(current, settings.search_radius_presets),
    )


@with_request_id
@require_db
@require_linked()
@handle_errors("customer.range_callback")
async def range_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    """Handles rng:<meters> and rng:custom."""
    query = update.callback_query
    await query.answer()
    value = query.data.split(":", 1)[1]

    if value == "custom":
        states.set_mode(context, states.MODE_AWAIT_RADIUS)
        await query.message.reply_text(
            "✏️ Kitne kilometre? Sirf number likhiye.\n\n"
            f"Jaise: 3  (matlab 3km). Range {settings.SEARCH_RADIUS_MIN_METERS // 1000}km "
            f"se {settings.SEARCH_RADIUS_MAX_METERS // 1000}km ke beech honi chahiye."
        )
        return

    try:
        meters = int(value)
    except ValueError:
        await query.message.reply_text("⚠️ Value samajh nahi aayi. Dobara try kijiye.")
        return
    saved = await set_search_radius(user["_id"], meters)
    await query.edit_message_text(
        f"✅ Range set: {humanize_distance(saved)}\n\n"
        "Agli search ya browse se yeh naya range use hoga.",
    )


async def handle_range_text(update: Update, context: ContextTypes.DEFAULT_TYPE, user,
                            text: str) -> bool:
    """Customer typed a custom range after tapping ✏️ Enter exact distance."""

    cleaned = text.strip().lower().replace("km", "").replace("kilometre", "").replace(
        "kilometer", ""
    ).strip()
    try:
        km = float(cleaned)
    except ValueError:
        await update.effective_message.reply_text(
            "⚠️ Samajh nahi aaya. Sirf number likhiye, jaise: 3 (3km ke liye)."
        )
        return True

    if km <= 0:
        await update.effective_message.reply_text(
            "⚠️ Range 0 ya usse kam nahi ho sakti. Kripya ek positive number likhiye."
        )
        return True

    requested_meters = km * 1000
    saved = await set_search_radius(user["_id"], requested_meters)
    states.clear_mode(context)

    note = ""
    if clamp_search_radius(requested_meters) != int(requested_meters):
        note = (f"\n\nℹ️ Range {settings.SEARCH_RADIUS_MIN_METERS // 1000}km se "
                f"{settings.SEARCH_RADIUS_MAX_METERS // 1000}km ke beech hi ho sakti hai, "
                "isliye adjust kar di gayi.")
    await update.effective_message.reply_text(
        f"✅ Range set: {humanize_distance(saved)}{note}\n\n"
        "Agli search ya browse se yeh naya range use hoga.",
        reply_markup=keyboards.customer_menu(),
    )
    return True
