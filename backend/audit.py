"""Audit trail helpers.

`record()` adds an AuditLog row to the caller's session without committing,
so the entry is written atomically with the change it describes.
"""

from sqlalchemy.orm import Session

from models import AuditLog, User

# Actor used for changes made from the public kiosk (no admin session).
KIOSK_ACTOR = "kiosk"
SYSTEM_ACTOR = "system"


def actor_name(user: User | None) -> str:
    return user.username if user is not None else SYSTEM_ACTOR


def record(
    db: Session,
    actor: str,
    action: str,
    entity: str = "",
    entity_id: object = "",
    details: str = "",
) -> None:
    db.add(
        AuditLog(
            actor=actor,
            action=action,
            entity=entity,
            entity_id=str(entity_id),
            details=details,
        )
    )


def describe_changes(before: dict, after: dict) -> str:
    """Human-readable "field: old -> new" list for the fields that changed."""
    parts = []
    for key, new in after.items():
        old = before.get(key)
        if old != new:
            parts.append(f"{key}: {_fmt(old)} -> {_fmt(new)}")
    return "; ".join(parts)


def _fmt(value) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "-"
    return str(value)
