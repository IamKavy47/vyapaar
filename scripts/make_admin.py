#!/usr/bin/env python3
"""Promote an existing user to admin role (real-mode setup).

Use this when you're running the application in REAL mode (no demo seed
data, real friends as merchants + customers). You:

  1. Start the backend + frontend.
  2. Register YOURSELF as a regular customer via the web app (with real
     Twilio OTP).
  3. Run this script with your email:
       python -m scripts.make_admin you@example.com
  4. Log back in — you're now admin, and the React app redirects you to
     /admin/shops/pending where you can approve your friends' shopfront
     photos.

If the user doesn't exist yet, the script will refuse — register first.

This script is idempotent: re-running it on an already-admin user is a
no-op.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import mongo as m  # noqa: E402
from app.database.mongo import close_mongo_connection, connect_to_mongo  # noqa: E402
from app.models.user import UserRole, utcnow  # noqa: E402
from app.utils.logging import setup_logging  # noqa: E402


async def promote(email: str) -> int:
    user = await m.users().find_one({"email": email.strip().lower()})
    if not user:
        print(f"❌ No user found with email '{email}'.")
        print("   Register via the web app first (with real OTP), then re-run this script.")
        return 1
    if user.get("role") == UserRole.ADMIN.value:
        print(f"✅ '{email}' is already an admin. No change.")
        return 0
    await m.users().update_one(
        {"_id": user["_id"]},
        {"$set": {
            "role": UserRole.ADMIN.value,
            "is_verified": True,
            "phone_verified": True,
            "phone_verified_at": user.get("phone_verified_at") or utcnow(),
            "updated_at": utcnow(),
        }},
    )
    print(f"✅ Promoted '{email}' ({user.get('full_name')}) to ADMIN.")
    print("   Log out and back in via the web app — you'll be redirected to /admin/shops/pending")
    print("   where you can approve your friends' shopfront photos.")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description="Promote a user to admin role (real-mode setup)")
    parser.add_argument("email", help="The email of the user to promote (must already exist)")
    args = parser.parse_args()

    setup_logging("WARNING")
    if not await connect_to_mongo():
        print("❌ Could not connect to MongoDB. Check MONGODB_URI in your .env")
        return 2
    try:
        return await promote(args.email)
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
