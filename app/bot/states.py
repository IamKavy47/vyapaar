"""Lightweight conversation state kept in context.user_data."""

MODE = "mode"
PENDING_PRICE_MATCH = "pending_price_match"
PENDING_INTENT = "pending_intent"
PENDING_ROLE = "pending_role"
LAST_REQUEST_ID = "last_request_id"

# Modes
MODE_IDLE = "idle"
MODE_SEARCH = "search"
MODE_KHATA = "khata"
MODE_INVENTORY = "inventory"
MODE_AWAIT_PRICE = "await_price"
MODE_AWAIT_SHOP_NAME = "await_shop_name"
MODE_AWAIT_CATEGORY = "await_category"
MODE_AWAIT_CAPABILITIES = "await_capabilities"
MODE_AWAIT_KHATA_REMINDER = "await_khata_reminder"
MODE_AWAIT_RADIUS = "await_radius"


def set_mode(context, mode: str) -> None:
    context.user_data[MODE] = mode


def get_mode(context) -> str:
    return context.user_data.get(MODE, MODE_IDLE)


def clear_mode(context) -> None:
    context.user_data[MODE] = MODE_IDLE
    context.user_data.pop(PENDING_PRICE_MATCH, None)
