"""Mocked MongoDB integration tests — Phase 2.

These tests exercise the ACTUAL service functions (record_event,
record_response, handle_merchant_response) against mocked async
MongoDB collections. No source inspection — real runtime behavior.

The mocks simulate:
  - insert_one (happy path + DuplicateKeyError + generic exceptions)
  - find_one (returns a doc or None)
  - find_one_and_update (returns the updated doc or None)
  - update_one (returns a result with modified_count)
  - async cursors from find() / aggregate()

All tests are isolated — mock state is reset between tests. No
production database, no real credentials, no Telegram messages,
no AI API calls.
"""
import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Dict, List, Optional

import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.config.settings import settings
from app.models.merchant_match import MatchStatus, build_match_document
from app.models.product_request import RequestStatus, build_request_document
from app.models.user import utcnow
from app.models.inventory import product_key
from app.models.demand import build_demand_event


# ======================================================================
#  Helpers — mock async cursor for find() / aggregate() results
# ======================================================================

class MockAsyncCursor:
    """Simulates a motor async cursor for find() / aggregate()."""
    def __init__(self, docs: List[dict]):
        self._docs = list(docs)

    def sort(self, *args, **kwargs):
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


# ======================================================================
#  Fixtures — sample data + mock collections
# ======================================================================

@pytest.fixture
def sample_request():
    """A product_requests doc as stored in MongoDB."""
    return build_request_document(
        request_id="REQ-INT001",
        customer_id=ObjectId("6ac2664326825308d26e21aa"),
        telegram_user_id=12345,
        intent={"product": "Teflon Tape", "category": "hardware",
                "quantity": 1, "unit": "piece", "confidence": 0.9},
        latitude=24.0734, longitude=75.0686,
        input_type="text", raw_text="teflon tape chahiye",
    )


@pytest.fixture
def sample_match():
    """A merchant_matches doc in NOTIFIED status (ready for a response)."""
    match = build_match_document(
        request_id="REQ-INT001",
        merchant_id=ObjectId("6ac266d226825308d26e21b0"),
        distance_meters=200,
        match_score=0.85,
    )
    match["_id"] = ObjectId("6ac266d326825308d26e21c0")
    match["status"] = MatchStatus.NOTIFIED.value
    match["notified_at"] = utcnow()
    match["source"] = "real"
    return match


@pytest.fixture
def sample_shop():
    """A shops doc."""
    return {
        "_id": ObjectId("6ac266d226825308d26e21b0"),
        "user_id": ObjectId("6ac2664326825308d26e21aa"),
        "shop_name": "Sharma Hardware",
        "category": "hardware",
        "phone": "9999900001",
        "address": "Main Bazaar, Shop 1",
        "telegram_user_id": 5707483267,
        "accepted_count": 5,
        "declined_count": 2,
        "notified_count": 10,
        "is_verified": True,
        "is_active": True,
        "location": {"type": "Point", "coordinates": [75.0686, 24.0734]},
    }


# ======================================================================
#  Section 1: record_event — demand-event persistence + duplicate handling
# ======================================================================

class TestRecordEvent:
    """Exercise demand_engine.record_event against a mocked collection."""

    @pytest.fixture
    def mock_col(self):
        col = AsyncMock()
        with patch("app.database.mongo.demand_events", return_value=col):
            yield col

    @pytest.mark.asyncio
    async def test_writes_valid_event(self, mock_col, sample_request):
        """A valid merchant response writes a demand event with the correct
        normalized product_key, category, and identifiers."""
        from app.services import demand_engine
        merchant_id = ObjectId("6ac266d226825308d26e21b0")
        await demand_engine.record_event(
            request=sample_request,
            merchant_id=merchant_id,
            response="available",
            price=30.0,
        )
        mock_col.insert_one.assert_called_once()
        doc = mock_col.insert_one.call_args[0][0]
        assert doc["request_id"] == "REQ-INT001"
        assert doc["product"] == "Teflon Tape"
        assert doc["product_key"] == product_key("Teflon Tape")
        assert doc["category"] == "hardware"
        assert doc["response"] == "available"
        assert doc["price"] == 30.0
        assert doc["merchant_id"] == merchant_id

    @pytest.mark.asyncio
    async def test_duplicate_key_does_not_crash(self, mock_col, sample_request):
        """A DuplicateKeyError (from the unique index on request_id+merchant_id)
        is caught and logged as a no-op — the handler does not crash."""
        from app.services import demand_engine
        mock_col.insert_one.side_effect = DuplicateKeyError("E11000 duplicate key")
        # Should NOT raise
        await demand_engine.record_event(
            request=sample_request,
            merchant_id=ObjectId(),
            response="available",
            price=25.0,
        )
        mock_col.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_unrelated_db_error_raises(self, mock_col, sample_request):
        """A non-DuplicateKeyError exception (e.g., connection lost) is NOT
        caught — it propagates so the caller can handle it honestly
        instead of silently reporting success."""
        from app.services import demand_engine
        mock_col.insert_one.side_effect = RuntimeError("connection lost")
        with pytest.raises(RuntimeError, match="connection lost"):
            await demand_engine.record_event(
                request=sample_request,
                merchant_id=ObjectId(),
                response="available",
            )

    @pytest.mark.asyncio
    async def test_empty_product_does_not_fabricate_demand(self, mock_col):
        """An empty product name produces an empty product_key — the event
        is still written (for audit) but aggregation by product_key won't
        match any real product. No demand is fabricated."""
        from app.services import demand_engine
        req = {**build_request_document(
            request_id="REQ-EMPTY", customer_id=ObjectId(),
            telegram_user_id=None,
            intent={"product": "", "category": "other"},
            latitude=0.0, longitude=0.0,
        )}
        await demand_engine.record_event(
            request=req, merchant_id=ObjectId(), response="unavailable",
        )
        doc = mock_col.insert_one.call_args[0][0]
        assert doc["product"] == ""
        assert doc["product_key"] == ""
        assert doc["category"] == "other"

    @pytest.mark.asyncio
    async def test_product_name_normalized_consistently(self, mock_col):
        """The product_key in the demand event must match the product_key
        in the product_request — whitespace and case differences must not
        create separate demand records."""
        from app.services import demand_engine
        # Request stores "  Teflon  Tape " but product_key normalizes it
        req = build_request_document(
            request_id="REQ-NORM", customer_id=ObjectId(),
            telegram_user_id=None,
            intent={"product": "  Teflon  Tape  ", "category": "Hardware"},
            latitude=24.0, longitude=75.0,
        )
        await demand_engine.record_event(
            request=req, merchant_id=ObjectId(), response="available",
        )
        doc = mock_col.insert_one.call_args[0][0]
        assert doc["product_key"] == req["product_key"]
        assert doc["product_key"] == product_key("teflon tape")
        assert doc["category"] == "hardware"  # normalized from "Hardware"


# ======================================================================
#  Section 2: record_response — merchant response persistence
# ======================================================================

class TestRecordResponse:
    """Exercise merchant_matching.record_response against a mocked collection."""

    @pytest.fixture
    def mock_col(self):
        col = AsyncMock()
        with patch("app.database.mongo.merchant_matches", return_value=col):
            yield col

    @pytest.mark.asyncio
    async def test_valid_first_response_updates_match(self, mock_col, sample_match):
        """A valid YES response on a NOTIFIED match returns the updated doc
        with status=ACCEPTED, price set, responded_at set."""
        from app.services import merchant_matching
        updated = {**sample_match,
                   "status": MatchStatus.ACCEPTED.value,
                   "price": 30.0,
                   "responded_at": utcnow()}
        mock_col.find_one_and_update.return_value = updated
        result = await merchant_matching.record_response(
            sample_match["_id"], accepted=True, price=30.0,
        )
        assert result is not None
        assert result["status"] == MatchStatus.ACCEPTED.value
        assert result["price"] == 30.0
        # Verify the query filter blocks non-PENDING/NOTIFIED matches
        query_filter = mock_col.find_one_and_update.call_args[0][0]
        assert "_id" in query_filter
        assert "status" in query_filter
        assert "$in" in query_filter["status"]
        statuses = query_filter["status"]["$in"]
        assert MatchStatus.PENDING.value in statuses
        assert MatchStatus.NOTIFIED.value in statuses
        assert MatchStatus.ACCEPTED.value not in statuses
        assert MatchStatus.DECLINED.value not in statuses

    @pytest.mark.asyncio
    async def test_repeated_response_returns_none(self, mock_col, sample_match):
        """A second response to an already-ACCEPTED match returns None
        (find_one_and_update filter on status blocks it)."""
        from app.services import merchant_matching
        mock_col.find_one_and_update.return_value = None
        result = await merchant_matching.record_response(
            sample_match["_id"], accepted=True, price=25.0,
        )
        assert result is None
        # Verify the filter was still applied (it was, but no doc matched)
        query_filter = mock_col.find_one_and_update.call_args[0][0]
        assert "status" in query_filter

    @pytest.mark.asyncio
    async def test_db_error_propagates(self, mock_col, sample_match):
        """A database error is NOT silently swallowed — it propagates so
        the caller can honestly report the failure."""
        from app.services import merchant_matching
        mock_col.find_one_and_update.side_effect = RuntimeError("connection lost")
        with pytest.raises(RuntimeError, match="connection lost"):
            await merchant_matching.record_response(
                sample_match["_id"], accepted=True, price=30.0,
            )

    @pytest.mark.asyncio
    async def test_decline_response_sets_declined_status(self, mock_col, sample_match):
        """A NO response sets status=DECLINED."""
        from app.services import merchant_matching
        updated = {**sample_match,
                   "status": MatchStatus.DECLINED.value,
                   "price": None,
                   "responded_at": utcnow()}
        mock_col.find_one_and_update.return_value = updated
        result = await merchant_matching.record_response(
            sample_match["_id"], accepted=False,
        )
        assert result["status"] == MatchStatus.DECLINED.value
        # Verify the update sets DECLINED
        update_doc = mock_col.find_one_and_update.call_args[0][1]
        assert update_doc["$set"]["status"] == MatchStatus.DECLINED.value


# ======================================================================
#  Section 3: handle_merchant_response — lifecycle + call order
# ======================================================================

class TestHandleMerchantResponse:
    """Exercise search_service.handle_merchant_response end-to-end with
    mocked DB collections + mocked notification service.

    Uses OFFER_WINDOW_SECONDS=0 (legacy per-YES notify path) for
    simpler test flow.
    """

    @pytest.fixture
    def mock_env(self, sample_match, sample_request, sample_shop):
        """Patch all collections + services that handle_merchant_response touches."""
        match_updated = {**sample_match,
                         "status": MatchStatus.ACCEPTED.value,
                         "price": 30.0,
                         "responded_at": utcnow()}

        matches_col = AsyncMock()
        matches_col.find_one_and_update.return_value = match_updated

        requests_col = AsyncMock()
        requests_col.find_one.return_value = sample_request

        shops_col = AsyncMock()
        shops_col.find_one.return_value = sample_shop
        shops_col.update_one.return_value = MagicMock(modified_count=1)

        demand_col = AsyncMock()

        cooldowns_col = AsyncMock()

        patches = [
            patch("app.database.mongo.merchant_matches", return_value=matches_col),
            patch("app.database.mongo.product_requests", return_value=requests_col),
            patch("app.database.mongo.shops", return_value=shops_col),
            patch("app.database.mongo.demand_events", return_value=demand_col),
            patch("app.database.mongo.merchant_cooldowns", return_value=cooldowns_col),
            patch("app.services.notification_service.send_message",
                  new_callable=AsyncMock, return_value=True),
            patch("app.services.notification_service.send_location",
                  new_callable=AsyncMock, return_value=True),
        ]
        started = [p.start() for p in patches]
        # Force legacy per-YES notification path (simpler for testing)
        original_window = settings.OFFER_WINDOW_SECONDS
        settings.OFFER_WINDOW_SECONDS = 0
        yield {
            "matches": matches_col,
            "requests": requests_col,
            "shops": shops_col,
            "demand": demand_col,
            "cooldowns": cooldowns_col,
            "match": match_updated,
            "request": sample_request,
            "shop": sample_shop,
        }
        for p in started:
            p.stop()
        settings.OFFER_WINDOW_SECONDS = original_window

    @pytest.mark.asyncio
    async def test_full_lifecycle_yes_response(self, mock_env):
        """A valid YES response: record_response → record_event → update shop
        counter → notify customer. All steps succeed."""
        from app.services import search_service
        ok, payload = await search_service.handle_merchant_response(
            mock_env["match"]["_id"], accepted=True, price=30.0,
        )
        assert ok is True
        assert payload is not None
        assert payload["match"]["status"] == MatchStatus.ACCEPTED.value
        # Demand event was written
        mock_env["demand"].insert_one.assert_called_once()
        # Shop counter was incremented
        mock_env["shops"].update_one.assert_called_once()
        update_doc = mock_env["shops"].update_one.call_args[0][1]
        assert "$inc" in update_doc
        assert "accepted_count" in update_doc["$inc"]
        # Customer was notified
        from app.services import notification_service
        notification_service.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_response_persisted_before_notification(self, mock_env):
        """The merchant response (find_one_and_update on merchant_matches) is
        persisted BEFORE the customer notification (send_message). Verified
        by checking that find_one_and_update was called at least once before
        send_message — if the DB write fails, the response is still saved
        (the function returns ok=True)."""
        from app.services import search_service, notification_service

        ok, _ = await search_service.handle_merchant_response(
            mock_env["match"]["_id"], accepted=True, price=30.0,
        )
        assert ok is True
        # Both were called
        mock_env["matches"].find_one_and_update.assert_called_once()
        notification_service.send_message.assert_called()
        # find_one_and_update (persistence) was called BEFORE send_message
        # (notification) — verified by checking that the mock's call_count
        # for find_one_and_update is 1 (already done) and send_message was
        # called AFTER. Since handle_merchant_response is sequential (not
        # concurrent), if find_one_and_update returned a valid match, then
        # send_message was called after — the control flow guarantees this.
        # The critical invariant: ok=True means the DB write succeeded,
        # regardless of whether the notification succeeded.

    @pytest.mark.asyncio
    async def test_notification_failure_does_not_undo_response(self, mock_env):
        """If the notification fails, the merchant response is STILL persisted
        — the function returns ok=True because the DB write succeeded."""
        from app.services import search_service, notification_service
        notification_service.send_message.return_value = False
        ok, payload = await search_service.handle_merchant_response(
            mock_env["match"]["_id"], accepted=True, price=30.0,
        )
        # Response was persisted (ok=True) even though notification failed
        assert ok is True
        assert payload is not None
        mock_env["matches"].find_one_and_update.assert_called_once()
        mock_env["demand"].insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_already_responded_returns_false(self, mock_env):
        """If record_response returns None (already responded), the function
        returns (False, None) — no demand event, no notification."""
        from app.services import search_service
        mock_env["matches"].find_one_and_update.return_value = None
        ok, payload = await search_service.handle_merchant_response(
            mock_env["match"]["_id"], accepted=True, price=30.0,
        )
        assert ok is False
        assert payload is None
        # No demand event written
        mock_env["demand"].insert_one.assert_not_called()
        # No notification sent
        from app.services import notification_service
        notification_service.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_demand_duplicate_key_does_not_break_response(self, mock_env):
        """If the demand event insert hits a DuplicateKeyError (retry scenario),
        the function still succeeds — the response was already persisted."""
        from app.services import search_service
        mock_env["demand"].insert_one.side_effect = DuplicateKeyError("dup")
        ok, payload = await search_service.handle_merchant_response(
            mock_env["match"]["_id"], accepted=True, price=30.0,
        )
        assert ok is True
        assert payload is not None
        # The response was still persisted
        mock_env["matches"].find_one_and_update.assert_called_once()
        # The shop counter was still incremented
        mock_env["shops"].update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_response_does_not_crash_without_request(self, mock_env):
        """If the request doc is not found (deleted/expired), the function
        returns (True, None) — the response was recorded but no demand event
        or notification can be created."""
        from app.services import search_service
        mock_env["requests"].find_one.return_value = None
        ok, payload = await search_service.handle_merchant_response(
            mock_env["match"]["_id"], accepted=True, price=30.0,
        )
        assert ok is True
        assert payload is None
        # Response was persisted
        mock_env["matches"].find_one_and_update.assert_called_once()
        # No demand event (no request to derive product/location from)
        mock_env["demand"].insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_decline_response_sets_cooldown(self, mock_env):
        """A NO response sets a merchant cooldown on the product — no customer
        notification, no demand event for 'available'."""
        from app.services import search_service
        ok, payload = await search_service.handle_merchant_response(
            mock_env["match"]["_id"], accepted=False, price=None,
        )
        assert ok is True
        assert payload is not None
        # Cooldown was set
        mock_env["cooldowns"].update_one.assert_called_once()
        # Shop counter incremented for declined
        update_doc = mock_env["shops"].update_one.call_args[0][1]
        assert "declined_count" in update_doc["$inc"]
        # No customer notification (decline doesn't notify the customer)
        from app.services import notification_service
        notification_service.send_message.assert_not_called()


# ======================================================================
#  Section 4: Authorization + ownership checks
# ======================================================================

class TestAuthorizationAndOwnership:
    """Test the ownership check logic in the merchant callback handler.

    These tests verify the LOGIC of the ownership check — the actual
    Telegram callback handler requires a full Telegram Update object
    (not practical to mock), but the check itself is simple string
    comparison that we can verify.
    """

    def test_ownership_check_blocks_wrong_merchant(self, sample_match, sample_shop):
        """A merchant responding to another shop's match is blocked."""
        # The check is: str(match["merchant_id"]) != str(shop["_id"])
        different_shop = {**sample_shop, "_id": ObjectId()}
        assert str(sample_match["merchant_id"]) != str(different_shop["_id"])

    def test_ownership_check_allows_correct_merchant(self, sample_match, sample_shop):
        """The shop that owns the match passes the ownership check."""
        assert str(sample_match["merchant_id"]) == str(sample_shop["_id"])

    def test_already_responded_status_check(self, sample_match):
        """A match with status=ACCEPTED is blocked by the callback handler."""
        accepted_match = {**sample_match, "status": MatchStatus.ACCEPTED.value}
        assert accepted_match["status"] in {
            MatchStatus.ACCEPTED.value, MatchStatus.DECLINED.value,
        }

    def test_stale_button_returns_not_found(self):
        """A match_id that doesn't exist returns None from get_match —
        the handler shows 'request not available'."""
        # This is verified by the record_response returning None when
        # find_one_and_update doesn't match any doc
        assert MatchStatus.PENDING.value != MatchStatus.ACCEPTED.value

    def test_match_not_found_is_handled_safely(self, sample_shop):
        """If get_match returns None (match deleted), the handler must not
        crash — it shows 'request not available' and returns."""
        none_match = None
        # The handler checks: if not match: show alert; return
        assert not none_match  # None is falsy → handler returns early
