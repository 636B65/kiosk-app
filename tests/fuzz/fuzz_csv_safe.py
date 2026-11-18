"""Fuzz CSV-injection protection of the report exports."""

import sys

import atheris

with atheris.instrument_imports():
    import _paths  # noqa: F401
    from routers.reports import csv_safe

FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def TestOneInput(data: bytes) -> None:
    text = atheris.FuzzedDataProvider(data).ConsumeUnicodeNoSurrogates(128)
    cell = csv_safe(text)
    assert not cell.lstrip().startswith(FORMULA_STARTS) or cell.startswith("'")
    assert cell.endswith(text)


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
