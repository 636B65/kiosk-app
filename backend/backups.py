"""SQLite database backups.

Backups are consistent snapshots made with ``VACUUM INTO`` (safe while the
app is serving requests) and stored next to the database in ``backups/``.
A background thread takes one every ``backup_interval_hours`` (setting,
default 24, ``0`` disables automatic backups) and keeps the newest
``backup_keep`` files (setting, default 7).
"""

import logging
import os
import re
import threading
from datetime import datetime, timezone

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from models import Setting
from timeutil import utcnow

logger = logging.getLogger(__name__)

INTERVAL_SETTING = "backup_interval_hours"
KEEP_SETTING = "backup_keep"
DEFAULT_INTERVAL_HOURS = 24
DEFAULT_KEEP = 7
MAX_KEEP = 365
# How often the scheduler wakes up to check whether a backup is due.
CHECK_INTERVAL_SECONDS = 600

BACKUP_NAME_RE = re.compile(r"^kiosk-(\d{8}-\d{6})(?:-(\d+))?\.db$")


def supported(engine: Engine) -> bool:
    database = engine.url.database
    return engine.dialect.name == "sqlite" and bool(database) and database != ":memory:"


def backup_dir(engine: Engine) -> str:
    database = os.path.abspath(engine.url.database or "")
    return os.path.join(os.path.dirname(database), "backups")


def _int_setting(db: Session, key: str, default: int, low: int, high: int) -> int:
    setting = db.get(Setting, key)
    try:
        value = int(setting.value) if setting and setting.value != "" else default
    except ValueError:
        value = default
    return max(low, min(value, high))


def interval_hours(db: Session) -> int:
    return _int_setting(db, INTERVAL_SETTING, DEFAULT_INTERVAL_HOURS, 0, 24 * 365)


def keep_count(db: Session) -> int:
    return _int_setting(db, KEEP_SETTING, DEFAULT_KEEP, 1, MAX_KEEP)


def _created_at(name: str, path: str) -> datetime:
    match = BACKUP_NAME_RE.match(name)
    if match:
        return datetime.strptime(match.group(1), "%Y%m%d-%H%M%S")
    return datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).replace(tzinfo=None)


def _sort_key(item: dict) -> tuple:
    # Same-second backups get "-1", "-2", ... suffixes; order those numerically.
    match = BACKUP_NAME_RE.match(item["name"])
    sequence = int(match.group(2) or 0) if match else 0
    return item["created_at"], sequence, item["name"]


def list_backups(engine: Engine) -> list[dict]:
    """Backups, newest first."""
    directory = backup_dir(engine)
    if not supported(engine) or not os.path.isdir(directory):
        return []
    items = []
    for name in os.listdir(directory):
        path = os.path.join(directory, name)
        if BACKUP_NAME_RE.match(name) and os.path.isfile(path):
            items.append(
                {
                    "name": name,
                    "size_bytes": os.path.getsize(path),
                    "created_at": _created_at(name, path),
                }
            )
    items.sort(key=_sort_key, reverse=True)
    return items


def backup_path(engine: Engine, name: str) -> str | None:
    """Absolute path of an existing backup, or None for unknown/unsafe names.

    The path is built only from names found on disk, never from the request.
    """
    for item in list_backups(engine):
        if item["name"] == name:
            return os.path.join(backup_dir(engine), item["name"])
    return None


def prune(engine: Engine, keep: int) -> list[str]:
    removed = []
    for item in list_backups(engine)[keep:]:
        os.remove(os.path.join(backup_dir(engine), item["name"]))
        removed.append(item["name"])
    return removed


def create_backup(engine: Engine, keep: int) -> dict:
    if not supported(engine):
        raise RuntimeError("Backups are only available for the SQLite database")
    directory = backup_dir(engine)
    os.makedirs(directory, exist_ok=True)
    stamp = utcnow().strftime("%Y%m%d-%H%M%S")
    name = f"kiosk-{stamp}.db"
    suffix = 1
    while os.path.exists(os.path.join(directory, name)):
        name = f"kiosk-{stamp}-{suffix}.db"
        suffix += 1
    path = os.path.join(directory, name)
    # VACUUM cannot run inside a transaction.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql("VACUUM INTO ?", (path,))
    removed = prune(engine, keep)
    logger.info("Database backup written to %s (pruned %d old)", path, len(removed))
    return {
        "name": name,
        "size_bytes": os.path.getsize(path),
        "created_at": _created_at(name, path),
        "pruned": removed,
    }


def backup_due(engine: Engine, hours: int) -> bool:
    if hours <= 0 or not supported(engine):
        return False
    backups = list_backups(engine)
    if not backups:
        return True
    age = utcnow() - backups[0]["created_at"]
    return age.total_seconds() >= hours * 3600


class BackupScheduler:
    """Daemon thread that takes a backup whenever one is due."""

    def __init__(self, engine: Engine, session_factory):
        self.engine = engine
        self.session_factory = session_factory
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, name="backup-scheduler", daemon=True)

    def start(self) -> None:
        if supported(self.engine):
            self.thread.start()

    def stop(self) -> None:
        self.stopped.set()

    def run_once(self) -> dict | None:
        db = self.session_factory()
        try:
            hours, keep = interval_hours(db), keep_count(db)
        finally:
            db.close()
        if backup_due(self.engine, hours):
            return create_backup(self.engine, keep)
        return None

    def _run(self) -> None:
        # The first check also waits, so short-lived processes (tests, one-off
        # commands) never write backups on their own.
        while not self.stopped.wait(CHECK_INTERVAL_SECONDS):
            try:
                self.run_once()
            except Exception:
                logger.exception("Scheduled database backup failed")
