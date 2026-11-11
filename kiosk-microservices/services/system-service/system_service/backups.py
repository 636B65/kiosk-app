"""Backups of every service database into one ``kiosk-YYYYmmdd-HHMMSS.tar.gz``.

Postgres databases are dumped with ``pg_dump --format=custom`` (restore with
``pg_restore``); SQLite files (local runs) with ``VACUUM INTO``. The archive
is written to the backup volume; the newest ``backup_keep`` archives are kept
and a scheduler thread takes one every ``backup_interval_hours``.
"""

import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
from datetime import datetime, timezone

from sqlalchemy import create_engine

from kiosk_common.http import ServiceClient
from kiosk_common.timeutil import utcnow

logger = logging.getLogger(__name__)

INTERVAL_SETTING = "backup_interval_hours"
KEEP_SETTING = "backup_keep"
DEFAULT_INTERVAL_HOURS = 24
DEFAULT_KEEP = 7
MAX_KEEP = 365
CHECK_INTERVAL_SECONDS = 600

BACKUP_NAME_RE = re.compile(r"^kiosk-(\d{8}-\d{6})(?:-(\d+))?\.tar\.gz$")


def _int_setting(settings: dict, key: str, default: int, low: int, high: int) -> int:
    try:
        raw = settings.get(key, "")
        value = int(raw) if raw not in ("", None) else default
    except (TypeError, ValueError):
        value = default
    return max(low, min(value, high))


def interval_hours(settings: dict) -> int:
    return _int_setting(settings, INTERVAL_SETTING, DEFAULT_INTERVAL_HOURS, 0, 24 * 365)


def keep_count(settings: dict) -> int:
    return _int_setting(settings, KEEP_SETTING, DEFAULT_KEEP, 1, MAX_KEEP)


def supported(databases: dict[str, str]) -> bool:
    if not databases:
        return False
    for url in databases.values():
        if url.startswith("postgresql") and shutil.which("pg_dump") is None:
            return False
        if not url.startswith(("postgresql", "sqlite")):
            return False
    return True


def _created_at(name: str, path: str) -> datetime:
    match = BACKUP_NAME_RE.match(name)
    if match:
        return datetime.strptime(match.group(1), "%Y%m%d-%H%M%S")
    return datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).replace(tzinfo=None)


def _sort_key(item: dict) -> tuple:
    match = BACKUP_NAME_RE.match(item["name"])
    sequence = int(match.group(2) or 0) if match else 0
    return item["created_at"], sequence, item["name"]


def list_backups(directory: str) -> list[dict]:
    if not os.path.isdir(directory):
        return []
    items = []
    for name in os.listdir(directory):
        path = os.path.join(directory, name)
        if BACKUP_NAME_RE.match(name) and os.path.isfile(path):
            items.append({"name": name, "size_bytes": os.path.getsize(path), "created_at": _created_at(name, path)})
    items.sort(key=_sort_key, reverse=True)
    return items


def backup_path(directory: str, name: str) -> str | None:
    """Absolute path of an existing backup; built only from names found on disk."""
    for item in list_backups(directory):
        if item["name"] == name:
            return os.path.join(directory, item["name"])
    return None


def prune(directory: str, keep: int) -> list[str]:
    removed = []
    for item in list_backups(directory)[keep:]:
        os.remove(os.path.join(directory, item["name"]))
        removed.append(item["name"])
    return removed


def _dump_one(name: str, url: str, into: str) -> str:
    if url.startswith("postgresql"):
        target = os.path.join(into, f"{name}.dump")
        # pg_dump understands plain postgresql:// URIs, not SQLAlchemy driver suffixes.
        dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", url)
        subprocess.run(
            ["pg_dump", "--format=custom", "--no-owner", f"--dbname={dsn}", "-f", target],
            check=True, capture_output=True, text=True, timeout=600,
        )
        return target
    if url.startswith("sqlite"):
        target = os.path.join(into, f"{name}.db")
        engine = create_engine(url)
        try:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.exec_driver_sql("VACUUM INTO ?", (target,))
        finally:
            engine.dispose()
        return target
    raise RuntimeError(f"Unsupported database URL for {name}")


def create_backup(directory: str, databases: dict[str, str], keep: int) -> dict:
    if not supported(databases):
        raise RuntimeError("Backups need pg_dump (Postgres) or SQLite databases")
    os.makedirs(directory, exist_ok=True)
    stamp = utcnow().strftime("%Y%m%d-%H%M%S")
    name = f"kiosk-{stamp}.tar.gz"
    suffix = 1
    while os.path.exists(os.path.join(directory, name)):
        name = f"kiosk-{stamp}-{suffix}.tar.gz"
        suffix += 1
    path = os.path.join(directory, name)
    with tempfile.TemporaryDirectory(dir=directory) as workdir:
        dumps = [_dump_one(db_name, url, workdir) for db_name, url in databases.items()]
        partial = path + ".partial"
        with tarfile.open(partial, "w:gz") as archive:
            for dump in dumps:
                archive.add(dump, arcname=os.path.basename(dump))
        os.replace(partial, path)
    removed = prune(directory, keep)
    logger.info("Backup written to %s (pruned %d old)", path, len(removed))
    return {
        "name": name,
        "size_bytes": os.path.getsize(path),
        "created_at": _created_at(name, path),
        "pruned": removed,
        "databases": sorted(databases),
    }


def backup_due(directory: str, hours: int) -> bool:
    if hours <= 0:
        return False
    items = list_backups(directory)
    if not items:
        return True
    return (utcnow() - items[0]["created_at"]).total_seconds() >= hours * 3600


class BackupScheduler:
    """Daemon thread that takes a backup whenever one is due (first check after 10 min)."""

    def __init__(self, directory: str, databases: dict[str, str], settings_client: ServiceClient):
        self.directory = directory
        self.databases = databases
        self.settings_client = settings_client
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, name="backup-scheduler", daemon=True)

    def start(self) -> None:
        if supported(self.databases):
            self.thread.start()

    def stop(self) -> None:
        self.stopped.set()

    def run_once(self) -> dict | None:
        settings = self.settings_client.get("/api/settings") or {}
        if backup_due(self.directory, interval_hours(settings)):
            return create_backup(self.directory, self.databases, keep_count(settings))
        return None

    def _run(self) -> None:
        while not self.stopped.wait(CHECK_INTERVAL_SECONDS):
            try:
                self.run_once()
            except Exception:
                logger.exception("Scheduled backup failed")
