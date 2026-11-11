"""Payment due date: the store-wide ``payment_due_date`` setting (ISO date)."""

from datetime import date, datetime, time

DUE_DATE_SETTING = "payment_due_date"


def parse_due_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def compute_due_time(due_date: date | None) -> datetime | None:
    if due_date is None:
        return None
    return datetime.combine(due_date, time(23, 59, 59))


def due_time_from_settings(settings: dict) -> datetime | None:
    return compute_due_time(parse_due_date(settings.get(DUE_DATE_SETTING)))
