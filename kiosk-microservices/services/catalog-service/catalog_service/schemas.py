from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_RESTOCK_QUANTITY = 100000
MAX_RESTOCK_NOTE_LENGTH = 200
MAX_ORDER_QUANTITY = 1000
MAX_ORDER_ITEMS = 50


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
    # The stock the admin's form showed; when given, `stock` is only saved if the
    # product still has exactly this much (else 409), so sales are never overwritten.
    expected_stock: Optional[int] = None
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
        return 5 if v is None else v

    model_config = ConfigDict(from_attributes=True)


class ProductInternalOut(ProductOut):
    """Full product for other services (cost price included)."""

    effective_price: float = 0.0
    is_low_stock: bool = False
    category_name: str = ""


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


ADJUSTMENT_REASONS = ("shrinkage", "damaged", "expired", "miscount", "other")
MAX_COUNT_ITEMS = 500


class StockCountItem(BaseModel):
    product_id: int
    counted: int = Field(ge=0, le=MAX_RESTOCK_QUANTITY)
    expected_stock: int
    reason: Optional[Literal["shrinkage", "damaged", "expired", "miscount", "other"]] = None
    note: str = Field(default="", max_length=200)


class StockCountIn(BaseModel):
    items: List[StockCountItem] = Field(min_length=1, max_length=MAX_COUNT_ITEMS)


class StockAdjustmentOut(BaseModel):
    id: int
    product_id: Optional[int] = None
    product_name: str
    expected: int
    counted: int
    difference: int
    reason: str
    unit_cost: Optional[float] = None
    note: str = ""
    created_by: str = ""
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class StockCountConflict(BaseModel):
    product_id: int
    product_name: str
    expected_stock: int
    current_stock: Optional[int] = None


class StockCountResult(BaseModel):
    applied: List[StockAdjustmentOut]
    conflicts: List[StockCountConflict]


class StockLineIn(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=MAX_ORDER_QUANTITY)


class StockRequest(BaseModel):
    items: List[StockLineIn] = Field(min_length=1, max_length=MAX_ORDER_ITEMS)


class ReservedLine(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    unit_price: float
    unit_cost: Optional[float] = None


class ReserveResult(BaseModel):
    items: List[ReservedLine]
