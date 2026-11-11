import time
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from auth_service.models import User
from auth_service.schemas import LoginRequest, UserOut
from auth_service.security import authenticate_user, create_access_token, token_claims
from kiosk_common.auth import Principal, get_current_user
from kiosk_common.db import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# In-memory rate limiter for login attempts (per client IP, per replica).
# With several replicas each one counts separately; add an ingress rate limit
# for a hard cap. The window keeps brute force slow either way.
# ---------------------------------------------------------------------------
_MAX_FAILED = 5
_WINDOW = 15 * 60
_MAX_TRACKED_IPS = 10_000

_failed_attempts: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Every trusted proxy (ingress controller, gateway) appends the address
        # it saw; only the entry that the outermost trusted proxy added is
        # trustworthy, anything before it may have been sent by the client.
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        hops = max(1, int(request.app.state.config.trusted_proxies))
        if parts:
            return parts[-hops] if len(parts) >= hops else parts[0]
    return request.client.host if request.client else "unknown"


def _check_rate_limit(request: Request) -> None:
    ip = _client_ip(request)
    now = time.time()
    attempts = [t for t in _failed_attempts.get(ip, []) if now - t < _WINDOW]
    _failed_attempts[ip] = attempts
    if len(attempts) >= _MAX_FAILED:
        retry_after = int(_WINDOW - (now - attempts[0]))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )


def _record_failure(request: Request) -> None:
    ip = _client_ip(request)
    now = time.time()
    _failed_attempts.setdefault(ip, []).append(now)
    if len(_failed_attempts) > _MAX_TRACKED_IPS:
        for key in [k for k, v in _failed_attempts.items() if now - v[-1] >= _WINDOW]:
            del _failed_attempts[key]


def _clear_failures(request: Request) -> None:
    _failed_attempts.pop(_client_ip(request), None)


def _login(request: Request, db: Session, username: str, password: str) -> tuple[User, str]:
    _check_rate_limit(request)
    user = authenticate_user(db, username, password)
    if not user:
        _record_failure(request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    _clear_failures(request)
    config = request.app.state.config
    token = create_access_token(
        config, token_claims(user), timedelta(minutes=config.access_token_expire_minutes)
    )
    return user, token


@router.post("/login")
def login(credentials: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user, token = _login(request, db, credentials.username, credentials.password)
    return {"access_token": token, "token_type": "bearer", "user": UserOut.model_validate(user)}


@router.post("/login/form")
def login_form(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    _, token = _login(request, db, form_data.username, form_data.password)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def read_me(current: Principal = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == current.username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return user
