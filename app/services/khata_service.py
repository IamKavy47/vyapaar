"""Digital Khata: credit ledger with running balances per customer."""
from typing import Dict, List, Optional

from bson import ObjectId

from app.database import mongo as m
from app.models.khata import EntryType, build_khata_entry, customer_key
from app.schemas.khata import KhataBalance, KhataSummary
from app.utils.logging import get_logger

logger = get_logger(__name__)


class KhataError(ValueError):
    pass


async def add_entry(*, merchant_id, customer_name: str, amount: float, entry_type: str,
                    description: str = "", source: str = "text",
                    customer_identifier: Optional[str] = None) -> Dict:
    if not customer_name or not customer_name.strip():
        raise KhataError("Customer ka naam nahi mila.")
    if amount <= 0:
        raise KhataError("Amount samajh nahi aaya.")
    try:
        doc = build_khata_entry(
            merchant_id=ObjectId(str(merchant_id)), customer_name=customer_name, amount=amount,
            entry_type=entry_type, description=description, source=source,
            customer_identifier=customer_identifier,
        )
    except ValueError as exc:
        raise KhataError(str(exc)) from exc
    await m.khata_entries().insert_one(doc)
    logger.info("khata entry stored | %s %s ₹%s", doc["customer_name"], entry_type, amount)
    return doc


async def balance_for(merchant_id, customer_name: str) -> KhataBalance:
    pipeline = [
        {"$match": {"merchant_id": ObjectId(str(merchant_id)),
                    "customer_key": customer_key(customer_name)}},
        {"$group": {
            "_id": "$customer_key",
            "customer_name": {"$last": "$customer_name"},
            "total_credit": {"$sum": {"$cond": [
                {"$eq": ["$entry_type", EntryType.CREDIT.value]}, "$amount", 0]}},
            "total_paid": {"$sum": {"$cond": [
                {"$eq": ["$entry_type", EntryType.PAYMENT.value]}, "$amount", 0]}},
            "entries": {"$sum": 1},
            "last_entry_at": {"$max": "$created_at"},
        }},
    ]
    async for row in m.khata_entries().aggregate(pipeline):
        return KhataBalance(
            customer_name=row.get("customer_name") or customer_name,
            outstanding=round(row["total_credit"] - row["total_paid"], 2),
            total_credit=round(row["total_credit"], 2),
            total_paid=round(row["total_paid"], 2),
            entries=row["entries"], last_entry_at=row.get("last_entry_at"),
        )
    return KhataBalance(customer_name=customer_name.title(), outstanding=0.0)


async def summary(merchant_id) -> KhataSummary:
    pipeline = [
        {"$match": {"merchant_id": ObjectId(str(merchant_id))}},
        {"$sort": {"created_at": 1}},
        {"$group": {
            "_id": "$customer_key",
            "customer_name": {"$last": "$customer_name"},
            "total_credit": {"$sum": {"$cond": [
                {"$eq": ["$entry_type", EntryType.CREDIT.value]}, "$amount", 0]}},
            "total_paid": {"$sum": {"$cond": [
                {"$eq": ["$entry_type", EntryType.PAYMENT.value]}, "$amount", 0]}},
            "entries": {"$sum": 1},
            "last_entry_at": {"$max": "$created_at"},
        }},
        {"$sort": {"last_entry_at": -1}},
    ]
    balances: List[KhataBalance] = []
    total = 0.0
    async for row in m.khata_entries().aggregate(pipeline):
        outstanding = round(row["total_credit"] - row["total_paid"], 2)
        total += outstanding
        balances.append(KhataBalance(
            customer_name=row.get("customer_name") or row["_id"],
            outstanding=outstanding,
            total_credit=round(row["total_credit"], 2),
            total_paid=round(row["total_paid"], 2),
            entries=row["entries"], last_entry_at=row.get("last_entry_at"),
        ))
    balances.sort(key=lambda b: -b.outstanding)
    return KhataSummary(merchant_id=str(merchant_id), total_outstanding=round(total, 2),
                        balances=balances)


async def recent_entries(merchant_id, limit: int = 10) -> List[Dict]:
    cursor = m.khata_entries().find(
        {"merchant_id": ObjectId(str(merchant_id))}
    ).sort("created_at", -1).limit(limit)
    return [doc async for doc in cursor]


def format_summary(result: KhataSummary) -> str:
    if not result.balances:
        return ("📒 KHATA\n\nAbhi koi entry nahi hai.\n\n"
                "Aise likhiye ya boliye:\n\"Ramesh ne 500 rupaye udhaar liye\"")
    lines = ["📒 KHATA", ""]
    for balance in result.balances[:20]:
        if balance.outstanding > 0:
            lines.append(f"👤 {balance.customer_name}\n   Outstanding: ₹{balance.outstanding:g}")
        elif balance.outstanding < 0:
            lines.append(f"👤 {balance.customer_name}\n   Advance: ₹{abs(balance.outstanding):g}")
        else:
            lines.append(f"👤 {balance.customer_name}\n   Settled ✅")
    lines += ["", f"💰 Total outstanding: ₹{result.total_outstanding:g}"]
    return "\n".join(lines)
