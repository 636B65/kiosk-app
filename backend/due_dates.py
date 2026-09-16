"""Payment due-date helpers.

A store-wide payment due date can be configured in Settings as
`payment_due_date` (an ISO date, e.g. "2026-10-15"). When it is set, newly
created orders are due by that date. When it is unset (the default) orders
have no due date.
"""

from datetime import date, datetime, time

from models import Setting
from sqlalchemy.orm import Session

DUE_DATE_SETTING = "payment_due_date"


def parse_due_date(value) -> date | None:
    """Parse the configured due date; None when unset or invalid."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def compute_due_time(due_date: date | None) -> datetime | None:
    """The exact due-by moment, or None when there is no end date."""
    if due_date is None:
        return None
    return datetime.combine(due_date, time(23, 59, 59))


def get_due_date(db: Session) -> datetime | None:
    """The store-wide due-by moment applied to new orders, or None."""
    setting = db.get(Setting, DUE_DATE_SETTING) if db else None
    value = setting.value if setting else None
    return compute_due_time(parse_due_date(value))
