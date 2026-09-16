"""Unit tests for payment due-date calculations.

Run with:  python -m pytest backend/tests/test_due_dates.py -v
"""

import sys
from datetime import date, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from due_dates import compute_due_time, parse_due_date  # noqa: E402


def test_empty_or_missing_value_means_no_due_date():
    assert parse_due_date(None) is None
    assert parse_due_date("") is None
    assert parse_due_date("   ") is None


def test_parses_iso_date():
    assert parse_due_date("2026-10-15") == date(2026, 10, 15)


def test_invalid_value_ignored():
    assert parse_due_date("not-a-date") is None
    assert parse_due_date("15") is None  # day-of-month no longer valid
    assert parse_due_date("0") is None


def test_compute_due_time_is_end_of_day():
    assert compute_due_time(date(2026, 10, 15)) == datetime(2026, 10, 15, 23, 59, 59)


def test_compute_due_time_none_maps_to_none():
    assert compute_due_time(None) is None
