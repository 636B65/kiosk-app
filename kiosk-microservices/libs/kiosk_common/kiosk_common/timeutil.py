from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time as a naive datetime.

    All services store naive UTC timestamps so values compare consistently
    across databases. Never use ``datetime.utcnow()`` (deprecated).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_dt(value) -> datetime | None:
    """Parse an ISO timestamp from another service's JSON (naive UTC)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
