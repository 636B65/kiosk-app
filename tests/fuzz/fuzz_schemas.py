"""Fuzz request validation: arbitrary order, product and user payloads must be
accepted or rejected with a validation error, never crash."""

import sys

import atheris

with atheris.instrument_imports():
    import _paths  # noqa: F401
    from pydantic import ValidationError

    from schemas import OrderCreate, ProductCreate, ProductUpdate, UserCreate, normalize_barcodes


def _value(fdp, depth=0):
    kind = fdp.ConsumeIntInRange(0, 6 if depth < 2 else 4)
    if kind == 0:
        return fdp.ConsumeUnicodeNoSurrogates(40)
    if kind == 1:
        return fdp.ConsumeIntInRange(-(10**9), 10**9)
    if kind == 2:
        return fdp.ConsumeRegularFloat()
    if kind == 3:
        return fdp.ConsumeBool()
    if kind == 4:
        return None
    if kind == 5:
        return [_value(fdp, depth + 1) for _ in range(fdp.ConsumeIntInRange(0, 4))]
    return _payload(fdp, depth + 1)


KEYS = ("customer_username", "items", "notes", "customer_pin", "product_id", "quantity", "name",
        "price", "special_price", "is_weekly_special", "special_starts_on", "special_ends_on",
        "cost_price", "stock", "expected_stock", "low_stock_threshold", "barcodes", "username",
        "password", "full_name")


def _payload(fdp, depth=0):
    return {KEYS[fdp.ConsumeIntInRange(0, len(KEYS) - 1)]: _value(fdp, depth) for _ in range(fdp.ConsumeIntInRange(0, 8))}


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    for model in (OrderCreate, ProductCreate, ProductUpdate, UserCreate):
        try:
            model.model_validate(_payload(fdp))
        except ValidationError:
            pass
    try:
        codes = normalize_barcodes([fdp.ConsumeUnicodeNoSurrogates(140) for _ in range(fdp.ConsumeIntInRange(0, 55))])
    except ValueError:
        return
    assert codes is not None and len(codes) == len(set(codes))


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
