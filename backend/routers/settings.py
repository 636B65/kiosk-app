from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Setting
from schemas import SettingIn
from security import get_current_user

router = APIRouter(prefix="/api/settings", tags=["settings"])


def get_all_settings(db: Session = Depends(get_db)):
    return {s.key: s.value for s in db.query(Setting).all()}


@router.get("")
def list_settings(db: Session = Depends(get_db)):
    return get_all_settings(db)


@router.put("/{key}")
def upsert_setting(
    key: str,
    data: SettingIn,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    setting = db.get(Setting, key)
    if setting:
        setting.value = data.value
    else:
        setting = Setting(key=key, value=data.value)
        db.add(setting)
    db.commit()
    return {"key": key, "value": setting.value}
