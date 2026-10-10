"""Order service — customer checkout orders + shopkeeper order management.

An order is created when the customer pays (online via Razorpay) or when
the customer picks "pay at shop" (cash). The shopkeeper sees all orders
in their Orders tab and can mark cash orders as paid.
"""
from typing import Dict, List, Optional

from bson import ObjectId

from app.database import mongo as m
from app.models.order import OrderStatus, PaymentMethod, build_order_document
from app.models.user import utcnow
from app.utils.logging import get_logger

logger = get_logger(__name__)


class OrderError(Exception):
    """User-facing order failure — message is safe to display."""


async def create_order_from_selection(
    *, request_id: str, match_id, customer_id, shop_id, merchant_id,
    product: str, price: Optional[float], quantity: int = 1, unit: str = "piece",
    customer_name: str = "", shop_name: str = "",
    payment_method: str = PaymentMethod.CASH.value,
    is_service: bool = False,
    razorpay_order_id: Optional[str] = None,
) -> Dict:
    """Create an order when the customer picks a shop (select_offer).

    If payment_method is "online", the order starts as PAID (Razorpay handles
    the actual payment). If "cash", the order starts as PENDING — the shopkeeper
    marks it paid when the customer pays in person.
    """
    doc = build_order_document(
        request_id=request_id, match_id=match_id,
        customer_id=customer_id, shop_id=shop_id, merchant_id=merchant_id,
        product=product, price=price, quantity=quantity, unit=unit,
        customer_name=customer_name, shop_name=shop_name,
        payment_method=payment_method, is_service=is_service,
    )
    if razorpay_order_id:
        doc["razorpay_order_id"] = razorpay_order_id
    # Idempotent: if an order already exists for this request, return it.
    existing = await m.orders().find_one({"request_id": request_id})
    if existing:
        return existing
    await m.orders().insert_one(doc)
    logger.info("order created | request=%s shop=%s method=%s product=%s",
                request_id, shop_name, payment_method, product)
    return doc


async def link_razorpay_payment(
    *, request_id: str, razorpay_order_id: str, razorpay_payment_id: str,
) -> bool:
    """When a Razorpay payment is verified, update the corresponding order
    to status=paid + link the payment IDs."""
    result = await m.orders().update_one(
        {"request_id": request_id},
        {"$set": {
            "status": OrderStatus.PAID.value,
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "paid_at": utcnow(),
            "updated_at": utcnow(),
        }},
    )
    return result.modified_count > 0


async def mark_cash_paid(*, order_id, merchant_id) -> Dict:
    """Shopkeeper marks a cash order as paid (customer paid in person).

    Only the shop that owns the order can mark it. Only PENDING orders
    can be marked (PAID is idempotent — returns the existing doc).
    """
    result = await m.orders().find_one_and_update(
        {
            "_id": ObjectId(str(order_id)),
            "merchant_id": merchant_id,
            "status": OrderStatus.PENDING.value,
        },
        {"$set": {
            "status": OrderStatus.PAID.value,
            "paid_at": utcnow(),
            "marked_paid_by": merchant_id,
            "updated_at": utcnow(),
        }},
        return_document=True,
    )
    if not result:
        # Check if it's already paid
        existing = await m.orders().find_one({"_id": ObjectId(str(order_id))})
        if existing and existing.get("status") == OrderStatus.PAID.value:
            return existing  # idempotent — already paid
        if existing and str(existing.get("merchant_id")) != str(merchant_id):
            raise OrderError("Yeh order aapki shop ka nahi hai.")
        raise OrderError("Order nahi mila ya pehle hi paid hai.")
    return result


async def list_orders_for_shop(shop_id, limit: int = 50) -> List[Dict]:
    """List all orders for a shop, most recent first."""
    cursor = m.orders().find(
        {"shop_id": str(shop_id)}
    ).sort("created_at", -1).limit(limit)
    return [doc async for doc in cursor]


async def get_order_for_request(request_id: str) -> Optional[Dict]:
    """Get the order for a specific customer request (if any)."""
    return await m.orders().find_one({"request_id": request_id})


def order_public(doc: dict) -> dict:
    """Serialize an order doc for the API response."""
    return {
        "id": str(doc.get("_id")),
        "requestId": doc.get("request_id"),
        "customerId": str(doc.get("customer_id")),
        "shopId": str(doc.get("shop_id")),
        "product": doc.get("product"),
        "price": doc.get("price"),
        "quantity": doc.get("quantity", 1),
        "unit": doc.get("unit", "piece"),
        "customerName": doc.get("customer_name"),
        "shopName": doc.get("shop_name"),
        "paymentMethod": doc.get("payment_method"),  # online | cash
        "isService": doc.get("is_service", False),
        "status": doc.get("status"),  # pending | paid | cancelled
        "razorpayPaymentId": doc.get("razorpay_payment_id"),
        "paidAt": doc.get("paid_at").isoformat() if doc.get("paid_at") else None,
        "createdAt": doc.get("created_at").isoformat() if doc.get("created_at") else None,
    }
