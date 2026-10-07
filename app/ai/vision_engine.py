"""Vision engine: photographs -> ProductIntent / inventory lines.

Image search does NOT get its own search system. It produces a ProductIntent and
then joins the exact same merchant-matching pipeline as text and voice.
"""
from typing import Optional

from app.ai.base import ProviderError
from app.ai.intent_engine import AIUnavailableError
from app.ai.prompts import INVOICE_SYSTEM, VISION_SYSTEM, VISION_USER
from app.ai.providers import vision_chain
from app.config.settings import settings
from app.schemas.intent import InventoryExtraction, ProductIntent
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def _vision_call(image_bytes: bytes, prompt: str, system: str, mime_type: str):
    errors = []
    for provider in vision_chain():
        if not provider.is_configured:
            continue
        try:
            logger.info("Vision started | provider=%s", provider.name)
            data = await provider.analyze_image(
                image_bytes, prompt, mime_type=mime_type, system=system
            )
            logger.info("Vision completed | provider=%s", provider.name)
            return data, provider.name
        except ProviderError as exc:
            errors.append(str(exc))
            logger.warning("Vision provider %s failed: %s", provider.name, exc.message)
        except Exception as exc:
            errors.append(f"[{provider.name}] {exc.__class__.__name__}")
    raise AIUnavailableError("; ".join(errors) or "no vision-capable provider is configured")


async def analyze_product_image(image_bytes: bytes, *, caption: str = "",
                                mime_type: str = "image/jpeg") -> ProductIntent:
    prompt = VISION_USER.format(caption=(caption or "").strip())
    data, provider_name = await _vision_call(image_bytes, prompt, VISION_SYSTEM, mime_type)
    intent = ProductIntent(**{k: v for k, v in data.items() if k in ProductIntent.model_fields})
    intent.provider = provider_name
    intent.uncertain = (
        settings.CONFIDENCE_UNCERTAIN <= intent.confidence < settings.CONFIDENCE_DIRECT
    )
    logger.info("image intent | product=%s confidence=%.2f", intent.product, intent.confidence)
    return intent


async def extract_inventory_from_image(image_bytes: bytes, *, hint: Optional[str] = None,
                                       mime_type: str = "image/jpeg") -> InventoryExtraction:
    """Wholesale invoice or shelf photo -> candidate stock lines (optional feature)."""
    prompt = "Extract the stock items from this image."
    if hint:
        prompt += f" Context from the shopkeeper: \"{hint}\""
    data, _ = await _vision_call(image_bytes, prompt, INVOICE_SYSTEM, mime_type)
    items = data.get("items") or []
    cleaned = []
    for item in items[:25]:
        if not isinstance(item, dict) or not item.get("product"):
            continue
        cleaned.append({
            "product": str(item.get("product")).strip(),
            "quantity": item.get("quantity") or 1,
            "unit": item.get("unit") or "piece",
            "brand": item.get("brand"),
            "price": item.get("price"),
            "confidence": item.get("confidence", 0.5),
        })
    return InventoryExtraction(
        items=cleaned, source_type=data.get("source_type") or "invoice", notes=data.get("notes")
    )
