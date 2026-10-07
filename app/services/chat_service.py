"""In-app chat between customer and shopkeeper — anonymised, scoped per request.

Privacy model: every message is scoped to a product_request, and access is
gated by the customer_id OR the shop_id owner check. The customer's phone is
never exposed to the shopkeeper and vice versa — both sides are anonymous
inside the chat. All text is logged server-side as an admissible audit trail.
"""
from typing import Dict, List, Optional

from bson import ObjectId

from app.config.settings import settings
from app.database import mongo as m
from app.models.chat import (
    ChatStatus, MessageKind, build_chat_document, build_message_document,
)
from app.models.merchant_match import MatchStatus
from app.models.user import UserRole, utcnow
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ChatError(Exception):
    """User-facing chat failure — message is safe to display."""


async def get_or_create_chat(request_id: str, user: Dict) -> Dict:
    """Get (or lazily create) the chat for a request. Customer-side call.

    The chat is created the first time the customer opens it after picking a
    shop. We need the shop_id + merchant_id from the chosen match — if no
    match has been selected yet (request.status != COMPLETED), refuse.
    """
    from app.services import search_service

    request = await search_service.get_request(request_id)
    if not request:
        raise ChatError("Request not found")
    if str(request.get("customer_id")) != str(user["_id"]):
        raise ChatError("Not your request")

    selected_match_id = request.get("selected_match_id")
    if not selected_match_id:
        raise ChatError("Chat opens once you pick a shop")

    # Existing chat?
    existing = await m.chats().find_one({"request_id": request_id})
    if existing:
        return existing

    # Need the chosen match row to get shop_id + merchant_id.
    from app.services import merchant_matching
    match = await merchant_matching.get_match(selected_match_id)
    if not match:
        raise ChatError("Selected shop not found")

    chat_doc = build_chat_document(
        request_id=request_id,
        customer_id=request["customer_id"],
        shop_id=match["merchant_id"],
        merchant_id=match["merchant_id"],
    )
    await m.chats().insert_one(chat_doc)

    # Drop a system message so the chat is never empty.
    sys_msg = build_message_document(
        chat_id=chat_doc["_id"], request_id=request_id,
        sender_id=user["_id"], sender_role="system",
        text=f"Customer picked {request.get('product') or 'this item'}. Chat is open — say hello!",
        kind=MessageKind.SYSTEM.value,
    )
    await m.chat_messages().insert_one(sys_msg)
    chat_doc["last_message_at"] = sys_msg["created_at"]
    chat_doc["last_message_preview"] = sys_msg["text"]
    chat_doc["last_message_sender_role"] = "system"
    await m.chats().update_one(
        {"_id": chat_doc["_id"]},
        {"$set": {
            "last_message_at": sys_msg["created_at"],
            "last_message_preview": sys_msg["text"],
            "last_message_sender_role": "system",
            "updated_at": utcnow(),
        }},
    )
    return chat_doc


async def get_chat_for_merchant(request_id: str, shop: Dict) -> Optional[Dict]:
    """Shop-side: fetch the chat only if it belongs to this shop."""
    chat = await m.chats().find_one({"request_id": request_id})
    if not chat:
        return None
    if str(chat.get("shop_id")) != str(shop["_id"]):
        raise ChatError("This chat belongs to another shop")
    return chat


async def send_message(
    *, request_id: str, user: Dict, text: str, shop: Optional[Dict] = None,
) -> Dict:
    """Persist + return a chat message from either side.

    Customer-side: pass only ``user`` (the function opens / fetches the chat
    for the request owned by this customer). Shop-side: pass both ``user``
    and ``shop`` (the function verifies the shop owns the chat).
    """
    text = (text or "").strip()
    if not text:
        raise ChatError("Empty message")
    if len(text) > 1000:
        raise ChatError("Message too long (max 1000 characters)")

    if shop is not None:
        # Shop-side send.
        chat = await get_chat_for_merchant(request_id, shop)
        if not chat:
            raise ChatError("No chat found for this request")
        if chat.get("status") == ChatStatus.CLOSED.value:
            raise ChatError("This chat has been closed")
        sender_role = "shopkeeper"
        sender_id = shop["user_id"]
        # Reset the merchant's unread count for this chat (they're sending).
        other_unread_field = "customer_unread_count"
    else:
        # Customer-side send.
        chat = await get_or_create_chat(request_id, user)
        if chat.get("status") == ChatStatus.CLOSED.value:
            raise ChatError("This chat has been closed")
        sender_role = "customer"
        sender_id = user["_id"]
        other_unread_field = "merchant_unread_count"

    msg = build_message_document(
        chat_id=chat["_id"], request_id=request_id,
        sender_id=sender_id, sender_role=sender_role, text=text,
    )
    await m.chat_messages().insert_one(msg)

    preview = text if len(text) <= 80 else text[:77] + "..."
    await m.chats().update_one(
        {"_id": chat["_id"]},
        {"$set": {
            "last_message_at": msg["created_at"],
            "last_message_preview": preview,
            "last_message_sender_role": sender_role,
            "updated_at": utcnow(),
        },
         "$inc": {other_unread_field: 1}},
    )

    msg["chat_id"] = str(msg["chat_id"])
    msg["sender_id"] = str(msg["sender_id"])
    msg["_id"] = str(msg["_id"])
    return msg


async def recent_messages(
    *, request_id: str, user: Dict, shop: Optional[Dict] = None,
    since: Optional[str] = None, limit: int = 100,
) -> List[Dict]:
    """Return messages for a chat, optionally filtered to those after `since`.

    Access control: the caller must be either the customer who owns the
    request or the shop that owns the chat.
    """
    if shop is not None:
        chat = await get_chat_for_merchant(request_id, shop)
    else:
        # Validate customer-side access without creating the chat.
        from app.services import search_service
        request = await search_service.get_request(request_id)
        if not request or str(request.get("customer_id")) != str(user["_id"]):
            raise ChatError("Not your request")
        chat = await m.chats().find_one({"request_id": request_id})
    if not chat:
        return []

    # Mark the caller's side as having read (reset their unread counter).
    if shop is not None:
        await m.chats().update_one(
            {"_id": chat["_id"]}, {"$set": {"merchant_unread_count": 0}},
        )
    else:
        await m.chats().update_one(
            {"_id": chat["_id"]}, {"$set": {"customer_unread_count": 0}},
        )

    query = {"request_id": request_id}
    if since:
        # `since` is an ISO string of the last message the client has — return
        # only messages strictly after that timestamp.
        from datetime import datetime
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            query["created_at"] = {"$gt": since_dt}
        except Exception:
            pass  # ignore malformed since; return full recent history

    cursor = m.chat_messages().find(query).sort("created_at", 1).limit(limit)
    out = []
    async for doc in cursor:
        out.append({
            "id": str(doc["_id"]),
            "chatId": str(doc["chat_id"]),
            "requestId": doc["request_id"],
            "senderId": str(doc["sender_id"]),
            "senderRole": doc["sender_role"],
            "text": doc["text"],
            "kind": doc["kind"],
            "createdAt": doc["created_at"].isoformat() if doc.get("created_at") else None,
            "readAt": doc["created_at"].isoformat() if doc.get("read_at") else None,
        })
    return out


async def list_conversations_for_shop(shop_id) -> List[Dict]:
    """Shop-side inbox: list all chats for this shop, most-recent first."""
    cursor = m.chats().find({"shop_id": shop_id}).sort("updated_at", -1).limit(50)
    out = []
    async for chat in cursor:
        out.append({
            "id": str(chat["_id"]),
            "requestId": chat["request_id"],
            "customerId": str(chat["customer_id"]),
            "shopId": str(chat["shop_id"]),
            "status": chat["status"],
            "lastMessageAt": chat["last_message_at"].isoformat() if chat.get("last_message_at") else None,
            "lastMessagePreview": chat.get("last_message_preview"),
            "lastMessageSenderRole": chat.get("last_message_sender_role"),
            "unreadCount": int(chat.get("merchant_unread_count", 0)),
            "createdAt": chat["created_at"].isoformat() if chat.get("created_at") else None,
        })
    return out


async def close_chat(request_id: str) -> None:
    """Mark a chat closed — e.g. when the request expires or customer confirms."""
    await m.chats().update_one(
        {"request_id": request_id},
        {"$set": {"status": ChatStatus.CLOSED.value, "updated_at": utcnow()}},
    )
