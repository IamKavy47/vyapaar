#!/usr/bin/env python3
"""End-to-end pipeline check without Telegram.

    python -m scripts.test_pipeline "Mere sink ke niche pipe leak ho raha hai, safed tape chahiye"

Runs: text -> intent -> zero-inventory matching -> merchant YES + price ->
customer result, then a merchant NO -> demand event -> demand report.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bson import ObjectId  # noqa: E402

from app.ai import intent_engine  # noqa: E402
from app.ai.intent_engine import AIUnavailableError  # noqa: E402
from app.database import mongo as m  # noqa: E402
from app.database.indexes import create_indexes  # noqa: E402
from app.database.mongo import close_mongo_connection, connect_to_mongo  # noqa: E402
from app.models.customer import build_customer_document  # noqa: E402
from app.models.user import UserRole, build_user_document  # noqa: E402
from app.services import demand_engine, search_service  # noqa: E402
from app.utils.geo import humanize_distance  # noqa: E402
from app.utils.logging import setup_logging  # noqa: E402
from app.utils.security import hash_password  # noqa: E402

LAT = float(os.getenv("SEED_CENTER_LAT", "24.0734"))
LNG = float(os.getenv("SEED_CENTER_LNG", "75.0686"))
DEFAULT_QUERY = ("Mere sink ke niche pipe leak ho raha hai, "
                 "usko rokne wala safed tape chahiye.")


def rule(title: str) -> None:
    print(f"\n{'=' * 62}\n{title}\n{'=' * 62}")


async def pipeline_customer():
    email = "pipeline.tester@vyapaar-mitra.local"
    user = await m.users().find_one({"email": email})
    if user:
        return user
    doc = build_user_document(
        full_name="Pipeline Tester", email=email, phone="9999900099",
        password_hash=hash_password("PipelineTester123"), role=UserRole.CUSTOMER.value,
    )
    result = await m.users().insert_one(doc)
    doc["_id"] = result.inserted_id
    await m.customers().insert_one(
        build_customer_document(user_id=doc["_id"], latitude=LAT, longitude=LNG)
    )
    return doc


async def main() -> None:
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))
    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUERY

    if not await connect_to_mongo():
        print("❌ MongoDB not reachable. Start MongoDB and check MONGODB_URI.")
        return
    await create_indexes()

    shop_count = await m.shops().count_documents({"is_active": True})
    if shop_count == 0:
        print("⚠️  No shops found. Run: python -m scripts.seed_demo_data --reset")
        await close_mongo_connection()
        return

    rule("1. CUSTOMER INPUT")
    print(f'🗣️  "{query}"')
    print("\n🔍 Samajh raha hoon... Nearby shops locate kar raha hoon.")

    rule("2. INTENT EXTRACTION (Gemini -> Groq -> GPT-OSS)")
    try:
        intent = await intent_engine.extract_intent(query, input_type="text")
    except AIUnavailableError as exc:
        print(f"❌ No AI provider available: {exc}")
        print("   Set GEMINI_API_KEY or GROQ_API_KEY in .env and try again.")
        await close_mongo_connection()
        return
    print(f"   product     : {intent.product}")
    print(f"   category    : {intent.category} / {intent.sub_category}")
    print(f"   quantity    : {intent.quantity} {intent.unit}")
    print(f"   confidence  : {intent.confidence:.2f} ({intent_engine.confidence_band(intent.confidence)})")
    print(f"   provider    : {intent.provider}")
    print(f"   alternatives: {intent.alternative_products}")

    user = await pipeline_customer()
    request = await search_service.create_request(
        intent=intent, customer_id=user["_id"], telegram_user_id=None,
        latitude=LAT, longitude=LNG, input_type="text", raw_text=query,
    )

    rule("3. ZERO-INVENTORY MERCHANT MATCHING")
    result = await search_service.run_matching(request, notify=False)
    if not result.candidates:
        print("😔 No merchants matched. Seed demo data first.")
        await close_mongo_connection()
        return
    print(f"Radius used: {result.radius_used_meters}m\n")
    for candidate in result.candidates:
        inventory = "has stock record" if candidate.has_inventory_hint else "ZERO INVENTORY ⭐"
        print(f"🏪 {candidate.shop_name:26s} {humanize_distance(candidate.distance_meters):>8s}  "
              f"score={candidate.match_score:.3f}  [{inventory}]")
        print(f"   breakdown: {candidate.score_breakdown}")

    rule("4. MERCHANT SAYS YES + PRICE")
    top = result.candidates[0]
    match = await m.merchant_matches().find_one({
        "request_id": request["request_id"], "merchant_id": ObjectId(top.merchant_id)
    })
    ok, payload = await search_service.handle_merchant_response(
        match["_id"], accepted=True, price=30.0
    )
    print(f"✅ {top.shop_name} confirmed availability at ₹30")
    print("\n🎉 Customer receives:")
    print(f"   🏪 {top.shop_name}")
    print(f"   📍 {humanize_distance(top.distance_meters)} away")
    print(f"   🔧 {request['product']}")
    print("   💰 ₹30")
    print("   (Availability confirmed — not a completed sale.)")

    rule("5. ANOTHER MERCHANT SAYS NO -> DEMAND EVENT")
    if len(result.candidates) > 1:
        second = result.candidates[1]
        match2 = await m.merchant_matches().find_one({
            "request_id": request["request_id"],
            "merchant_id": ObjectId(second.merchant_id),
        })
        await search_service.handle_merchant_response(match2["_id"], accepted=False)
        print(f"❌ {second.shop_name} does not have it -> DemandEvent recorded")
        print(f"   Cooldown set for {second.shop_name} on '{request['product']}'")
    else:
        print("(only one candidate — skipping)")

    rule("6. DEMAND INTELLIGENCE")
    rows = await demand_engine.top_products(limit=10)
    print(demand_engine.format_demand_report(rows))

    rule("SUMMARY")
    print("Traditional commerce asks:  What products has this shop uploaded?")
    print("Vyapaar-Mitra asks:         Who nearby can satisfy this customer's need?")
    await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
