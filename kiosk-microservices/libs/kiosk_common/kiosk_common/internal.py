"""Service-to-service authentication: a shared token in the X-Internal-Token header.

``/internal/*`` routes are never exposed by the gateway; the token is a second
line of defence so a pod that is reachable inside the cluster still cannot be
driven by anything but the other kiosk services.
"""

import hmac

from fastapi import Header, HTTPException, Request

INTERNAL_HEADER = "X-Internal-Token"


def require_internal(
    request: Request,
    token: str | None = Header(default=None, alias=INTERNAL_HEADER),
) -> None:
    expected = request.app.state.config.internal_token
    if not token or not expected or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Internal token required")
