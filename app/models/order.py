"""Order model — one per customer checkout (after select_offer + optional payment).

An order is created when:
  - A customer picks a shop (select_offer → COMPLETED) AND
  - The customer either pays online (Razorpay) OR picks "pay at shop" (cash/UPI in person)

The shopkeeper sees orders in their "Orders" tab and can:
  - View order history (product, price, customer, payment method, date)
  - Mark a cash order as "paid" when the customer pays in person
  - See which orders were paid online vs cash

Payment methods:
  - "online" — Razorpay payment verified (auto-paid)
  - "cash" — customer chose to pay at the shop (shopkeeper marks it paid)

Order status:
  - "pending" — order created, not yet paid (cash orders start here)
  - "paid" — payment confirmed (online: auto via Razorpay verify; cash: shopkeeper taps "Mark paid")
  - "cancelled" — shopkeeper or customer cancelled (future scope)
"""
from enum import Enum
from typing import Dict, Optional

from app.models.user import utcnow


class OrderStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"


class PaymentMethod(str, Enum):
    ONLINE = "online"   # Razorpay
    CASH = "cash"       # Pay at shop (cash/UPI in person)


def build_order_document(
    *, request_id: str, match_id, customer_id, shop_id, merchant_id,
    product: str, price: Optional[float], quantity: int = 1, unit: str = "piece",
    customer_name: str = "", shop_name: str = "",
    payment_method: str = PaymentMethod.CASH.value,
    is_service: bool = False,
) -> Dict:
    now = utcnow()
    return {
        "request_id": request_id,
        "match_id": str(match_id),
        "customer_id": customer_id,
        "shop_id": str(shop_id),
        "merchant_id": merchant_id,
        "product": product,
        "price": price,
        "quantity": quantity,
        "unit": unit,
        "customer_name": customer_name,
        "shop_name": shop_name,
        "payment_method": payment_method,  # online | cash
        "is_service": is_service,
        "status": OrderStatus.PAID.value if payment_method == PaymentMethod.ONLINE.value
                  else OrderStatus.PENDING.value,
        "razorpay_order_id": None,
        "razorpay_payment_id": None,
        "paid_at": now if payment_method == PaymentMethod.ONLINE.value else None,
        "marked_paid_by": None,  # who marked a cash order as paid (merchant_id)
        "created_at": now,
        "updated_at": now,
    }
