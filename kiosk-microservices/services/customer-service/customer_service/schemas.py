from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


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


class OrderItemOut(BaseModel):
    id: int
    product_id: Optional[int] = None
    product_name: str
    quantity: int
    unit_price: float


class OrderDetailOut(BaseModel):
    id: int
    status: str
    subtotal: float
    total: float
    notes: str
    customer_username: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    due_date: Optional[datetime] = None
    items: List[OrderItemOut] = []


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


class ResolveIn(BaseModel):
    username: str
    pin: Optional[str] = Field(default=None, max_length=16)


class ResolveOut(BaseModel):
    id: int
    username: str
    created: bool = False
