#!/usr/bin/env python3
"""Seed demo merchants for the live demo.

Run:  python -m scripts.seed_demo_data [--reset]

Several shops are seeded with ZERO inventory on purpose — that is the whole point
of the demo. Sharma Hardware has no products at all and must still be matched.
"""
import argparse
import asyncio
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import mongo as m  # noqa: E402
from app.database.indexes import create_indexes  # noqa: E402
from app.database.mongo import close_mongo_connection, connect_to_mongo  # noqa: E402
from app.models.customer import build_customer_document  # noqa: E402
from app.models.inventory import build_inventory_document  # noqa: E402
from app.models.shop import build_shop_document  # noqa: E402
from app.models.user import UserRole, build_user_document  # noqa: E402
from app.utils.logging import setup_logging  # noqa: E402
from app.utils.security import hash_password  # noqa: E402

CENTER_LAT = float(os.getenv("SEED_CENTER_LAT", "24.0734"))   # Mandsaur, MP
CENTER_LNG = float(os.getenv("SEED_CENTER_LNG", "75.0686"))
DEMO_PASSWORD = os.getenv("SEED_PASSWORD", "VyapaarDemo123")


def offset(lat: float, lng: float, north_m: float, east_m: float):
    """Shift a coordinate by a metre offset (good enough at city scale)."""
    dlat = north_m / 111_320.0
    dlng = east_m / (111_320.0 * math.cos(math.radians(lat)))
    return lat + dlat, lng + dlng


# (name, category, capabilities, north_m, east_m, inventory)
SHOPS = [
    ("Sharma Hardware", "hardware",
     ["plumbing", "pipes", "fittings", "tools", "sealants", "adhesives"],
     180, 90, []),  # ← ZERO INVENTORY on purpose (capable but unlisted)
    ("Patel Plumbing", "plumbing",
     ["pipes", "fittings", "sealants", "taps", "sanitary"],
     -260, 150, []),
    # Gupta Electricals now stocks Teflon Tape — the demo's "shop with
    # inventory listed" that confirms at the listed price (₹25).
    ("Gupta Electricals", "electrical",
     ["wires", "switches", "bulbs", "tape", "fans", "adapters", "plumbing"],
     320, -210, [("Electrical Tape", 40, "roll", "Anchor", 25.0),
                 ("Teflon Tape", 60, "piece", None, 25.0)]),
    ("Ramesh General Store", "general_store",
     ["household", "groceries", "stationery", "cleaning", "adhesives"],
     -140, -320, [("Fevicol", 12, "bottle", "Pidilite", 45.0)]),
    ("Mobile Point", "mobile_electronics",
     ["mobiles", "chargers", "cables", "accessories", "repair"],
     700, 420, []),
    ("Stationery Corner", "stationery",
     ["paper", "pens", "notebooks", "printing", "adhesives"],
     -620, 380, [("A4 Paper Ream", 30, "packet", "JK", 320.0)]),
    ("Maa Medical", "medical",
     ["medicines", "otc", "first_aid", "surgical"],
     450, 620, []),
    ("Fashion Point", "clothing",
     ["apparel", "fabric", "tailoring"],
     -900, -640, [("Cotton Shirt", 25, "piece", None, 499.0)]),
    ("Sweet Bakery House", "bakery_food",
     ["bakery", "snacks", "sweets", "beverages"],
     1200, -800, []),
    # Raj Plumbing: 1.2km north of centre, capable but does NOT stock
    # Teflon Tape — its NO is the demand-intelligence signal that drives
    # the demo's "stock opportunity" recommendation.
    ("Raj Plumbing", "plumbing",
     ["pipes", "fittings", "taps", "sanitary", "water_purifiers"],
     1200, 0, []),
    ("Verma Hardware & Paints", "hardware",
     ["paints", "tools", "fasteners", "plumbing", "sealants"],
     -1500, 1100, [("Teflon Tape", 60, "piece", None, 28.0)]),
]


async def reset() -> None:
    for name in ("users", "customers", "shops", "inventory_items", "product_requests",
                 "merchant_matches", "demand_events", "khata_entries", "auth_tokens",
                 "sessions", "notifications", "merchant_cooldowns"):
        await m.collection(name).delete_many({})
    print("🧹 Existing demo data cleared.")


async def seed_customer() -> None:
    email = "demo.customer@vyapaar-mitra.local"
    if await m.users().find_one({"email": email}):
        print("• Demo customer already exists")
        return
    user = build_user_document(
        full_name="Demo Customer", email=email, phone="9999900001",
        password_hash=hash_password(DEMO_PASSWORD), role=UserRole.CUSTOMER.value,
        is_verified=True,
    )
    result = await m.users().insert_one(user)
    await m.customers().insert_one(build_customer_document(
        user_id=result.inserted_id, latitude=CENTER_LAT, longitude=CENTER_LNG
    ))
    print(f"👤 Demo customer seeded ({email} / {DEMO_PASSWORD})")


async def seed_shops() -> None:
    created = 0
    for index, (name, category, capabilities, north, east, inventory) in enumerate(SHOPS, start=1):
        email = f"shop{index}@vyapaar-mitra.local"
        if await m.users().find_one({"email": email}):
            continue
        user = build_user_document(
            full_name=name, email=email, phone=f"99999{10000 + index}",
            password_hash=hash_password(DEMO_PASSWORD), role=UserRole.SHOPKEEPER.value,
            is_verified=True,
        )
        user_result = await m.users().insert_one(user)
        latitude, longitude = offset(CENTER_LAT, CENTER_LNG, north, east)
        shop = build_shop_document(
            user_id=user_result.inserted_id, shop_name=name, phone=f"99999{10000 + index}",
            category=category, capabilities=capabilities, latitude=latitude, longitude=longitude,
            address=f"Demo Market, Shop {index}",
            description=f"{name} — demo merchant seeded for the hackathon build.",
            is_verified=True,
        )
        shop_result = await m.shops().insert_one(shop)

        for product, quantity, unit, brand, price in inventory:
            await m.inventory_items().insert_one(build_inventory_document(
                shop_id=shop_result.inserted_id, product=product, quantity=quantity,
                unit=unit, brand=brand, price=price, source="seed",
            ))
        created += 1
        marker = "ZERO INVENTORY ⭐" if not inventory else f"{len(inventory)} item(s)"
        print(f"🏪 {name:26s} {category:18s} {marker}")

    print(f"\n✅ {created} shop(s) seeded around ({CENTER_LAT}, {CENTER_LNG})")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Vyapaar-Mitra demo data")
    parser.add_argument("--reset", action="store_true", help="delete existing data first")
    args = parser.parse_args()

    setup_logging("WARNING")
    if not await connect_to_mongo():
        print("❌ Could not connect to MongoDB. Check MONGODB_URI in your .env")
        return
    await create_indexes()

    if args.reset:
        await reset()

    await seed_shops()
    await seed_customer()

    print("\n📌 Note: shopkeeper accounts are NOT linked to Telegram yet.")
    print("   For the live demo, open the bot, choose 🏪 Shopkeeper, press 🔐 Login / Register")
    print(f"   and log in with e.g. shop1@vyapaar-mitra.local / {DEMO_PASSWORD}")
    print("   Then share the shop's location from Telegram so it can receive requests.")
    await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
