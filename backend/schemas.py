from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MIN_PASSWORD_LENGTH = 8
MAX_ORDER_QUANTITY = 1000
MAX_ORDER_ITEMS = 50
MAX_NOTES_LENGTH = 500
MAX_RESTOCK_QUANTITY = 100000
MAX_RESTOCK_NOTE_LENGTH = 200


def normalize_barcodes(values) -> Optional[List[str]]:
    if values is None:
        return None
    if not isinstance(values, list):
        raise ValueError("barcodes must be a list of strings")
    if len(values) > 50:
        raise ValueError("a product may have at most 50 barcodes")
    normalized = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("barcodes must be strings")
        code = value.strip().casefold()
        if not code:
            continue
        if len(code) > 128:
            raise ValueError("barcodes must not exceed 128 characters")
        if code not in normalized:
            normalized.append(code)
    return normalized


class CategoryBase(BaseModel):
    name: str
    description: str = ""
    sort_order: int = 0


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


class CategoryOut(CategoryBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


def _check_special_window(starts: Optional[date], ends: Optional[date]) -> None:
    if starts and ends and ends < starts:
        raise ValueError("special_ends_on must not be before special_starts_on")


class ProductBase(BaseModel):
    name: str
    description: str = ""
    price: float = 0.0
    special_price: Optional[float] = None
    is_weekly_special: bool = False
    special_starts_on: Optional[date] = None
    special_ends_on: Optional[date] = None
    cost_price: Optional[float] = Field(default=None, ge=0)
    stock: int = 0
    low_stock_threshold: int = Field(default=5, ge=0)
    is_active: bool = True
    category_id: Optional[int] = None
    barcodes: List[str] = Field(default_factory=list)

    @field_validator("barcodes", mode="before")
    @classmethod
    def _normalize_barcodes(cls, values):
        return normalize_barcodes(values) or []


class ProductCreate(ProductBase):
    price: float = Field(default=0.0, ge=0)
    special_price: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_special_window(self):
        _check_special_window(self.special_starts_on, self.special_ends_on)
        return self


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = Field(default=None, ge=0)
    special_price: Optional[float] = Field(default=None, ge=0)
    is_weekly_special: Optional[bool] = None
    special_starts_on: Optional[date] = None
    special_ends_on: Optional[date] = None
    cost_price: Optional[float] = Field(default=None, ge=0)
    stock: Optional[int] = None
    low_stock_threshold: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    category_id: Optional[int] = None
    barcodes: Optional[List[str]] = None

    @field_validator("barcodes", mode="before")
    @classmethod
    def _normalize_barcodes(cls, values):
        return normalize_barcodes(values)

    @model_validator(mode="after")
    def _validate_special_window(self):
        _check_special_window(self.special_starts_on, self.special_ends_on)
        return self


class ProductOut(ProductBase):
    id: int
    image_url: Optional[str] = None
    category: Optional[CategoryOut] = None
    special_active: bool = False

    @field_validator("low_stock_threshold", mode="before")
    @classmethod
    def _default_threshold(cls, v):
        # Rows written outside the ORM may lack a threshold; never fail the public list.
        return 5 if v is None else v

    model_config = ConfigDict(from_attributes=True)


class RestockIn(BaseModel):
    quantity: int = Field(ge=1, le=MAX_RESTOCK_QUANTITY)
    unit_cost: Optional[float] = Field(default=None, ge=0)
    note: str = Field(default="", max_length=MAX_RESTOCK_NOTE_LENGTH)


class RestockOut(BaseModel):
    id: int
    product_id: Optional[int] = None
    product_name: str
    quantity: int
    unit_cost: Optional[float] = None
    stock_after: int
    note: str = ""
    created_by: str = ""
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AuditOut(BaseModel):
    id: int
    created_at: Optional[datetime] = None
    actor: str
    action: str
    entity: str = ""
    entity_id: str = ""
    details: str = ""

    model_config = ConfigDict(from_attributes=True)


class OrderItemIn(BaseModel):
    product_id: int
    quantity: int = 1

    @field_validator("quantity")
    @classmethod
    def _validate_quantity(cls, v: int) -> int:
        if v < 1:
            raise ValueError("quantity must be at least 1")
        if v > MAX_ORDER_QUANTITY:
            raise ValueError(f"quantity must not exceed {MAX_ORDER_QUANTITY}")
        return v


class OrderCreate(BaseModel):
    customer_username: str
    items: List[OrderItemIn]
    notes: str = ""
    # Required (and checked) only when the customer has set a PIN.
    customer_pin: Optional[str] = Field(default=None, max_length=16)

    @field_validator("items")
    @classmethod
    def _validate_items(cls, v: List[OrderItemIn]) -> List[OrderItemIn]:
        if not v:
            raise ValueError("order must contain at least one item")
        if len(v) > MAX_ORDER_ITEMS:
            raise ValueError(f"order must contain at most {MAX_ORDER_ITEMS} items")
        return v

    @field_validator("notes")
    @classmethod
    def _validate_notes(cls, v: str) -> str:
        if len(v) > MAX_NOTES_LENGTH:
            raise ValueError(f"notes must not exceed {MAX_NOTES_LENGTH} characters")
        return v


class OrderItemOut(BaseModel):
    id: int
    product_id: Optional[int] = None
    product_name: str
    quantity: int
    unit_price: float

    model_config = ConfigDict(from_attributes=True)


class OrderOut(BaseModel):
    id: int
    status: str
    subtotal: float
    total: float
    notes: str
    customer_username: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    due_date: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class OrderDetailOut(OrderOut):
    items: List[OrderItemOut] = []


class CustomerOut(BaseModel):
    id: int
    username: str
    created_at: Optional[datetime] = None
    has_pin: bool = False

    model_config = ConfigDict(from_attributes=True)


class MonthAgg(BaseModel):
    month: str
    orders: int = 0
    spent: float = 0.0


class WeekdayAgg(BaseModel):
    day: str
    orders: int = 0
    spent: float = 0.0


class CustomerStats(BaseModel):
    orders: int = 0
    paid_orders: int = 0
    pending_orders: int = 0
    cancelled_orders: int = 0
    total_spent: float = 0.0
    total_paid: float = 0.0
    balance: float = 0.0
    avg_order: float = 0.0
    items_bought: int = 0
    first_order_at: Optional[datetime] = None
    last_order_at: Optional[datetime] = None
    last_paid_at: Optional[datetime] = None
    last_paid_amount: float = 0.0
    top_item: Optional[str] = None
    top_item_qty: int = 0
    avg_orders_per_month: float = 0.0
    busiest_day: Optional[str] = None
    orders_per_month: List[MonthAgg] = []
    orders_by_weekday: List[WeekdayAgg] = []
    next_due_date: Optional[datetime] = None


class CustomerWithBalance(CustomerOut):
    balance: float = 0.0
    total_paid: float = 0.0
    order_count: int = 0
    stats: CustomerStats


class FavoriteOut(BaseModel):
    product_id: int
    name: str
    quantity: int


class CustomerHistoryOut(BaseModel):
    customer: CustomerOut
    balance: float = 0.0
    total_paid: float = 0.0
    orders: List[OrderDetailOut] = []
    stats: CustomerStats
    favorites: List[FavoriteOut] = []


class PinChangeIn(BaseModel):
    pin: str = Field(max_length=16)
    current_pin: Optional[str] = Field(default=None, max_length=16)


class SettingIn(BaseModel):
    key: str
    value: str


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str = ""

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(
                f"password must be at least {MIN_PASSWORD_LENGTH} characters"
            )
        return v


class UserUpdate(BaseModel):
    password: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("password")
    @classmethod
    def _validate_password_update(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(
                f"password must be at least {MIN_PASSWORD_LENGTH} characters"
            )
        return v


class LoginRequest(BaseModel):
    username: str
    password: str
