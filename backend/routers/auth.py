import time
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import User
from schemas import LoginRequest, UserOut
from security import (
    authenticate_user,
    create_access_token,
    get_current_user,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Simple in-memory rate limiter for login attempts (per client IP).
# For a single-process kiosk deployment this is sufficient; a distributed
# store (Redis, etc.) would be needed for multi-node setups.
# ---------------------------------------------------------------------------
_MAX_FAILED = 5       # lock out after this many failures
_WINDOW = 15 * 60     # sliding window in seconds (15 minutes)

_failed_attempts: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(request: Request) -> None:
    ip = _client_ip(request)
    now = time.time()
    attempts = _failed_attempts.get(ip, [])
    # keep only attempts inside the window
    attempts = [t for t in attempts if now - t < _WINDOW]
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
    _failed_attempts.setdefault(ip, []).append(time.time())


def _clear_failures(request: Request) -> None:
    _failed_attempts.pop(_client_ip(request), None)


# ---------------------------------------------------------------------------

@router.post("/login")
def login(
    credentials: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _check_rate_limit(request)
    user = authenticate_user(
        db, credentials.username, credentials.password
    )
    if not user:
        _record_failure(request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    _clear_failures(request)
    token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UserOut.model_validate(user),
    }


@router.post("/login/form")
def login_form(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    _check_rate_limit(request)
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        _record_failure(request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    _clear_failures(request)
    token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)):
    return current_user
