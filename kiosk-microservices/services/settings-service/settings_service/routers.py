from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from kiosk_common import audit
from kiosk_common.auth import Principal, get_current_user
from kiosk_common.db import get_db
from settings_service.models import Outbox, Setting

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingIn(BaseModel):
    key: str
    value: str


@router.get("")
def list_settings(db: Session = Depends(get_db)):
    return {s.key: s.value for s in db.query(Setting).all()}


@router.put("/{key}")
def upsert_setting(
    key: str,
    data: SettingIn,
    db: Session = Depends(get_db),
    user: Principal = Depends(get_current_user),
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
            db, Outbox, user.username, "settings.update", "setting", key,
            audit.describe_changes({key: previous}, {key: data.value}),
        )
    db.commit()
    return {"key": key, "value": setting.value}
