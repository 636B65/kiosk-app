import json
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

import audit
import payment_info
from database import get_db
from models import Setting, User
from routers.products import ALLOWED_IMAGE_TYPES, MAX_IMAGE_BYTES, _detect_image_type, images_dir
from schemas import SettingIn
from security import get_current_user

router = APIRouter(prefix="/api/settings", tags=["settings"])


def get_all_settings(db: Session = Depends(get_db)):
    return {s.key: s.value for s in db.query(Setting).all()}


@router.get("")
def list_settings(db: Session = Depends(get_db)):
    return get_all_settings(db)


@router.post("/payment-qr")
def upload_payment_qr(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload the QR code image of a payment method (e.g. a Swish or bank QR).

    The file is only referenced once the admin saves `payment_methods` with its name.
    """
    ext = ALLOWED_IMAGE_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(status_code=400, detail="Only PNG, JPEG, WebP and GIF images are allowed")
    data = file.file.read(MAX_IMAGE_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large (max 5 MB)")
    actual_type = _detect_image_type(data)
    if actual_type is None or ALLOWED_IMAGE_TYPES.get(actual_type) != ext:
        raise HTTPException(status_code=400, detail="File content does not match the declared image type")
    name = f"pay-{uuid.uuid4().hex}{ext}"
    with open(os.path.join(images_dir(), name), "wb") as f:
        f.write(data)
    audit.record(db, user.username, "settings.payment_qr_upload", "setting", payment_info.METHODS_SETTING, name)
    db.commit()
    return {"image": name, "url": f"/api/images/{name}"}


@router.put("/{key}")
def upsert_setting(
    key: str,
    data: SettingIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    value = data.value
    # The kiosk shows these to every customer, so they are checked and stored canonically.
    if key == payment_info.METHODS_SETTING:
        try:
            value = payment_info.normalize_methods(value, images_dir())
        except payment_info.PaymentInfoError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    elif key == payment_info.INSTRUCTIONS_SETTING:
        try:
            value = payment_info.normalize_instructions(value)
        except payment_info.PaymentInfoError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    setting = db.get(Setting, key)
    previous = setting.value if setting else None
    if setting:
        setting.value = value
    else:
        setting = Setting(key=key, value=value)
        db.add(setting)
    if previous != value:
        if key == payment_info.METHODS_SETTING:
            methods = json.loads(value)
            details = f"{len(methods)} payment method(s), {sum(m['enabled'] for m in methods)} shown"
        else:
            details = audit.describe_changes({key: previous}, {key: value})
        audit.record(db, user.username, "settings.update", "setting", key, details)
    db.commit()
    if key == payment_info.METHODS_SETTING:
        # Remove QR images that are no longer used by any method.
        for name in payment_info.qr_images(previous) - payment_info.qr_images(value):
            path = os.path.join(images_dir(), name)
            if os.path.isfile(path):
                os.remove(path)
    return {"key": key, "value": setting.value}
