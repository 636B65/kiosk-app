from datetime import datetime

from order_service.due_dates import due_time_from_settings


def test_due_time_is_end_of_configured_day():
    assert due_time_from_settings({"payment_due_date": "2026-03-01"}) == datetime(2026, 3, 1, 23, 59, 59)


def test_missing_or_invalid_due_date_is_none():
    assert due_time_from_settings({}) is None
    assert due_time_from_settings({"payment_due_date": ""}) is None
    assert due_time_from_settings({"payment_due_date": "not-a-date"}) is None
