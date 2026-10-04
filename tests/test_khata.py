"""Khata parsing and balance arithmetic."""
from app.models.khata import EntryType, build_khata_entry, customer_key
from app.utils.parsing import parse_amount_words, parse_price


def outstanding(entries):
    """Same arithmetic the aggregation performs, expressed in Python."""
    credit = sum(e["amount"] for e in entries if e["entry_type"] == EntryType.CREDIT.value)
    paid = sum(e["amount"] for e in entries if e["entry_type"] == EntryType.PAYMENT.value)
    return round(credit - paid, 2)


def test_entry_normalizes_name():
    entry = build_khata_entry(merchant_id="m1", customer_name="  ramesh  ", amount=500,
                              entry_type="credit")
    assert entry["customer_name"] == "Ramesh"
    assert entry["customer_key"] == "ramesh"


def test_entry_rejects_unknown_type():
    try:
        build_khata_entry(merchant_id="m1", customer_name="Ramesh", amount=500,
                          entry_type="unknown")
    except ValueError as exc:
        assert str(exc) == "Invalid khata entry type"
    else:
        raise AssertionError("invalid entry type was accepted")


def test_customer_key_is_case_insensitive():
    assert customer_key("RAMESH") == customer_key("ramesh")


def test_credit_then_payment_balance():
    entries = [
        build_khata_entry(merchant_id="m1", customer_name="Ramesh", amount=500, entry_type="credit"),
        build_khata_entry(merchant_id="m1", customer_name="Ramesh", amount=200, entry_type="payment"),
    ]
    assert outstanding(entries) == 300.0


def test_full_repayment_settles():
    entries = [
        build_khata_entry(merchant_id="m1", customer_name="Suresh", amount=250, entry_type="credit"),
        build_khata_entry(merchant_id="m1", customer_name="Suresh", amount=250, entry_type="payment"),
    ]
    assert outstanding(entries) == 0.0


def test_overpayment_becomes_negative_advance():
    entries = [
        build_khata_entry(merchant_id="m1", customer_name="Geeta", amount=100, entry_type="credit"),
        build_khata_entry(merchant_id="m1", customer_name="Geeta", amount=150, entry_type="payment"),
    ]
    assert outstanding(entries) == -50.0


def test_price_parsing_variants():
    assert parse_price("₹30") == 30.0
    assert parse_price("Rs. 1,250") == 1250.0
    assert parse_price("30/-") == 30.0
    assert parse_price("no digits here") is None


def test_hindi_number_words():
    assert parse_amount_words("paanch sau rupaye") == 500.0
    assert parse_amount_words("do hazar") == 2000.0
    assert parse_amount_words("500 rupaye") == 500.0
    assert parse_amount_words("kuch bhi nahi") is None
