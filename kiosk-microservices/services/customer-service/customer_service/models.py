from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import declarative_base

from kiosk_common.outbox import make_outbox_model
from kiosk_common.timeutil import utcnow

Base = declarative_base()


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    # Optional kiosk PIN: Argon2id over a peppered HMAC (see pins.py), never the PIN.
    pin_hash = Column(String, nullable=True)
    pin_failed_attempts = Column(Integer, default=0)
    pin_locked_until = Column(DateTime, nullable=True)

    @property
    def has_pin(self):
        return bool(self.pin_hash)


Outbox = make_outbox_model(Base)
