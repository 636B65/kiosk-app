from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from auth_service.models import User
from auth_service.schemas import IntrospectIn, IntrospectOut
from auth_service.security import password_version
from kiosk_common.db import get_db
from kiosk_common.internal import require_internal

router = APIRouter(prefix="/internal/auth", tags=["internal"], dependencies=[Depends(require_internal)])


def resolve_user(db: Session, payload: dict) -> User | None:
    """The user a token payload belongs to, if the account is still valid."""
    username = payload.get("sub")
    if not isinstance(username, str):
        return None
    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active or payload.get("pwv") != password_version(user):
        return None
    return user


@router.post("/introspect", response_model=IntrospectOut)
def introspect(data: IntrospectIn, request: Request, db: Session = Depends(get_db)):
    """Other services ask here whether a token's account is still active."""
    payload = request.app.state.auth.decode(data.token)
    user = resolve_user(db, payload) if payload else None
    if user is None:
        return IntrospectOut(active=False)
    return IntrospectOut(active=True, username=user.username, user_id=user.id, full_name=user.full_name or "")


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    return {"users": db.query(User).count()}
