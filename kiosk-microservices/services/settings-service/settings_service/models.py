from sqlalchemy import Column, String
from sqlalchemy.orm import declarative_base

from kiosk_common.outbox import make_outbox_model

Base = declarative_base()


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(String, default="")


Outbox = make_outbox_model(Base)

DEFAULTS = {
    "store_name": "My Kiosk Store",
    "receipt_footer": "Thank you for your purchase!",
    "currency": "EUR",
    "payment_due_date": "",
    "kiosk_idle_seconds": "90",
    "kiosk_barcode_scanning": "false",
    "backup_interval_hours": "24",
    "backup_keep": "7",
}
