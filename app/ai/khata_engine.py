"""Khata engine: shopkeeper's note (typed or spoken) -> structured ledger entry."""
from app.ai.intent_engine import _run_structured
from app.ai.prompts import INVENTORY_VOICE_SYSTEM, KHATA_SYSTEM, KHATA_USER_TEMPLATE
from app.schemas.intent import InventoryExtraction, KhataIntent
from app.utils.logging import get_logger
from app.utils.parsing import parse_amount_words

logger = get_logger(__name__)


async def extract_khata_entry(text: str) -> KhataIntent:
    prompt = KHATA_USER_TEMPLATE.format(text=text.strip())
    data, provider_name = await _run_structured(prompt, KHATA_SYSTEM, max_tokens=512)
    entry = KhataIntent(**{k: v for k, v in data.items() if k in KhataIntent.model_fields})

    # Safety net: Indian number words are a classic STT/LLM failure point.
    if entry.amount <= 0:
        fallback_amount = parse_amount_words(text)
        if fallback_amount:
            entry.amount = fallback_amount
            entry.confidence = min(entry.confidence, 0.6)
    logger.info(
        "khata entry | name=%s amount=%s type=%s provider=%s",
        entry.customer_name, entry.amount, entry.entry_type, provider_name,
    )
    return entry


async def extract_inventory_from_text(text: str) -> InventoryExtraction:
    """'Bhai 20 Fevicol ke bottle aaye hain' -> one inventory line."""
    data, _ = await _run_structured(
        f'Shopkeeper stock note: "{text.strip()}"', INVENTORY_VOICE_SYSTEM, max_tokens=512
    )
    items = []
    for item in (data.get("items") or [])[:25]:
        if isinstance(item, dict) and item.get("product"):
            items.append({
                "product": str(item["product"]).strip(),
                "quantity": item.get("quantity") or 1,
                "unit": item.get("unit") or "piece",
                "brand": item.get("brand"),
                "price": item.get("price"),
                "confidence": item.get("confidence", 0.6),
            })
    return InventoryExtraction(items=items, source_type="voice", notes=data.get("notes"))
