"""Demand report formatting (aggregation shape is asserted without a live DB)."""
from app.services.demand_engine import format_demand_report


def test_empty_report_is_friendly():
    text = format_demand_report([])
    assert "LOCAL DEMAND" in text
    assert "nahi" in text


def test_report_lists_products_and_counts():
    rows = [
        {"product": "Teflon Tape", "requests": 18, "unavailable": 11},
        {"product": "1-inch PVC Pipe", "requests": 13, "unavailable": 7},
        {"product": "Electrical Tape", "requests": 11, "unavailable": 4},
    ]
    text = format_demand_report(rows)
    assert "Teflon Tape" in text
    assert "18 requests" in text
    assert "11 unavailable" in text
    assert "Electrical Tape" in text


def test_custom_title_is_used():
    assert "PLATFORM DEMAND" in format_demand_report([], title="PLATFORM DEMAND")
