from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import audit
from database import get_db
from models import Setting, User
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
    user: User = Depends(get_current_user),
):
    setting = db.get(Setting, key)
    previous = setting.value if setting else None
    if setting:
        setting.value = data.value
    else:
        setting = Setting(key=key, value=data.value)
        db.add(setting)
    if previous != data.value:
        audit.record(
            db, user.username, "settings.update", "setting", key,
            audit.describe_changes({key: previous}, {key: data.value}),
        )
    db.commit()
    return {"key": key, "value": setting.value}
