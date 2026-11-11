"""Admin authentication for every service.

Tokens are JWTs signed by the auth service with the shared SECRET_KEY. Other
services verify the signature locally and then ask the auth service whether the
account is still active and the password unchanged (the ``pwv`` claim), caching
positive answers briefly. The auth service itself checks its own user table.
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from kiosk_common.http import ServiceClient, UpstreamError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login/form")
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login/form", auto_error=False)


@dataclass(frozen=True)
class Principal:
    username: str
    user_id: int | None = None
    full_name: str = ""


Resolver = Callable[[str, dict], Principal | None]


class AuthVerifier:
    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        resolver: Resolver | None = None,
        cache_seconds: int = 60,
    ):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.resolver = resolver
        self.cache_seconds = cache_seconds
        self._cache: dict[str, tuple[float, Principal]] = {}

    def decode(self, token: str) -> dict | None:
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except jwt.PyJWTError:
            return None

    def verify(self, token: str) -> Principal | None:
        payload = self.decode(token)
        if not payload or not isinstance(payload.get("sub"), str):
            return None
        if self.resolver is None:
            return Principal(username=payload["sub"])
        key = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and cached[0] > now:
            return cached[1]
        principal = self.resolver(token, payload)
        if principal is not None and self.cache_seconds > 0:
            if len(self._cache) > 5000:
                self._cache.clear()
            self._cache[key] = (now + self.cache_seconds, principal)
        return principal

    def forget(self) -> None:
        self._cache.clear()


def introspect_resolver(auth_client: ServiceClient) -> Resolver:
    """Resolver that asks the auth service (fails closed when it is unreachable)."""

    def resolve(token: str, payload: dict) -> Principal | None:
        try:
            data = auth_client.post("/internal/auth/introspect", json={"token": token})
        except UpstreamError:
            return None
        if not data or not data.get("active"):
            return None
        return Principal(
            username=data["username"],
            user_id=data.get("user_id"),
            full_name=data.get("full_name") or "",
        )

    return resolve


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(request: Request, token: str = Depends(oauth2_scheme)) -> Principal:
    principal = request.app.state.auth.verify(token)
    if principal is None:
        raise _unauthorized()
    return principal


def get_optional_user(
    request: Request, token: str | None = Depends(optional_oauth2_scheme)
) -> Principal | None:
    """The signed-in admin for public endpoints that show admins more, else None."""
    if not token:
        return None
    return request.app.state.auth.verify(token)
