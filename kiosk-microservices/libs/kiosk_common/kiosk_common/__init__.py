"""Shared building blocks for the kiosk microservices.

Every service is a FastAPI app built with ``create_base_app`` and owns its own
database. Services talk to each other over HTTP (``ServiceClient``) with a
shared internal token, and publish audit events through a transactional outbox
(``outbox``) that a background relay ships to the audit service.
"""

__all__ = [
    "app",
    "audit",
    "auth",
    "config",
    "db",
    "http",
    "internal",
    "money",
    "outbox",
    "testing",
    "timeutil",
    "usernames",
]
