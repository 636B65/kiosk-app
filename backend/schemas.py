from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

MIN_PASSWORD_LENGTH = 8
MAX_ORDER_QUANTITY = 1000
MAX_ORDER_ITEMS = 50
MAX_NOTES_LENGTH = 500


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


class ProductBase(BaseModel):
    name: str
    description: str = ""
    price: float = 0.0
    special_price: Optional[float] = None
    is_weekly_special: bool = False
    stock: int = 0
    is_active: bool = True
    category_id: Optional[int] = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    special_price: Optional[float] = None
    is_weekly_special: Optional[bool] = None
    stock: Optional[int] = None
    is_active: Optional[bool] = None
    category_id: Optional[int] = None


class ProductOut(ProductBase):
    id: int
    image_url: Optional[str] = None
    category: Optional[CategoryOut] = None

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

    model_config = ConfigDict(from_attributes=True)


class OrderDetailOut(OrderOut):
    items: List[OrderItemOut] = []


class CustomerOut(BaseModel):
    id: int
    username: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CustomerStats(BaseModel):
    orders: int = 0
    total_spent: float = 0.0
    total_paid: float = 0.0
    balance: float = 0.0
    avg_order: float = 0.0
    items_bought: int = 0
    first_order_at: Optional[datetime] = None
    last_order_at: Optional[datetime] = None
    top_item: Optional[str] = None
    top_item_qty: int = 0


class CustomerWithBalance(CustomerOut):
    balance: float = 0.0
    total_paid: float = 0.0
    order_count: int = 0
    stats: CustomerStats


class CustomerHistoryOut(BaseModel):
    customer: CustomerOut
    balance: float = 0.0
    total_paid: float = 0.0
    orders: List[OrderDetailOut] = []
    stats: CustomerStats


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
