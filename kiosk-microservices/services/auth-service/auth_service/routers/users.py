from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth_service.models import Outbox, User
from auth_service.schemas import UserCreate, UserOut, UserUpdate
from auth_service.security import get_password_hash
from kiosk_common import audit
from kiosk_common.auth import Principal, get_current_user
from kiosk_common.db import get_db

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), _: Principal = Depends(get_current_user)):
    return db.query(User).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current: Principal = Depends(get_current_user),
):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    user = User(
        username=data.username,
        password_hash=get_password_hash(data.password),
        full_name=data.full_name,
    )
    db.add(user)
    audit.record(db, Outbox, current.username, "user.create", "user", data.username)
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current: Principal = Depends(get_current_user),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    changed = [
        field
        for field, value in (
            ("password", data.password),
            ("full_name", data.full_name),
            ("is_active", data.is_active),
        )
        if value is not None and (field == "password" or getattr(user, field) != value)
    ]
    if changed:
        # Never log the password itself, only that it changed.
        audit.record(
            db, Outbox, current.username, "user.update", "user", user.username,
            "changed: " + ", ".join(changed),
        )
    if data.password:
        user.password_hash = get_password_hash(data.password)
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.is_active is not None:
        user.is_active = data.is_active
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: Principal = Depends(get_current_user),
):
    if user_id == current.user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    audit.record(db, Outbox, current.username, "user.delete", "user", user.username)
    db.delete(user)
    db.commit()
