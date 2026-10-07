"""AI-powered product image fetch.

When a shopkeeper adds a product to their inventory, they can optionally
upload a photo. If they don't, this service fetches one automatically.

Image sources (tried in order):
  1. Pexels (if PEXELS_API_KEY is set) — high-quality stock photos
  2. Openverse API (https://api.openverse.org) — no key needed, aggregates
     CC-licensed images from Wikimedia Commons, Flickr, museums, etc.
     This is the default for the hackathon since Pexels key issuance
     is currently paused.
  3. Lorem Picsum (https://picsum.photos) — last-resort placeholder that
     returns a consistent image based on a seed (not a real product
     photo, but at least something visual).

The "AI" flavour: Gemini optionally expands the product name into a better
search query (e.g. "Teflon Tape" -> "white PTFE plumbing thread seal tape")
so the image search returns more relevant results.

All results are cached in the ``product_images`` collection for 24 hours
so we don't re-fetch the same product image every time.
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
    """Fetch a product image URL. Caches for 24 hours.

    Tries Pexels (if configured) → Openverse (no key) → Picsum placeholder.
    Returns the image URL or a Picsum placeholder URL (never None so the
    Browse page always has *something* to show).
    """
    pkey = product_key(product_name)

    # Check cache
    cached = await _read_cache(pkey)
    if cached:
        return cached

    # Build the search query. Use Gemini for query expansion if available;
    # otherwise just use the product name + a category suffix.
    query = await _expand_query(product_name, category)
    logger.info("fetching product image | product=%s query=%s", product_name, query)

    # Try Pexels first (if key is set)
    image_url = None
    if settings.PEXELS_API_KEY:
        image_url = await _fetch_from_pexels(query)
    if not image_url:
        image_url = await _fetch_from_openverse(query)
    if not image_url:
        # Last resort: a deterministic placeholder so the Browse page
        # always has a visual. picsum.photos/seed/<key>/400/300 returns
        # the same image for a given seed — consistent, not random.
        image_url = f"https://picsum.photos/seed/{pkey}/400/300"

    await _write_cache(pkey, product_name, image_url)
    logger.info("product image fetched | product=%s url=%s", product_name, image_url)
    return image_url


async def _fetch_from_pexels(query: str) -> Optional[str]:
    """Fetch from Pexels API. Requires PEXELS_API_KEY."""
    if not settings.PEXELS_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.pexels.com/v1/search",
                params={"query": query, "per_page": 1, "orientation": "square"},
                headers={"Authorization": settings.PEXELS_API_KEY},
            )
            if response.status_code != 200:
                logger.warning("Pexels search failed | status=%s", response.status_code)
                return None
            data = response.json()
            photos = data.get("photos") or []
            if not photos:
                return None
            return (photos[0].get("src") or {}).get("medium") \
                or (photos[0].get("src") or {}).get("large")
    except Exception as exc:
        logger.error("Pexels fetch exception | %s", exc)
        return None


async def _fetch_from_openverse(query: str) -> Optional[str]:
    """Fetch from Openverse API. No API key needed.

    Openverse aggregates CC-licensed images from Wikimedia Commons,
    Flickr, museums, etc. Anonymous tier: ~100 requests/day.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.openverse.org/v1/images",
                params={
                    "q": query,
                    "page_size": 1,
                    "mature": "false",
                },
                headers={"User-Agent": "Vyapaar-Mitra/1.0"},
            )
            if response.status_code != 200:
                logger.warning("Openverse search failed | status=%s", response.status_code)
                return None
            data = response.json()
            results = data.get("results") or []
            if not results:
                return None
            # Openverse returns 'url' (the direct image URL) and
            # 'thumbnail' (a smaller version). Use the thumbnail for
            # faster loading on the Browse grid.
            return results[0].get("thumbnail") or results[0].get("url")
    except Exception as exc:
        logger.error("Openverse fetch exception | %s", exc)
        return None


async def _expand_query(product_name: str, category: Optional[str]) -> str:
    """Use Gemini to expand a product name into a better search query.

    Example: 'Teflon Tape' -> 'white PTFE plumbing thread seal tape'
    Falls back to plain '{product} {category} product india' if Gemini is
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
            f"Reply with a 3-6 word search query that would return a relevant photo. "
            f"Reply with ONLY the query, no quotes, no explanation. "
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
    """Cache a fetch result so we don't hammer the image APIs."""
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
