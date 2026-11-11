import hashlib
from datetime import timedelta

import bcrypt
import jwt
from sqlalchemy.orm import Session

from auth_service.config import Config
from auth_service.models import User
from kiosk_common.timeutil import utcnow


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# Checked when the username does not exist, so a failed login always costs one
# bcrypt verification and response times do not reveal which usernames exist.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equalizer", bcrypt.gensalt()).decode("utf-8")


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user


def password_version(user: User) -> str:
    """Token claim tied to the current password: changing it revokes old tokens."""
    return hashlib.sha256(user.password_hash.encode("utf-8")).hexdigest()[:16]


def token_claims(user: User) -> dict:
    return {"sub": user.username, "pwv": password_version(user)}


def create_access_token(config: Config, data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = utcnow() + (expires_delta or timedelta(minutes=config.access_token_expire_minutes))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, config.secret_key, algorithm=config.algorithm)
