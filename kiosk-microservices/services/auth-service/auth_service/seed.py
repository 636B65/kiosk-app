import secrets

from sqlalchemy.orm import Session

from auth_service.models import User
from auth_service.security import get_password_hash


def initial_admin_password(configured: str) -> str:
    """ADMIN_PASSWORD when usable (>= 8 chars), else a random one printed once."""
    if len(configured) < 8:
        generated = secrets.token_urlsafe(18)
        if configured:
            print(
                "[seed] ADMIN_PASSWORD is too short (< 8 chars) - ignoring it and "
                "generating a random password for the 'admin' account instead.",
                flush=True,
            )
        print(
            "[seed] No usable ADMIN_PASSWORD set - generated a random password for "
            f"the 'admin' account (save it now): {generated}",
            flush=True,
        )
        return generated
    return configured


def seed(db: Session, admin_password: str) -> None:
    if not db.query(User).filter(User.username == "admin").first():
        db.add(
            User(
                username="admin",
                password_hash=get_password_hash(initial_admin_password(admin_password)),
                full_name="Store Administrator",
            )
        )
        db.commit()
