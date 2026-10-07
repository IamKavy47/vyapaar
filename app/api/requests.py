"""Request inspection + the end-to-end pipeline test endpoint."""
from fastapi import APIRouter, HTTPException

from app.ai import intent_engine
from app.ai.intent_engine import AIUnavailableError
from app.database import mongo as m
from app.models.customer import build_customer_document
from app.models.user import UserRole, build_user_document
from app.schemas.match import MatchResult
from app.schemas.request import RequestPublic, TestMatchPayload
from app.services import merchant_matching, search_service
from app.utils.logging import bind_request_id, get_logger, new_request_id
from app.utils.security import hash_password

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["requests"])


@router.get("/requests/{request_id}", response_model=RequestPublic)
async def get_request(request_id: str):
    doc = await search_service.get_request(request_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Request not found")
    return RequestPublic(**{
        "request_id": doc["request_id"], "product": doc.get("product"),
        "category": doc.get("category"), "sub_category": doc.get("sub_category"),
        "quantity": doc.get("quantity", 1), "unit": doc.get("unit", "piece"),
        "confidence": doc.get("confidence", 0.0), "status": doc.get("status"),
        "input_type": doc.get("input_type", "text"),
        "matched_count": doc.get("matched_count", 0), "created_at": doc.get("created_at"),
    })


@router.get("/requests/{request_id}/offers")
async def get_offers(request_id: str):
    doc = await search_service.get_request(request_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"request_id": request_id, "offers": await merchant_matching.accepted_offers(request_id)}


async def _ensure_api_customer(name: str):
    """A throwaway customer used by the test endpoint so the pipeline is realistic."""
    email = "api-tester@vyapaar-mitra.local"
    user = await m.users().find_one({"email": email})
    if user:
        return user
    doc = build_user_document(
        full_name=name, email=email, phone="0000000000",
        password_hash=hash_password("api-tester-not-a-login"),
        role=UserRole.CUSTOMER.value,
    )
    result = await m.users().insert_one(doc)
    doc["_id"] = result.inserted_id
    await m.customers().insert_one(build_customer_document(user_id=doc["_id"]))
    return doc


@router.post("/test/match", response_model=MatchResult)
async def test_match(payload: TestMatchPayload):
    """Run intent extraction + zero-inventory matching without Telegram.

    notify=false by default so demos don't spam real merchants.
    """
    bind_request_id(new_request_id("API"))
    try:
        intent = await intent_engine.extract_intent(payload.text, input_type="text")
    except AIUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"AI providers unavailable: {exc}")

    if not intent.product:
        raise HTTPException(status_code=422, detail="Could not identify a product from that text.")

    user = await _ensure_api_customer(payload.customer_name)
    request = await search_service.create_request(
        intent=intent, customer_id=user["_id"], telegram_user_id=None,
        latitude=payload.latitude, longitude=payload.longitude,
        input_type="text", raw_text=payload.text,
    )
    return await search_service.run_matching(request, notify=payload.notify)
