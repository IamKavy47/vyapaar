"""ProductIntent validation and confidence banding."""
from app.ai.intent_engine import clarification_options, confidence_band
from app.schemas.intent import KhataIntent, ProductIntent


def test_intent_parses_example_payload():
    intent = ProductIntent(**{
        "intent": "find_product", "product": "Teflon Tape", "category": "hardware",
        "sub_category": "plumbing", "quantity": 1, "unit": "piece", "brand": None,
        "description": "White PTFE tape used to seal pipe threads", "confidence": 0.94,
        "alternative_products": ["PTFE Thread Seal Tape"],
    })
    assert intent.product == "Teflon Tape"
    assert intent.category == "hardware"
    assert intent.confidence == 0.94
    assert intent.is_actionable


def test_confidence_is_clamped():
    assert ProductIntent(confidence=5).confidence == 1.0
    assert ProductIntent(confidence=-3).confidence == 0.0
    assert ProductIntent(confidence="garbage").confidence == 0.0


def test_unknown_category_falls_back_to_other():
    assert ProductIntent(category="spaceship parts").category == "other"


def test_category_aliases_normalize():
    assert ProductIntent(category="Mobile & Electronics").category == "mobile_electronics"
    assert ProductIntent(category="grocery").category == "kirana"


def test_quantity_is_sanitized():
    assert ProductIntent(quantity="3").quantity == 3
    assert ProductIntent(quantity=0).quantity == 1
    assert ProductIntent(quantity="abc").quantity == 1


def test_alternatives_accept_string_or_list():
    assert ProductIntent(alternative_products="PTFE Tape").alternative_products == ["PTFE Tape"]
    assert ProductIntent(alternative_products=None).alternative_products == []


def test_confidence_bands():
    assert confidence_band(0.94) == "direct"
    assert confidence_band(0.70) == "uncertain"
    assert confidence_band(0.40) == "clarify"


def test_clarification_options_deduplicate():
    intent = ProductIntent(product="Teflon Tape",
                           alternative_products=["teflon tape", "PVC Sealing Tape"])
    options = clarification_options(intent)
    assert options[0] == "Teflon Tape"
    assert "PVC Sealing Tape" in options
    assert len(options) <= 3


def test_khata_intent_normalizes_entry_type():
    assert KhataIntent(entry_type="paid").entry_type == "payment"
    assert KhataIntent(entry_type="udhaar").entry_type == "credit"
    assert KhataIntent(amount="-50").amount == 0.0
