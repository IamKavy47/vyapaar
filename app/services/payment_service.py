"""Razorpay payment service — in-app payments for products and services.

Flow:
  1. Customer picks a shop (select_offer succeeds → request COMPLETED).
  2. Customer taps "Pay" on the Deal pakki! panel.
  3. Frontend calls POST /api/v1/payments/create-order → returns Razorpay order_id.
  4. Frontend opens Razorpay checkout (Razorpay JS SDK) with the order_id.
  5. Customer pays (UPI / card / netbanking).
  6. Razorpay redirects back to the app with the payment_id + signature.
  7. Frontend calls POST /api/v1/payments/verify → server verifies the signature.
  8. On success: payment record linked to request + match for audit trail.
  9. Shopkeeper sees "Payment received" on their Telegram/web inbox.
  10. Razorpay webhook (POST /api/v1/payments/webhook) is a backup verification.

The payment is for the PRODUCT PRICE (merchant-confirmed) + optional SERVICE CHARGE
(for service professionals like plumbers). The platform does NOT take a commission
in the hackathon — the full amount goes to the shopkeeper (via Razorpay transfer
or manual settlement). Commission logic can be added in Phase 2.
"""
import hmac
import hashlib
from typing import Dict, Optional

from app.config.settings import settings
from app.database import mongo as m
from app.models.user import utcnow
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PaymentError(Exception):
    """User-facing payment failure — message is safe to display."""


def _get_razorpay_client():
    """Create a Razorpay client. Raises if not configured."""
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise PaymentError("Razorpay is not configured. Contact support.")
    import razorpay
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


async def create_order(
    *, request_id: str, match_id: str, amount_paise: int,
    customer_id, shop_id, product: str, customer_name: str = "",
    shop_name: str = "", is_service: bool = False,
) -> Dict:
    """Create a Razorpay order for a customer checkout.

    amount_paise: the amount in paise (₹1 = 100 paise). Must be ≥ 100 (₹1 min).
    is_service: True if this is a service payment (plumber, electrician, etc.)
                vs a product payment. Stored for analytics — no difference in
                the Razorpay flow.

    Returns: { order_id, amount, currency, key_id } for the frontend to open
    the Razorpay checkout modal.
    """
    if amount_paise < 100:
        raise PaymentError("Minimum payment amount is ₹1 (100 paise).")

    client = _get_razorpay_client()
    notes = {
        "request_id": request_id,
        "match_id": str(match_id),
        "product": product[:50],
        "customer_id": str(customer_id),
        "shop_id": str(shop_id),
        "is_service": str(is_service),
    }
    try:
        # Razorpay's client.order.create() is synchronous — run in a thread.
        import asyncio
        order = await asyncio.to_thread(
            client.order.create,
            {
                "amount": amount_paise,
                "currency": settings.RAZORPAY_CURRENCY,
                "notes": notes,
                "receipt": f"vyapaar-{request_id[:20]}",
            },
        )
    except Exception as exc:
        logger.error("Razorpay order creation failed | request=%s | %s", request_id, exc)
        raise PaymentError("Could not create payment order. Please try again.") from exc

    # Persist the order record.
    doc = {
        "razorpay_order_id": order["id"],
        "request_id": request_id,
        "match_id": str(match_id),
        "customer_id": customer_id,
        "shop_id": shop_id,
        "product": product,
        "amount_paise": amount_paise,
        "currency": settings.RAZORPAY_CURRENCY,
        "is_service": is_service,
        "customer_name": customer_name,
        "shop_name": shop_name,
        "status": "created",  # created → paid → failed → refunded
        "razorpay_payment_id": None,
        "razorpay_signature": None,
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    await m.payments().insert_one(doc)
    logger.info("payment order created | order=%s request=%s amount=%dp", order["id"], request_id, amount_paise)

    return {
        "orderId": order["id"],
        "amount": amount_paise,
        "currency": settings.RAZORPAY_CURRENCY,
        "keyId": settings.RAZORPAY_KEY_ID,
        "productName": product,
        "shopName": shop_name,
        "isService": is_service,
    }


async def verify_payment(
    *, razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str,
) -> Dict:
    """Verify a Razorpay payment signature after checkout.

    Returns { ok: True, paymentId } on success. Raises PaymentError on failure.
    """
    # Verify the signature using HMAC-SHA256.
    key = settings.RAZORPAY_KEY_SECRET.encode("utf-8")
    msg = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
    expected = hmac.new(key, msg, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, razorpay_signature):
        logger.error("Razorpay signature verification failed | order=%s", razorpay_order_id)
        raise PaymentError("Payment verification failed. Please contact support.")

    # Update the payment record.
    result = await m.payments().update_one(
        {"razorpay_order_id": razorpay_order_id},
        {"$set": {
            "status": "paid",
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
            "paid_at": utcnow(),
            "updated_at": utcnow(),
        }},
    )
    if result.modified_count == 0:
        logger.warning("payment record not found for order=%s", razorpay_order_id)
        raise PaymentError("Payment record not found. Please contact support.")

    doc = await m.payments().find_one({"razorpay_order_id": razorpay_order_id})
    logger.info("payment verified | order=%s payment=%s request=%s",
                razorpay_order_id, razorpay_payment_id, doc.get("request_id") if doc else "?")

    return {
        "ok": True,
        "paymentId": razorpay_payment_id,
        "orderId": razorpay_order_id,
        "amountPaise": doc.get("amount_paise") if doc else None,
        "product": doc.get("product") if doc else None,
        "shopName": doc.get("shop_name") if doc else None,
    }


async def handle_webhook(self, body: bytes, signature: str) -> Dict:
    """Handle Razorpay webhook (backup verification — the client-side verify
    is the primary path, but webhooks catch edge cases like network failures
    after a successful payment).

    The webhook payload is verified using the RAZORPAY_WEBHOOK_SECRET.
    """
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        logger.warning("Razorpay webhook received but no webhook secret configured — skipping")
        return {"ok": False, "reason": "webhook secret not configured"}

    # Verify webhook signature.
    expected = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        logger.error("Razorpay webhook signature verification failed")
        return {"ok": False, "reason": "signature mismatch"}

    import json
    try:
        payload = json.loads(body)
    except Exception:
        return {"ok": False, "reason": "invalid JSON"}

    event = payload.get("event", "")
    if event == "payment.captured":
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = payment_entity.get("order_id")
        payment_id = payment_entity.get("id")
        if order_id and payment_id:
            await m.payments().update_one(
                {"razorpay_order_id": order_id},
                {"$set": {
                    "status": "paid",
                    "razorpay_payment_id": payment_id,
                    "paid_at": utcnow(),
                    "updated_at": utcnow(),
                    "webhook_verified": True,
                }},
            )
            logger.info("webhook: payment captured | order=%s payment=%s", order_id, payment_id)
            return {"ok": True}

    return {"ok": False, "reason": f"unhandled event: {event}"}


async def get_payment_for_request(request_id: str) -> Optional[Dict]:
    """Get the payment status for a request (if any)."""
    return await m.payments().find_one({"request_id": request_id})
