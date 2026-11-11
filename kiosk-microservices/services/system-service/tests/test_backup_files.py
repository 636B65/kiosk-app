import os

from system_service import backups


def test_backup_names_and_pruning(tmp_path):
    for name in ("kiosk-20260101-000000.tar.gz", "kiosk-20260102-000000.tar.gz", "kiosk-20260102-000000-1.tar.gz", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    items = backups.list_backups(str(tmp_path))
    assert [i["name"] for i in items] == [
        "kiosk-20260102-000000-1.tar.gz", "kiosk-20260102-000000.tar.gz", "kiosk-20260101-000000.tar.gz",
    ]
    assert backups.backup_path(str(tmp_path), "../notes.txt") is None
    assert backups.prune(str(tmp_path), keep=1) == ["kiosk-20260102-000000.tar.gz", "kiosk-20260101-000000.tar.gz"]
    assert os.path.exists(tmp_path / "notes.txt")


def test_settings_bounds():
    assert backups.interval_hours({"backup_interval_hours": "0"}) == 0
    assert backups.interval_hours({"backup_interval_hours": "oops"}) == 24
    assert backups.keep_count({"backup_keep": "0"}) == 1
    assert backups.keep_count({"backup_keep": "9999"}) == backups.MAX_KEEP


def test_supported_requires_known_urls():
    assert backups.supported({}) is False
    assert backups.supported({"a": "mysql://x"}) is False
    assert backups.supported({"a": "sqlite:///x.db"}) is True
