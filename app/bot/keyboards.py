"""All Telegram keyboards. Inline for actions, reply keyboards for menus."""
from typing import List, Optional

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.models.shop import CATEGORIES, CATEGORY_LABELS


def role_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 I am a Customer", callback_data="role:customer")],
        [InlineKeyboardButton("🏪 I am a Shopkeeper", callback_data="role:shopkeeper")],
        [InlineKeyboardButton("🔐 Login / Register", callback_data="auth:link")],
        [InlineKeyboardButton("❓ Help", callback_data="nav:help")],
    ])


def auth_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Open secure login page", url=url)],
        [InlineKeyboardButton("🔄 I've linked — refresh", callback_data="auth:check")],
    ])


def customer_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["🔎 Find Product", "🛒 Browse Nearby"],
            ["🎤 Voice Search", "📷 Photo Search"],
            ["🧾 My Requests", "📍 My Location"],
            ["📏 Range", "📒 My Khata"],
            ["⚙️ Profile", "🚪 Logout"],
        ],
        resize_keyboard=True,
    )


def merchant_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["🏪 My Shop", "📦 Inventory"],
            ["🔔 Requests", "📊 Demand"],
            ["📒 Khata", "📍 Location"],
            ["⚙️ Settings", "🚪 Logout"],
        ],
        resize_keyboard=True,
    )


def location_request_keyboard(label: str = "📍 Share Location") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(label, request_location=True)], ["⬅️ Back"]],
        resize_keyboard=True, one_time_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def merchant_response_keyboard(match_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ YES", callback_data=f"mr:yes:{match_id}"),
        InlineKeyboardButton("❌ NO", callback_data=f"mr:no:{match_id}"),
    ]])


def clarification_keyboard(options: List[str]) -> InlineKeyboardMarkup:
    numerals = ["1️⃣", "2️⃣", "3️⃣"]
    rows = [
        [InlineKeyboardButton(f"{numerals[i]} {option}", callback_data=f"clar:{i}")]
        for i, option in enumerate(options[:3])
    ]
    rows.append([InlineKeyboardButton("✍️ Something else", callback_data="clar:other")])
    return InlineKeyboardMarkup(rows)


def category_keyboard() -> InlineKeyboardMarkup:
    rows, row = [], []
    for index, category in enumerate(CATEGORIES, start=1):
        row.append(InlineKeyboardButton(CATEGORY_LABELS[category], callback_data=f"cat:{category}"))
        if index % 2 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def inventory_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 View items", callback_data="inv:list")],
        [InlineKeyboardButton("🎤 Add by voice", callback_data="inv:voice")],
        [InlineKeyboardButton("📷 Add from invoice/shelf photo", callback_data="inv:photo")],
    ])


def khata_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Summary", callback_data="khata:summary")],
        [InlineKeyboardButton("➕ Add entry (text/voice)", callback_data="khata:add")],
        [InlineKeyboardButton("📧 Send reminder", callback_data="khata:remind")],
    ])


def repeat_request_keyboard(request_ids: List[str], labels: List[str]) -> Optional[InlineKeyboardMarkup]:
    rows = [
        [InlineKeyboardButton(f"🔁 {label}", callback_data=f"rep:{rid}")]
        for rid, label in zip(request_ids[:5], labels[:5])
    ]
    return InlineKeyboardMarkup(rows) if rows else None


def logout_confirm_keyboard() -> InlineKeyboardMarkup:
    """Logging out unlinks Telegram, so it is worth one deliberate tap."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚪 Yes, log me out", callback_data="logout:confirm")],
        [InlineKeyboardButton("↩️ Cancel", callback_data="logout:cancel")],
    ])


def browse_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧺 What's in stock nearby", callback_data="brs:stock")],
        [InlineKeyboardButton("🏪 Shops around me", callback_data="brs:shops")],
        [InlineKeyboardButton("🏷️ Browse by category", callback_data="brs:cats")],
    ])


def browse_category_keyboard(rows: List[dict]) -> InlineKeyboardMarkup:
    """Only categories that actually have shops nearby, with their counts."""
    buttons, row = [], []
    for index, entry in enumerate(rows[:12], start=1):
        label = f"{entry['label']} ({entry['shops']})"
        row.append(InlineKeyboardButton(label, callback_data=f"brs:cat:{entry['category']}"))
        if index % 2 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="brs:menu")])
    return InlineKeyboardMarkup(buttons)


def browse_shops_keyboard(shops: List[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            f"🏪 {shop['shop_name']} · {int(shop['distance_meters'])}m",
            callback_data=f"brs:shop:{shop['shop_id']}",
        )]
        for shop in shops[:8]
    ]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="brs:menu")])
    return InlineKeyboardMarkup(rows)


def browse_products_keyboard(products: List[dict]) -> InlineKeyboardMarkup:
    """One reserve button per listed item, numbered to match the message text."""
    rows = []
    for index, entry in enumerate(products[:8], start=1):
        price = f" ₹{entry['price']:g}" if entry.get("price") is not None else ""
        rows.append([InlineKeyboardButton(
            f"🛒 {index}. {entry['product'][:22]}{price}",
            callback_data=f"brs:buy:{entry['item_id']}",
        )])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="brs:menu")])
    return InlineKeyboardMarkup(rows)


def shop_actions_keyboard(shop: dict) -> InlineKeyboardMarkup:
    """Navigation is a URL button so it opens Maps directly, no copy-paste."""
    rows = []
    if shop.get("navigation_url"):
        rows.append([InlineKeyboardButton("🧭 Navigate to shop", url=shop["navigation_url"])])
    rows.append([InlineKeyboardButton("📦 See what's in stock",
                                      callback_data=f"brs:stock_shop:{shop['shop_id']}")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="brs:shops")])
    return InlineKeyboardMarkup(rows)


def navigation_keyboard(navigation_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🧭 Navigate", url=navigation_url)]])


def range_keyboard(current_meters: int, presets: List[int]) -> InlineKeyboardMarkup:
    """Preset distances plus a way to type an exact one.

    A checkmark on the active preset doubles as a confirmation that the setting
    actually took — otherwise a tap with no visible change reads as broken.
    """
    def label(meters: int) -> str:
        text = f"{meters // 1000}km" if meters >= 1000 else f"{meters}m"
        return f"✅ {text}" if meters == current_meters else text

    rows, row = [], []
    for index, meters in enumerate(presets, start=1):
        row.append(InlineKeyboardButton(label(meters), callback_data=f"rng:{meters}"))
        if index % 3 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("✏️ Enter exact distance", callback_data="rng:custom")])
    return InlineKeyboardMarkup(rows)
