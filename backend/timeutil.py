from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time as a naive datetime.

    The database (SQLite) stores naive UTC timestamps, so values written by
    this helper compare consistently with what is read back. Using
    ``datetime.now(timezone.utc)`` (then dropping the tzinfo) avoids the
    deprecated ``datetime.utcnow()``.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
