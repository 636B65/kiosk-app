"""How customers can pay, as the admin wants it shown on the kiosk's "Pay" screen.

The setting `payment_methods` holds a JSON list of methods, `pay_instructions` a free
text above them. Both are public (the kiosk shows them to anyone), so the admin's input
is validated and stored in one canonical form, and QR codes are uploaded images served from
the product image folder (the CSP allows `img-src 'self'` only; the kiosk runs air-gapped).
"""

import json
import os
import re
import unicodedata

METHODS_SETTING = "payment_methods"
INSTRUCTIONS_SETTING = "pay_instructions"

METHOD_TYPES = ("bank", "phone", "qr", "link", "text")
MAX_METHODS = 10
MAX_LABEL = 40
MAX_VALUE = 300
MAX_NOTE = 300
MAX_INSTRUCTIONS = 500

# Uploaded QR codes: pay-<32 hex>.<ext> (written by the upload endpoint, nothing else matches).
QR_NAME_RE = re.compile(r"^pay-[0-9a-f]{32}\.(png|jpg|webp|gif)$")
_LINK_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


class PaymentInfoError(ValueError):
    pass


def _text(value, field: str, limit: int, multiline: bool = False) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise PaymentInfoError(f"{field} must be text")
    value = value.strip()
    if len(value) > limit:
        raise PaymentInfoError(f"{field} must be at most {limit} characters")
    for ch in value:
        if multiline and ch in "\n\r\t":
            continue
        if unicodedata.category(ch).startswith("C"):
            raise PaymentInfoError(f"{field} contains characters that are not allowed")
    return value


def normalize_methods(raw: str, images_dir: str) -> str:
    """Validate the JSON list and return it in canonical form; PaymentInfoError if wrong."""
    if not raw or not raw.strip():
        return "[]"
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise PaymentInfoError("payment_methods must be valid JSON") from exc
    if not isinstance(data, list):
        raise PaymentInfoError("payment_methods must be a list")
    if len(data) > MAX_METHODS:
        raise PaymentInfoError(f"At most {MAX_METHODS} payment methods are allowed")
    methods = []
    for index, item in enumerate(data, 1):
        if not isinstance(item, dict):
            raise PaymentInfoError(f"Payment method {index} must be an object")
        kind = item.get("type")
        if kind not in METHOD_TYPES:
            raise PaymentInfoError(
                f"Payment method {index}: type must be one of {', '.join(METHOD_TYPES)}"
            )
        label = _text(item.get("label"), "label", MAX_LABEL)
        value = _text(item.get("value"), "value", MAX_VALUE, multiline=(kind == "text"))
        note = _text(item.get("note"), "note", MAX_NOTE, multiline=True)
        image = _text(item.get("image"), "image", 80)
        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise PaymentInfoError(f"Payment method {index}: enabled must be true or false")
        if kind == "qr":
            if not QR_NAME_RE.match(image):
                raise PaymentInfoError(f"Payment method {index}: upload a QR code image first")
            if not os.path.isfile(os.path.join(images_dir, image)):
                raise PaymentInfoError(f"Payment method {index}: the QR code image is missing")
        else:
            image = ""
            if not value:
                raise PaymentInfoError(f"Payment method {index}: a value is required")
        if kind == "link" and not _LINK_RE.match(value):
            raise PaymentInfoError(f"Payment method {index}: a link must start with http:// or https://")
        methods.append(
            {"type": kind, "label": label, "value": value, "note": note, "image": image, "enabled": enabled}
        )
    return json.dumps(methods, ensure_ascii=False, separators=(",", ":"))


def normalize_instructions(raw: str) -> str:
    return _text(raw, "pay_instructions", MAX_INSTRUCTIONS, multiline=True)


def qr_images(raw: str | None) -> set[str]:
    """Uploaded QR files a stored payment_methods value refers to (tolerates anything)."""
    try:
        data = json.loads(raw or "[]")
    except ValueError:
        return set()
    if not isinstance(data, list):
        return set()
    return {
        item["image"]
        for item in data
        if isinstance(item, dict) and isinstance(item.get("image"), str) and QR_NAME_RE.match(item["image"])
    }
