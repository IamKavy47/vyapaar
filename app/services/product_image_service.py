"""AI-powered product image fetch.

When a shopkeeper adds a product to their inventory, they can optionally
upload a photo. If they don't, this service fetches one from Pexels (free,
real stock photos). The "AI" flavour:

  1. The product name (e.g. "Teflon Tape") is optionally passed through
     Gemini for query expansion -> "white PTFE plumbing thread seal tape"
     so the Pexels search returns more relevant results.
  2. The expanded query is sent to the Pexels /v1/search endpoint.
  3. The first result's `src.medium` URL is cached in the `product_images`
     collection for 24 hours so we don't re-fetch the same product image
     every time a shopkeeper adds the same product.

If Pexels is not configured (no PEXELS_API_KEY), returns None — the Browse
page shows a neutral placeholder.
"""
from datetime import timedelta
from typing import Optional

import httpx

from app.config.settings import settings
from app.database import mongo as m
from app.models.inventory import product_key
from app.models.user import utcnow
from app.utils.logging import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 24 * 3600  # 24 hours


async def fetch_product_image(product_name: str,
                              category: Optional[str] = None) -> Optional[str]:
    """Fetch a product image URL from Pexels. Caches for 24 hours.

    Returns the image URL (a public https://images.pexels.com/... URL)
    or None if Pexels is not configured / fails / returns no results.
    """
    if not settings.PEXELS_API_KEY:
        logger.debug("Pexels not configured — skipping product image fetch")
        return None

    pkey = product_key(product_name)
    cached = await _read_cache(pkey)
    if cached:
        return cached

    # Build the search query. Use Gemini for query expansion if available;
    # otherwise just use the product name + a category suffix.
    query = await _expand_query(product_name, category)
    logger.info("fetching product image | product=%s query=%s", product_name, query)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.pexels.com/v1/search",
                params={
                    "query": query,
                    "per_page": 1,
                    "orientation": "square",
                },
                headers={"Authorization": settings.PEXELS_API_KEY},
            )
            if response.status_code != 200:
                logger.warning("Pexels search failed | status=%s body=%s",
                               response.status_code, response.text[:200])
                await _write_cache(pkey, product_name, None)
                return None
            data = response.json()
            photos = data.get("photos") or []
            if not photos:
                logger.info("Pexels returned 0 photos for query=%s", query)
                await _write_cache(pkey, product_name, None)
                return None
            image_url = (photos[0].get("src") or {}).get("medium") \
                or (photos[0].get("src") or {}).get("large")
            if not image_url:
                await _write_cache(pkey, product_name, None)
                return None
            await _write_cache(pkey, product_name, image_url)
            logger.info("product image fetched | product=%s url=%s", product_name, image_url)
            return image_url
    except Exception as exc:
        logger.error("Pexels fetch exception | %s | %s", exc.__class__.__name__, exc)
        return None


async def _expand_query(product_name: str, category: Optional[str]) -> str:
    """Use Gemini to expand a product name into a better Pexels search query.

    Example: "Teflon Tape" -> "white PTFE plumbing thread seal tape"
    Falls back to plain "{product} {category} product india" if Gemini is
    not configured or fails.
    """
    base = product_name.strip()
    if category:
        base = f"{base} {category}"
    suffix = settings.PRODUCT_IMAGE_SEARCH_SUFFIX or ""
    if suffix:
        base = f"{base} {suffix}"
    # Gemini query expansion — best-effort, never blocks on failure.
    if not settings.GEMINI_API_KEY:
        return base
    try:
        from app.ai.providers.gemini import GeminiProvider
        provider = GeminiProvider()
        prompt = (
            f"You are helping an e-commerce search engine find a stock photo for a product. "
            f"Product name: '{product_name}'. Category: '{category or 'unknown'}'. "
            f"Reply with a 3-6 word search query that would return a relevant photo on Pexels "
            f"(a stock photo site). Reply with ONLY the query, no quotes, no explanation. "
            f"Example: 'white PTFE plumbing thread seal tape'."
        )
        text = await provider.generate_text(prompt)
        expanded = (text or "").strip().strip('"').strip("'").strip()[:80]
        if expanded and len(expanded) > 3:
            return expanded
    except Exception as exc:
        logger.debug("Gemini query expansion failed (non-fatal) | %s", exc)
    return base


async def _read_cache(pkey: str) -> Optional[str]:
    """Read a cached image URL. Returns None if not cached or expired."""
    doc = await m.product_images().find_one({"product_key": pkey})
    if not doc:
        return None
    fetched_at = doc.get("fetched_at")
    if not fetched_at:
        return None
    age = (utcnow() - fetched_at).total_seconds()
    if age > CACHE_TTL_SECONDS:
        return None  # stale — caller will re-fetch
    return doc.get("image_url")


async def _write_cache(pkey: str, product_name: str, image_url: Optional[str]) -> None:
    """Cache a fetch result (success or None) so we don't hammer Pexels."""
    try:
        await m.product_images().update_one(
            {"product_key": pkey},
            {"$set": {
                "product_key": pkey,
                "product_name": product_name,
                "image_url": image_url,
                "fetched_at": utcnow(),
            }},
            upsert=True,
        )
    except Exception as exc:
        logger.warning("product image cache write failed (non-fatal) | %s", exc)
