"""Transactional outbox.

A service writes the events it must tell other services about (audit entries,
stock to give back after a failed call) into its own ``outbox`` table in the
same transaction as the change itself. A background relay then delivers them
over HTTP and marks them sent, retrying until it succeeds. The change and the
event are therefore never out of step, even if the other service is down.
"""

import json
import logging
import threading
from typing import Callable

from sqlalchemy import Column, DateTime, Integer, String, Text

from kiosk_common.db import Database
from kiosk_common.timeutil import utcnow

logger = logging.getLogger(__name__)

Sink = Callable[[list[dict]], None]


def make_outbox_model(base):
    """Create the ``Outbox`` model for a service's own declarative base."""

    class Outbox(base):
        __tablename__ = "outbox"

        id = Column(Integer, primary_key=True)
        topic = Column(String(64), nullable=False, index=True)
        payload = Column(Text, nullable=False)
        created_at = Column(DateTime, default=utcnow, nullable=False)
        attempts = Column(Integer, default=0, nullable=False)
        sent_at = Column(DateTime, nullable=True, index=True)
        last_error = Column(Text, default="")

    return Outbox


def publish(db, outbox_model, topic: str, payload: dict) -> None:
    """Queue an event in the caller's transaction (the caller commits)."""
    db.add(outbox_model(topic=topic, payload=json.dumps(payload, default=str)))


class OutboxRelay:
    """Daemon thread delivering queued events, topic by topic, oldest first."""

    def __init__(
        self,
        database: Database,
        outbox_model,
        sinks: dict[str, Sink],
        interval_seconds: float = 2.0,
        batch_size: int = 100,
    ):
        self.database = database
        self.model = outbox_model
        self.sinks = sinks
        self.interval = interval_seconds
        self.batch_size = batch_size
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, name="outbox-relay", daemon=True)

    def start(self) -> None:
        if not self.thread.is_alive():
            self.thread.start()

    def stop(self) -> None:
        self.stopped.set()

    def flush(self) -> int:
        """Deliver everything that is pending once; returns how many were sent."""
        delivered = 0
        for topic, sink in self.sinks.items():
            while True:
                sent = self._deliver_batch(topic, sink)
                delivered += sent
                if sent < self.batch_size:
                    break
        return delivered

    def pending(self) -> int:
        with self.database.session() as db:
            return db.query(self.model).filter(self.model.sent_at.is_(None)).count()

    def _deliver_batch(self, topic: str, sink: Sink) -> int:
        model = self.model
        with self.database.session() as db:
            query = (
                db.query(model)
                .filter(model.topic == topic, model.sent_at.is_(None))
                .order_by(model.id)
                .limit(self.batch_size)
            )
            if self.database.dialect == "postgresql":
                # Several replicas may relay at once; each takes its own rows.
                query = query.with_for_update(skip_locked=True)
            rows = query.all()
            if not rows:
                db.rollback()
                return 0
            events = [json.loads(row.payload) for row in rows]
            try:
                sink(events)
            except Exception as exc:  # delivery failed: keep the rows for the next run
                for row in rows:
                    row.attempts = (row.attempts or 0) + 1
                    row.last_error = str(exc)[:500]
                db.commit()
                logger.warning("outbox: %d %s event(s) not delivered: %s", len(rows), topic, exc)
                return 0
            now = utcnow()
            for row in rows:
                row.sent_at = now
                row.attempts = (row.attempts or 0) + 1
            db.commit()
            return len(rows)

    def _run(self) -> None:
        while not self.stopped.wait(self.interval):
            try:
                self.flush()
            except Exception:
                logger.exception("outbox relay failed")
