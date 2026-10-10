"""Subscription service — single Pro tier (₹299/month for shopkeepers).

Pro unlocks 6 analytics-driven benefits on the merchant dashboard:
  1. Nearby hot products (top-10 most-requested SKUs in your pin-code)
  2. Demand heatmap (visual map of where customers are asking, ~300m buckets)
  3. Sales analytics (daily/weekly revenue trends, top sellers, slow-movers)
  4. Smart pricing suggestions (AI recommends price vs. competitor offers + demand)
  5. Slow-mover alerts ("you haven't restocked X in 14 days but demand is +30%")
  6. Festival readiness ("Diwali in 3 weeks → stock lights, dry fruits, decorations")

For the hackathon demo, /merchant/subscribe grants a 14-day free trial with
no real payment — the user just clicks "Start Trial" and the Pro features
unlock. In production this is wired to Razorpay the same way the customer
checkout orders are.
"""
from datetime import timedelta
from typing import Dict, Optional

from bson import ObjectId

from app.config.settings import settings
from app.database import mongo as m
from app.models.user import utcnow
from app.utils.logging import get_logger

logger = get_logger(__name__)


def is_pro(user_doc: Optional[Dict]) -> bool:
    """Return True if the user has an active Pro subscription.

    Pro is active iff pro_expires_at is set AND in the future. A revoked
    subscription sets pro_expires_at to None; an expired subscription leaves
    pro_expires_at in the past (still truthy), so we check both.
    """
    if not user_doc:
        return False
    exp = user_doc.get("pro_expires_at")
    if not exp:
        return False
    # Be permissive about tz-aware vs naive datetimes — Mongo returns tz-aware.
    now = utcnow()
    try:
        if exp.tzinfo is None:
            from datetime import timezone
            exp = exp.replace(tzinfo=timezone.utc)
    except AttributeError:
        return False
    return exp > now


async def grant_trial(user_id, *, days: Optional[int] = None) -> Dict:
    """Grant a 14-day free Pro trial. Idempotent for first-time users only —
    a user who has already used their trial cannot get another one.

    Returns the updated user document.
    """
    days = days if days is not None else settings.PRO_TRIAL_DURATION_DAYS
    user = await m.users().find_one({"_id": ObjectId(str(user_id))})
    if not user:
        raise ValueError("User not found")
    if user.get("pro_trial_used") and not is_pro(user):
        raise ValueError(
            "Aapne apna 14-din ka free trial pehle hi use kar liya hai. "
            "Pro continue karne ke liye ₹299/month pay karein."
        )
    now = utcnow()
    expires = now + timedelta(days=days)
    update = {
        "pro_expires_at": expires,
        "pro_trial_used": True,
        "pro_subscribed_at": user.get("pro_subscribed_at") or now,
        "updated_at": now,
    }
    await m.users().update_one({"_id": ObjectId(str(user_id))}, {"$set": update})
    user.update(update)
    logger.info("Pro trial granted | user=%s expires=%s", user_id, expires.isoformat())
    return user


async def grant_pro(user_id, *, days: int = 30) -> Dict:
    """Grant a 30-day paid Pro subscription. Used after Razorpay payment
    verification in production; can also be used by admins to manually grant
    Pro to a shopkeeper."""
    user = await m.users().find_one({"_id": ObjectId(str(user_id))})
    if not user:
        raise ValueError("User not found")
    now = utcnow()
    # If user already has active Pro, extend from current expiry; else from now.
    base = user.get("pro_expires_at") if is_pro(user) else now
    if base is None:
        base = now
    elif base.tzinfo is None:
        from datetime import timezone
        base = base.replace(tzinfo=timezone.utc)
    expires = base + timedelta(days=days)
    update = {
        "pro_expires_at": expires,
        "pro_subscribed_at": user.get("pro_subscribed_at") or now,
        "updated_at": now,
    }
    await m.users().update_one({"_id": ObjectId(str(user_id))}, {"$set": update})
    user.update(update)
    logger.info("Pro granted | user=%s expires=%s days=%d", user_id, expires.isoformat(), days)
    return user


async def revoke_pro(user_id) -> bool:
    """Revoke Pro immediately. Used by admins if a payment is reversed or
    a shopkeeper is suspended. Sets pro_expires_at to None."""
    now = utcnow()
    result = await m.users().update_one(
        {"_id": ObjectId(str(user_id))},
        {"$set": {"pro_expires_at": None, "updated_at": now}},
    )
    return result.modified_count > 0


async def get_pro_status(user_id) -> Dict:
    """Return Pro status for the /merchant/pro-status endpoint."""
    user = await m.users().find_one({"_id": ObjectId(str(user_id))})
    if not user:
        return {"isPro": False, "proExpiresAt": None, "trialUsed": False}
    return {
        "isPro": is_pro(user),
        "proExpiresAt": user.get("pro_expires_at").isoformat() if user.get("pro_expires_at") else None,
        "trialUsed": user.get("pro_trial_used", False),
        "pricePaise": settings.PRO_SUBSCRIPTION_PRICE_PAISE,
        "priceDisplay": f"₹{settings.PRO_SUBSCRIPTION_PRICE_PAISE // 100}/month",
        "trialDays": settings.PRO_TRIAL_DURATION_DAYS,
    }
