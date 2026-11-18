"""Fuzz parsing of the store-wide payment due date setting."""

import sys

import atheris

with atheris.instrument_imports():
    import _paths  # noqa: F401
    from due_dates import compute_due_time, parse_due_date


def TestOneInput(data: bytes) -> None:
    value = atheris.FuzzedDataProvider(data).ConsumeUnicodeNoSurrogates(64)
    parsed = parse_due_date(value)
    due = compute_due_time(parsed)
    assert (parsed is None) == (due is None)
    if due is not None:
        assert due.date() == parsed and (due.hour, due.minute, due.second) == (23, 59, 59)


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
