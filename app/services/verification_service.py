"""Shopfront photo verification — the visible trust signal customers see
before walking to a shop.

Flow:
  1. Shopkeeper taps "Capture shopfront photo" inside the PWA on their phone.
  2. The browser opens the rear camera via <input capture="environment"> and
     captures a JPEG. At the same moment, the browser records its current
     GPS via navigator.geolocation.
  3. The shopkeeper uploads the JPEG + the browser-captured GPS to
     ``POST /api/v1/merchant/shop/shopfront-photo``.
  4. This service parses the JPEG's EXIF GPS tags (cross-check #1) and
     compares both the EXIF GPS and the browser GPS to the registered shop
     location. Both must be within SHOPFRONT_PHOTO_DISTANCE_METERS (200m).
  5. The photo is **EXIF-stripped** (privacy — the saved/uploaded photo
     must not retain the GPS in its metadata) and uploaded to ImgBB if
     ``IMGBB_API_KEY`` is configured, otherwise saved to disk under
     ``app/static/shop_photos/{shop_id}.jpg``.
  6. The shop doc is updated with the photo URL + both GPS readings +
     ``verification_status="photo_pending"``.
  7. An admin (you, for the hackathon) reviews the pending photos via the
     /admin/shops/pending page and approves each one — flipping
     ``is_verified=True`` + ``verification_status="verified"``.

The shop remains invisible to customers (is_verified=False in
find_candidates' geoNear query) until step 6 completes.
"""
import io
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

from PIL import Image, UnidentifiedImageError

from app.config.settings import settings
from app.database import mongo as m
from app.models.user import utcnow
from app.utils.geo import haversine_meters
from app.utils.logging import get_logger

logger = get_logger(__name__)


class VerificationError(Exception):
    """User-facing verification failure — message is safe to display."""


def _dms_to_degrees(values: Tuple[float, float, float], ref: str) -> Optional[float]:
    """Convert EXIF GPS coordinates (degrees, minutes, seconds + N/S/E/W ref)
    into a single signed decimal-degrees float."""
    if not values or len(values) < 3:
        return None
    try:
        d, m, s = values[0], values[1], values[2]
        # 's' may be a tuple (e.g., (45.0, 1)) — PIL returns rationals as
        # (numerator, denominator).
        if isinstance(s, tuple):
            s = s[0] / s[1] if s[1] else 0.0
        if isinstance(d, tuple):
            d = d[0] / d[1] if d[1] else 0.0
        if isinstance(m, tuple):
            m = m[0] / m[1] if m[1] else 0.0
        decimal = float(d) + float(m) / 60.0 + float(s) / 3600.0
        if ref in ("S", "W"):
            decimal = -decimal
        return decimal
    except Exception:
        return None


def extract_exif_gps(image_bytes: bytes) -> Optional[Tuple[float, float]]:
    """Parse EXIF GPSLatitude / GPSLongitude from a JPEG's bytes.

    Returns (lat, lng) or None if no GPS is present. PIL doesn't always
    populate the GPS tag depending on the JPEG's source, so this is a
    best-effort signal — the browser's reported GPS at capture time is the
    primary signal.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
    except UnidentifiedImageError as exc:
        raise VerificationError("This file is not a valid image.") from exc
    except Exception as exc:
        raise VerificationError(f"Could not read image: {exc}") from exc

    try:
        exif = img._getexif() if hasattr(img, "_getexif") else None
    except Exception:
        exif = None
    if not exif:
        return None

    GPS_INFO_TAG = 0x8825  # IFD Pointer to GPS Info IFD
    gps_ifd = exif.get(GPS_INFO_TAG)
    if not gps_ifd:
        return None
    gps_data = exif.get(gps_ifd) if isinstance(gps_ifd, int) else gps_ifd
    if not isinstance(gps_data, dict):
        return None

    lat = _dms_to_degrees(
        gps_data.get("GPSLatitude"), gps_data.get("GPSLatitudeRef", "N"),
    )
    lng = _dms_to_degrees(
        gps_data.get("GPSLongitude"), gps_data.get("GPSLongitudeRef", "E"),
    )
    if lat is None or lng is None:
        return None
    return (lat, lng)


def _shop_location(shop: Dict) -> Optional[Tuple[float, float]]:
    """Pull the registered shop's (lat, lng) from its GeoJSON Point."""
    loc = shop.get("location")
    if not loc or loc.get("type") != "Point":
        return None
    coords = loc.get("coordinates") or []
    if len(coords) < 2:
        return None
    # GeoJSON is [lng, lat]; we want (lat, lng).
    return (coords[1], coords[0])


async def upload_shopfront_photo(
    *, shop_id, photo_bytes: bytes,
    browser_lat: Optional[float], browser_lng: Optional[float],
    filename: str = "shopfront.jpg",
) -> Dict:
    """Validate + save the shopfront photo and update the shop's verification
    status. Returns the public fields the API should relay back.
    """
    if not photo_bytes:
        raise VerificationError("Photo is empty.")
    if len(photo_bytes) > settings.SHOPFRONT_PHOTO_MAX_BYTES:
        raise VerificationError(
            f"Photo is too large — please keep it under "
            f"{settings.SHOPFRONT_PHOTO_MAX_BYTES // (1024 * 1024)} MB."
        )

    shop = await m.shops().find_one({"_id": shop_id})
    if not shop:
        raise VerificationError("Shop not found")
    shop_loc = _shop_location(shop)
    if not shop_loc:
        raise VerificationError(
            "Set your shop's location before uploading a shopfront photo."
        )

    # Cross-check #1: EXIF GPS in the JPEG itself.
    try:
        exif_gps = extract_exif_gps(photo_bytes)
    except VerificationError:
        raise
    except Exception as exc:
        logger.warning("EXIF parse failed | shop=%s | %s", shop_id, exc)
        exif_gps = None

    # Cross-check #2: browser GPS captured at photo time.
    browser_gps = None
    if browser_lat is not None and browser_lng is not None:
        browser_gps = (float(browser_lat), float(browser_lng))

    if not exif_gps and not browser_gps:
        raise VerificationError(
            "We couldn't get any GPS from the photo. Please allow location "
            "permission in your browser and retake the photo."
        )

    # Both signals, if both present, must be within the radius of the shop.
    radius = settings.SHOPFRONT_PHOTO_DISTANCE_METERS
    shop_lat, shop_lng = shop_loc
    for label, gps in (("EXIF", exif_gps), ("browser", browser_gps)):
        if gps is None:
            continue
        dist = haversine_meters(shop_lat, shop_lng, gps[0], gps[1])
        if dist > radius:
            raise VerificationError(
                f"The {label} location of the photo is {int(dist)}m from your "
                f"shop's registered location — photos must be within {radius}m. "
                "Take the photo standing in front of your shop."
            )

    # Save the photo to disk under app/static/shop_photos/.
    photo_dir: Path = settings.shopfront_photo_dir
    photo_dir.mkdir(parents=True, exist_ok=True)
    # Always overwrite the previous photo for this shop (one photo per shop).
    out_path = photo_dir / f"{shop_id}.jpg"
    # Re-encode as JPEG for size + sanitisation. Pillow's default save
    # strips EXIF metadata (including GPS) — the saved photo on disk must
    # NOT retain the GPS coordinates, since it's a publicly-served file.
    # The GPS has already been extracted and stored on the shop doc
    # (photo_browser_location + photo_exif_location) for verification;
    # the photo itself is just the visual.
    sanitised_bytes_io = io.BytesIO()
    try:
        img = Image.open(io.BytesIO(photo_bytes))
        img.convert("RGB").save(sanitised_bytes_io, "JPEG", quality=85, optimize=True)
    except Exception as exc:
        raise VerificationError(f"Could not process photo: {exc}") from exc
    sanitised_bytes = sanitised_bytes_io.getvalue()

    # Upload to ImgBB if configured, else fall back to disk (local dev only).
    if settings.IMGBB_API_KEY:
        photo_url = await _upload_to_imgbb(sanitised_bytes)
        if not photo_url:
            raise VerificationError(
                "Photo upload to ImgBB failed. Please try again in a moment."
            )
    else:
        out_path.write_bytes(sanitised_bytes)
        photo_url = f"/static/shop_photos/{shop_id}.jpg"

    now = utcnow()
    await m.shops().update_one(
        {"_id": shop_id},
        {"$set": {
            "shopfront_photo_url": photo_url,
            "photo_browser_location": {"lat": browser_gps[0], "lng": browser_gps[1]} if browser_gps else None,
            "photo_exif_location": {"lat": exif_gps[0], "lng": exif_gps[1]} if exif_gps else None,
            "photo_uploaded_at": now,
            "verification_status": "photo_pending",  # waiting for admin approval
            "updated_at": now,
        }},
    )
    logger.info("shopfront photo uploaded | shop=%s url=%s", shop_id, photo_url)
    return {
        "shopfrontPhotoUrl": photo_url,
        "photoBrowserLocation": {"lat": browser_gps[0], "lng": browser_gps[1]} if browser_gps else None,
        "photoExifLocation": {"lat": exif_gps[0], "lng": exif_gps[1]} if exif_gps else None,
        "photoUploadedAt": now.isoformat(),
        "verificationStatus": "photo_pending",
    }


async def _upload_to_imgbb(image_bytes: bytes) -> Optional[str]:
    """Upload an image to ImgBB and return the public URL.

    ImgBB API: https://api.imgbb.com/1/upload?key=API_KEY
    Body: multipart form with the image file.
    Response: { data: { url: "https://...", display_url: "https://..." }, success, status }

    Returns None on failure (caller raises VerificationError).
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.imgbb.com/1/upload",
                params={"key": settings.IMGBB_API_KEY},
                files={"image": ("shopfront.jpg", image_bytes, "image/jpeg")},
            )
            if response.status_code != 200:
                logger.error(
                    "ImgBB upload failed | status=%s body=%s",
                    response.status_code, response.text[:200],
                )
                return None
            data = response.json()
            if not data.get("success"):
                logger.error("ImgBB returned success=false | %s", data)
                return None
            url = (data.get("data") or {}).get("url")
            if not url:
                logger.error("ImgBB response missing data.url | %s", data)
                return None
            logger.info("ImgBB upload OK | url=%s", url)
            return url
    except Exception as exc:
        logger.error("ImgBB upload exception | %s | %s", exc.__class__.__name__, exc)
        return None


async def admin_approve_shop(shop_id) -> Dict:
    """Admin (you, for the hackathon) approves a pending shop — flips
    ``is_verified=True`` so the shop becomes visible to customers via the
    find_candidates geoNear gate."""
    shop = await m.shops().find_one({"_id": shop_id})
    if not shop:
        raise VerificationError("Shop not found")
    if not shop.get("shopfront_photo_url"):
        raise VerificationError("Shop has not uploaded a shopfront photo yet.")
    now = utcnow()
    await m.shops().update_one(
        {"_id": shop_id},
        {"$set": {
            "is_verified": True,
            "verification_status": "verified",
            "photo_approved_at": now,
            "updated_at": now,
        }},
    )
    logger.info("shop approved | shop=%s", shop_id)
    return {"shopId": str(shop_id), "isVerified": True, "approvedAt": now.isoformat()}


async def admin_reject_shop(shop_id, reason: str = "") -> Dict:
    """Admin rejects — shop stays invisible, shopkeeper can re-upload."""
    now = utcnow()
    await m.shops().update_one(
        {"_id": shop_id},
        {"$set": {
            "is_verified": False,
            "verification_status": "rejected",
            "photo_approved_at": None,
            "rejection_reason": reason[:200],
            "updated_at": now,
        }},
    )
    return {"shopId": str(shop_id), "isVerified": False, "reason": reason}


async def list_pending_shops() -> list:
    """List all shops awaiting admin approval."""
    cursor = m.shops().find({
        "verification_status": "photo_pending",
        "is_active": True,
    }).sort("photo_uploaded_at", -1).limit(50)
    out = []
    async for shop in cursor:
        out.append({
            "id": str(shop["_id"]),
            "shopName": shop.get("shop_name"),
            "category": shop.get("category"),
            "phone": shop.get("phone"),
            "address": shop.get("address"),
            "shopfrontPhotoUrl": shop.get("shopfront_photo_url"),
            "photoUploadedAt": shop["photo_uploaded_at"].isoformat() if shop.get("photo_uploaded_at") else None,
            "photoBrowserLocation": shop.get("photo_browser_location"),
            "photoExifLocation": shop.get("photo_exif_location"),
            "verificationStatus": shop.get("verification_status"),
        })
    return out
