import unicodedata

from fastapi import HTTPException

MAX_USERNAME_LENGTH = 64


def normalize_username(username: str | None) -> str:
    """Canonical form used for storing and looking up customer usernames."""
    return unicodedata.normalize("NFC", (username or "").strip().lower())


def validate_new_username(name: str) -> None:
    """Rules for creating a customer at the public kiosk.

    Control and format characters (e.g. zero-width spaces) are rejected so a new
    name cannot look identical to an existing one in the admin panel.
    """
    if len(name) > MAX_USERNAME_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Username must be at most {MAX_USERNAME_LENGTH} characters",
        )
    if any(unicodedata.category(ch).startswith("C") for ch in name):
        raise HTTPException(
            status_code=422, detail="Username contains characters that are not allowed"
        )
