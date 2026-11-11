"""Audit trail helpers: events go through the outbox to the audit service."""

from kiosk_common.http import ServiceClient
from kiosk_common.outbox import publish
from kiosk_common.timeutil import utcnow

# Actor used for changes made from the public kiosk (no admin session).
KIOSK_ACTOR = "kiosk"
SYSTEM_ACTOR = "system"
TOPIC = "audit"


def record(
    db,
    outbox_model,
    actor: str,
    action: str,
    entity: str = "",
    entity_id: object = "",
    details: str = "",
) -> None:
    """Queue an audit entry in the caller's transaction (written when it commits)."""
    publish(
        db,
        outbox_model,
        TOPIC,
        {
            "created_at": utcnow().isoformat(),
            "actor": actor,
            "action": action,
            "entity": entity,
            "entity_id": str(entity_id),
            "details": details,
        },
    )


def audit_sink(audit_client: ServiceClient):
    def send(events: list[dict]) -> None:
        audit_client.post("/internal/audit/events", json={"events": events})

    return send


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
