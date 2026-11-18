"""Fuzz the public kiosk inputs: customer usernames and PINs."""

import sys

import atheris

with atheris.instrument_imports():
    import _paths  # noqa: F401
    from fastapi import HTTPException

    import pins
    from routers.customers import MAX_USERNAME_LENGTH, normalize_username, validate_new_username


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    name = normalize_username(fdp.ConsumeUnicodeNoSurrogates(256))
    assert normalize_username(name) == name
    try:
        validate_new_username(name)
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        assert len(name) <= MAX_USERNAME_LENGTH
    pin = fdp.ConsumeUnicodeNoSurrogates(16)
    if pins.is_valid_pin(pin):
        assert pin.isascii() and pin.isdigit() and 4 <= len(pin) <= 8


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
