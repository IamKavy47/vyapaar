"""Auth / user API schemas."""
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.shop import normalize_category
from app.models.user import UserRole


class RegisterPayload(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str = Field(min_length=6, max_length=20)
    password: str = Field(min_length=8, max_length=128)
    role: str = UserRole.CUSTOMER.value

    # Shopkeeper-only. Captured at registration because these barely ever change,
    # and a shop without a category or a pin cannot be matched to anybody.
    shop_name: Optional[str] = Field(default=None, max_length=120)
    shop_category: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    address: Optional[str] = Field(default=None, max_length=300)

    @field_validator("role")
    @classmethod
    def _role(cls, v):
        value = (v or "").strip().lower()
        if value not in {UserRole.CUSTOMER.value, UserRole.SHOPKEEPER.value}:
            return UserRole.CUSTOMER.value
        return value

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        cleaned = "".join(ch for ch in v if ch.isdigit() or ch == "+")
        if len(cleaned) < 6:
            raise ValueError("Please enter a valid phone number.")
        return cleaned

    @field_validator("shop_category")
    @classmethod
    def _category(cls, v):
        return normalize_category(v) if v else None

    @field_validator("latitude", "longitude", mode="before")
    @classmethod
    def _coordinate(cls, v):
        # Browser geolocation posts an empty string when the user declines.
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @field_validator("shop_name", "address")
    @classmethod
    def _trimmed(cls, v):
        cleaned = (v or "").strip()
        return cleaned or None

    @model_validator(mode="after")
    def _shopkeeper_needs_a_category(self):
        if self.role == UserRole.SHOPKEEPER.value and not self.shop_category:
            raise ValueError("Please choose the category your shop belongs to.")
        return self

    @property
    def has_location(self) -> bool:
        return self.latitude is not None and self.longitude is not None


class LoginPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserPublic(BaseModel):
    id: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    telegram_user_id: Optional[int] = None
    is_verified: bool = False
