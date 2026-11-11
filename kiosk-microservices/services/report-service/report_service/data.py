"""Loading the data a report needs from the other services."""

from dataclasses import dataclass, field
from datetime import date, datetime, time

from fastapi import Request

from kiosk_common.timeutil import parse_dt

DUE_DATE_SETTING = "payment_due_date"


@dataclass
class ReportData:
    orders: list[dict] = field(default_factory=list)
    products: list[dict] = field(default_factory=list)
    customers: list[dict] = field(default_factory=list)
    settings: dict = field(default_factory=dict)

    @property
    def due_date(self) -> datetime | None:
        value = self.settings.get(DUE_DATE_SETTING)
        if not value:
            return None
        try:
            return datetime.combine(date.fromisoformat(str(value)), time(23, 59, 59))
        except ValueError:
            return None


def _with_dates(order: dict) -> dict:
    order = dict(order)
    for key in ("created_at", "completed_at", "due_date"):
        order[key] = parse_dt(order.get(key))
    return order


def load(request: Request, *, products: bool = False, customers: bool = False, settings: bool = False) -> ReportData:
    clients = request.app.state.clients
    data = ReportData(orders=[_with_dates(o) for o in clients["orders"].get("/internal/orders/export")])
    if products:
        data.products = clients["catalog"].get("/internal/products")
    if customers:
        data.customers = clients["customers"].get("/internal/customers")
    if settings:
        data.settings = clients["settings"].get("/api/settings") or {}
    return data


def load_adjustments(request: Request, start: datetime | None, end: datetime | None) -> list[dict]:
    params = {}
    if start is not None:
        params["start"] = start.isoformat()
    if end is not None:
        params["end"] = end.isoformat()
    rows = request.app.state.clients["catalog"].get("/internal/adjustments", params=params)
    for row in rows:
        row["created_at"] = parse_dt(row.get("created_at"))
    return rows
