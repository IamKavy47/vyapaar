"""Customer search: text, voice and image all converge on one pipeline."""
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from app.ai import intent_engine, vision_engine
from app.ai.intent_engine import AIUnavailableError, confidence_band
from app.bot import keyboards, states
from app.bot.middleware import (
    rate_limit_ai, require_db, require_linked, with_request_id,
)
from app.config.settings import settings
from app.models.user import UserRole
from app.schemas.intent import ProductIntent
from app.services import search_service
from app.services.location_service import get_customer_location
from app.utils.geo import humanize_distance
from app.utils.logging import get_logger

logger = get_logger(__name__)

ACK_VOICE = "🔍 Samajh raha hoon...\nNearby shops locate kar raha hoon."
ACK_TEXT = "🔍 Samajh raha hoon..."
ACK_IMAGE = "🔍 Photo dekh raha hoon...\nProduct identify kar raha hoon."

NO_LOCATION = (
    "📍 Pehle apni location bhej dijiye, tabhi main aas-paas ki shops dhoondh sakta hoon.\n\n"
    "Neeche '📍 Share Location' button dabaiye."
)

AI_DOWN = (
    "⚠️ AI service abhi respond nahi kar rahi hai.\n"
    "Main jhooti jaankari nahi de sakta. Kripya thodi der baad phir try kijiye."
)

STT_DOWN = (
    "🎤 Voice abhi process nahi ho pa rahi (speech service unavailable).\n"
    "Aap type karke bhej dijiye — matching waise hi kaam karegi."
)


async def _customer_location(user) -> Optional[tuple]:
    return await get_customer_location(user["_id"])


async def _run_pipeline(update: Update, context: ContextTypes.DEFAULT_TYPE, user,
                        intent: ProductIntent, *, input_type: str,
                        raw_text: str = "", transcript: str = "") -> None:
    message = update.effective_message

    if intent.intent in {"greeting", "help"} or not intent.product:
        await message.reply_text(
            "🙏 Namaste! Bataiye aapko kya chahiye.\n"
            "Jaise: \"1 inch PVC pipe chahiye\" ya voice note bhejiye."
        )
        return

    band = confidence_band(intent.confidence)
    if band == "clarify":
        options = intent_engine.clarification_options(intent)
        context.user_data[states.PENDING_INTENT] = {
            "intent": intent.model_dump(), "input_type": input_type,
            "raw_text": raw_text, "transcript": transcript,
        }
        if options:
            await message.reply_text(
                "🤔 Main poori tarah sure nahi hoon ki aapko kya chahiye.\n\nDid you mean:",
                reply_markup=keyboards.clarification_keyboard(options),
            )
        else:
            await message.reply_text(
                "🤔 Main samajh nahi paaya. Thoda detail mein likhiye, ya product ki photo bhejiye."
            )
        return

    location = await _customer_location(user)
    if not location:
        await message.reply_text(
            NO_LOCATION, reply_markup=keyboards.location_request_keyboard()
        )
        context.user_data[states.PENDING_INTENT] = {
            "intent": intent.model_dump(), "input_type": input_type,
            "raw_text": raw_text, "transcript": transcript,
        }
        return

    latitude, longitude = location
    request = await search_service.create_request(
        intent=intent, customer_id=user["_id"],
        telegram_user_id=update.effective_user.id, latitude=latitude, longitude=longitude,
        input_type=input_type, raw_text=raw_text, transcript=transcript,
    )
    context.user_data[states.LAST_REQUEST_ID] = request["request_id"]

    summary = [f"🔧 {intent.product}"]
    if transcript:
        summary.insert(0, f"🗣️ \"{transcript}\"")
    if band == "uncertain":
        summary.append("(thoda unsure hoon — shops se confirm karwata hoon)")
    await message.reply_text("\n".join(summary))

    result = await search_service.run_matching(request, notify=True)

    if not result.candidates:
        await message.reply_text(
            f"😔 {humanize_distance(result.radius_used_meters)} ke andar koi "
            "matching shop nahi mili.\n\nAapki request demand data mein record ho gayi hai — "
            "jaise hi koi shop aayegi, aapko pata chalega.\n\n"
            "📏 Range badhane ke liye 📏 Range button dabaiye."
        )
        return

    await message.reply_text(
        f"📨 {result.notified} nearby shop(s) ko aapki request bhej di hai "
        f"({humanize_distance(result.radius_used_meters)} radius).\n\n"
        "Jaise hi koi shop confirm karega, aapko turant message milega. ⏳"
    )


@with_request_id
@require_db
@require_linked()
@rate_limit_ai
async def handle_text_search(update: Update, context: ContextTypes.DEFAULT_TYPE, user,
                             text: Optional[str] = None) -> None:
    message = update.effective_message
    query = (text or message.text or "").strip()
    if len(query) < 2:
        await message.reply_text("Kripya thoda detail mein bataiye aapko kya chahiye.")
        return
    await message.reply_text(ACK_TEXT)
    try:
        intent = await intent_engine.extract_intent(query, input_type="text")
    except AIUnavailableError as exc:
        logger.error("intent extraction failed: %s", exc)
        await message.reply_text(AI_DOWN)
        return
    await _run_pipeline(update, context, user, intent, input_type="text", raw_text=query)


@with_request_id
@require_db
@require_linked()
@rate_limit_ai
async def handle_voice_search(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    message = update.effective_message
    # Immediate acknowledgement — never make the customer wait for STT.
    await message.reply_text(ACK_VOICE)

    voice = message.voice or message.audio
    if not voice:
        await message.reply_text("🎤 Voice note samajh nahi aaya. Dobara bhejiye.")
        return
    try:
        telegram_file = await voice.get_file()
        audio_bytes = bytes(await telegram_file.download_as_bytearray())
    except Exception as exc:
        logger.warning("voice download failed | user=%s error=%s: %s",
                       (user or {}).get("_id"), exc.__class__.__name__, exc)
        await message.reply_text("🎤 Voice download nahi ho paayi. Dobara try kijiye.")
        return

    try:
        transcript = await intent_engine.transcribe_voice(
            audio_bytes, mime_type=getattr(voice, "mime_type", None) or "audio/ogg"
        )
    except Exception as exc:
        logger.warning("STT failed | user=%s error=%s: %s",
                       (user or {}).get("_id"), exc.__class__.__name__, exc)
        await message.reply_text(STT_DOWN)
        return

    if states.get_mode(context) == states.MODE_KHATA:
        from app.bot.handlers.khata import process_khata_text
        await process_khata_text(update, context, user, transcript, source="voice")
        return
    if states.get_mode(context) == states.MODE_INVENTORY:
        from app.bot.handlers.inventory import process_inventory_text
        await process_inventory_text(update, context, user, transcript)
        return

    if (user or {}).get("role") == UserRole.SHOPKEEPER.value:
        await message.reply_text(
            "🏪 Shopkeeper voice note ke liye pehle mode chuniye:\n"
            "📒 Khata ya 📦 Inventory."
        )
        return

    try:
        intent = await intent_engine.extract_intent(transcript, input_type="voice")
    except AIUnavailableError:
        await message.reply_text(AI_DOWN)
        return
    await _run_pipeline(update, context, user, intent, input_type="voice",
                        raw_text=transcript, transcript=transcript)


@with_request_id
@require_db
@require_linked()
@rate_limit_ai
async def handle_photo_search(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    message = update.effective_message
    photos = message.photo
    if not photos:
        await message.reply_text("📷 Photo nahi mili. Dobara bhejiye.")
        return

    if (user or {}).get("role") == UserRole.SHOPKEEPER.value or \
            states.get_mode(context) == states.MODE_INVENTORY:
        from app.bot.handlers.inventory import process_inventory_photo
        await process_inventory_photo(update, context, user)
        return

    await message.reply_text(ACK_IMAGE)
    try:
        telegram_file = await photos[-1].get_file()
        image_bytes = bytes(await telegram_file.download_as_bytearray())
    except Exception as exc:
        logger.warning("photo download failed | user=%s error=%s: %s",
                       (user or {}).get("_id"), exc.__class__.__name__, exc)
        await message.reply_text("📷 Photo download nahi ho paayi. Dobara try kijiye.")
        return

    try:
        intent = await vision_engine.analyze_product_image(
            image_bytes, caption=message.caption or ""
        )
    except AIUnavailableError:
        await message.reply_text(
            "⚠️ Image service abhi unavailable hai. Aap product ka naam likh kar bhej dijiye."
        )
        return

    if not intent.product:
        await message.reply_text(
            "🤔 Photo se product clearly identify nahi hua.\n"
            "Thoda paas se photo lijiye, ya naam likh kar bhejiye."
        )
        return

    await _run_pipeline(update, context, user, intent, input_type="image",
                        raw_text=message.caption or "")


@with_request_id
@require_db
@require_linked()
async def clarification_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    query = update.callback_query
    await query.answer()
    choice = query.data.split(":", 1)[1]
    pending = context.user_data.get(states.PENDING_INTENT)

    if choice == "other" or not pending:
        context.user_data.pop(states.PENDING_INTENT, None)
        await query.message.reply_text(
            "✍️ Theek hai — product ka naam likhiye ya uski photo bhejiye."
        )
        return

    intent = ProductIntent(**pending["intent"])
    options = intent_engine.clarification_options(intent)
    try:
        selected = options[int(choice)]
    except (ValueError, IndexError):
        await query.message.reply_text("Option samajh nahi aaya. Dobara bhejiye.")
        return

    intent.product = selected
    intent.confidence = max(intent.confidence, settings.CONFIDENCE_DIRECT)
    context.user_data.pop(states.PENDING_INTENT, None)
    await query.edit_message_text(f"✅ {selected}")
    await _run_pipeline(update, context, user, intent,
                        input_type=pending.get("input_type", "text"),
                        raw_text=pending.get("raw_text", ""),
                        transcript=pending.get("transcript", ""))


async def resume_pending_search(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> bool:
    """Called after a customer shares location mid-search."""
    pending = context.user_data.pop(states.PENDING_INTENT, None)
    if not pending:
        return False
    intent = ProductIntent(**pending["intent"])
    await _run_pipeline(update, context, user, intent,
                        input_type=pending.get("input_type", "text"),
                        raw_text=pending.get("raw_text", ""),
                        transcript=pending.get("transcript", ""))
    return True


@with_request_id
@require_db
@require_linked()
async def repeat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    query = update.callback_query
    await query.answer()
    request_id = query.data.split(":", 1)[1]
    old = await search_service.get_request(request_id)
    if not old:
        await query.message.reply_text("Yeh request ab available nahi hai.")
        return
    intent = ProductIntent(
        intent="find_product", product=old.get("product"), category=old.get("category"),
        sub_category=old.get("sub_category"), quantity=old.get("quantity", 1),
        unit=old.get("unit", "piece"), brand=old.get("brand"),
        description=old.get("description"), confidence=max(0.85, old.get("confidence", 0.85)),
        alternative_products=old.get("alternative_products", []),
    )
    await query.message.reply_text(f"🔁 Dobara dhoondh raha hoon: {intent.product}")
    await _run_pipeline(update, context, user, intent, input_type="text",
                        raw_text=old.get("raw_text", ""))
