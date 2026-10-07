"""Optional inventory items. The marketplace works fine with zero of these."""
from typing import Dict, Optional

from app.models.user import utcnow
from app.utils.parsing import normalize_text


def product_key(name: str) -> str:
    """Stable lookup key so 'Teflon Tape' and 'teflon  tape' collapse together."""
    return normalize_text(name).lower()


def build_inventory_document(
    *, shop_id, product: str, quantity: float = 0, unit: str = "piece",
    brand: Optional[str] = None, price: Optional[float] = None,
    source: str = "manual", confidence: float = 1.0,
    image_url: Optional[str] = None,
    image_source: str = "none",  # manual | ai_fetched | none
    in_stock: Optional[bool] = None,
) -> Dict:
    now = utcnow()
    qty = float(quantity or 0)
    return {
        "shop_id": shop_id,
        "product": normalize_text(product),
        "product_key": product_key(product),
        "quantity": qty,
        "unit": unit or "piece",
        "brand": brand,
        "price": price,
        "source": source,  # manual | voice | invoice_image | shelf_image
        "confidence": confidence,
        # Product image — either uploaded by the shopkeeper (manual) or
        # auto-fetched from Pexels when the shopkeeper skips the photo
        # upload (ai_fetched). The Browse page shows this image on the
        # product card; without it, a neutral placeholder is shown.
        "image_url": image_url,
        "image_source": image_source,
        # in_stock defaults to (quantity > 0) if not explicitly set.
        "in_stock": in_stock if in_stock is not None else qty > 0,
        "created_at": now,
        "updated_at": now,
    }
