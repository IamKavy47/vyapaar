"""JSON extraction, request/demand document construction, role authorization."""
from app.models.demand import build_demand_event
from app.models.inventory import product_key
from app.models.merchant_match import MatchStatus, build_match_document
from app.models.product_request import RequestStatus, build_request_document
from app.models.shop import build_shop_document, normalize_category
from app.models.user import UserRole
from app.services.auth_service import require_role
from app.utils.parsing import extract_json, extract_json_object, normalize_text


def test_extract_json_from_fenced_block():
    raw = 'Here you go:\n```json\n{"product": "Teflon Tape"}\n```'
    assert extract_json(raw)["product"] == "Teflon Tape"


def test_extract_json_with_preamble():
    assert extract_json_object('Sure! {"a": 1} hope that helps')["a"] == 1


def test_extract_json_returns_empty_on_garbage():
    assert extract_json_object("no json at all") == {}


def test_product_key_collapses_whitespace_and_case():
    assert product_key("  Teflon   Tape ") == product_key("teflon tape")


def test_normalize_text():
    assert normalize_text("  a   b  ") == "a b"


def test_shop_document_defaults_capabilities_from_category():
    shop = build_shop_document(user_id="u1", shop_name="Sharma Hardware", phone="1",
                               category="hardware")
    assert "plumbing" in shop["capabilities"]
    assert shop["location"] is None  # no coordinates supplied yet
    assert shop["is_active"] is True


def test_shop_document_stores_geojson():
    shop = build_shop_document(user_id="u1", shop_name="S", phone="1", category="hardware",
                               latitude=24.0, longitude=75.0)
    assert shop["location"]["coordinates"] == [75.0, 24.0]


def test_request_document_starts_in_created_state():
    doc = build_request_document(
        request_id="REQ-1", customer_id="c1", telegram_user_id=1,
        intent={"product": "Teflon Tape", "category": "hardware", "confidence": 0.94},
        latitude=24.0, longitude=75.0,
    )
    assert doc["status"] == RequestStatus.CREATED.value
    assert doc["product_key"] == "teflon tape"
    assert doc["location"]["coordinates"] == [75.0, 24.0]


def test_match_document_starts_pending():
    doc = build_match_document(request_id="REQ-1", merchant_id="m1", distance_meters=203.4,
                               match_score=0.87)
    assert doc["status"] == MatchStatus.PENDING.value
    assert doc["price"] is None
    assert doc["distance_meters"] == 203.4


def test_demand_event_records_unavailable():
    event = build_demand_event(
        request_id="REQ-1", merchant_id="m1", product="Teflon Tape", category="hardware",
        sub_category="plumbing", latitude=24.0, longitude=75.0, response="unavailable",
    )
    assert event["response"] == "unavailable"
    assert event["product_key"] == "teflon tape"


def test_category_normalization():
    assert normalize_category("Hardware") == "hardware"
    assert normalize_category(None) == "other"
    assert normalize_category("bakery") == "bakery_food"
    assert normalize_category("Mobile & Electronics") == "mobile_electronics"


def test_role_authorization():
    shopkeeper = {"role": UserRole.SHOPKEEPER.value}
    customer = {"role": UserRole.CUSTOMER.value}
    admin = {"role": UserRole.ADMIN.value}
    assert require_role(shopkeeper, UserRole.SHOPKEEPER.value)[0]
    assert not require_role(customer, UserRole.SHOPKEEPER.value)[0]
    assert require_role(admin, UserRole.SHOPKEEPER.value)[0]  # admin overrides
    assert not require_role(None, UserRole.CUSTOMER.value)[0]
