from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import declarative_base

from kiosk_common.timeutil import utcnow

Base = declarative_base()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=utcnow, index=True)
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False, index=True)
    entity = Column(String, default="")
    entity_id = Column(String, default="")
    details = Column(Text, default="")
