"""In-app chat between customer and shopkeeper.

Privacy model: every conversation is scoped to a single product_request, and
both sides are anonymised — the customer's phone number is NEVER exposed to
the shopkeeper and vice versa. All text messages are logged server-side so
there is an admissible evidence trail if anything goes wrong offline.

A chat is opened the moment the customer picks a shop (status=COMPLETED),
and stays open until the request is explicitly closed (customer confirms
they bought the item, or the request expires).
"""
from enum import Enum
from typing import Dict, Optional

from app.models.user import utcnow


class ChatStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class MessageKind(str, Enum):
    TEXT = "text"
    SYSTEM = "system"   # e.g. "Customer picked your shop", auto-generated


def build_chat_document(
    *, request_id: str, customer_id, shop_id, merchant_id,
) -> Dict:
    now = utcnow()
    return {
        "request_id": request_id,
        "customer_id": customer_id,
        "shop_id": shop_id,
        "merchant_id": merchant_id,
        "status": ChatStatus.ACTIVE.value,
        "last_message_at": None,
        "last_message_preview": None,
        "last_message_sender_role": None,
        "customer_unread_count": 0,
        "merchant_unread_count": 0,
        "created_at": now,
        "updated_at": now,
    }


def build_message_document(
    *, chat_id, request_id: str, sender_id, sender_role: str,
    text: str, kind: str = MessageKind.TEXT.value,
) -> Dict:
    now = utcnow()
    return {
        "chat_id": chat_id,
        "request_id": request_id,
        "sender_id": sender_id,
        "sender_role": sender_role,  # "customer" | "shopkeeper"
        "text": text.strip()[:1000],
        "kind": kind,
        "created_at": now,
        "read_at": None,
    }
