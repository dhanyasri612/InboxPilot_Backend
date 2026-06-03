from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from database import Base

CAREER_CATEGORIES = {"Job", "Internship", "Interview", "Networking", "College"}


class Email(Base):
    """Maps to the existing Supabase `emails` table."""

    __tablename__ = "emails"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user_email = Column(Text, nullable=False, index=True)
    gmail_id = Column(Text, nullable=False, index=True)
    subject = Column(Text, default="")
    sender = Column(Text, default="")
    body = Column(Text, default="")
    company = Column("compnay", Text, default="Unknown")
    category = Column(Text, default="Other", index=True)
    subcategory = Column(Text, default="")
    priority = Column(BigInteger, default=20)
    deadline = Column(Text, nullable=True)
    summary = Column(Text, default="")
    is_deleted = Column(Boolean, default=False)
    confidence = Column(BigInteger, default=0)
    deadline_detected = Column(Boolean, default=False)
    career_related = Column(Boolean, default=False)
    ai_category = Column(Text, default="Other")
    ai_confidence = Column(BigInteger, default=0)
    ai_reason = Column(Text, default="")
    validation_result = Column(JSONB, default=dict)
    internal_date = Column(BigInteger, nullable=True, index=True)
    application_status = Column(Text, default="Discovered")

    def to_api_dict(self):
        internal_date = self.internal_date
        return {
            "id": self.gmail_id,
            "subject": self.subject or "",
            "sender": self.sender or "",
            "company": self.company or "Unknown",
            "category": self.category or "Other",
            "subcategory": self.subcategory or "",
            "confidence": int(self.confidence or 0),
            "priority": int(self.priority or 20),
            "deadline": self.deadline,
            "deadlineDetected": bool(self.deadline_detected or self.deadline),
            "career_related": bool(self.career_related),
            "ai_category": self.ai_category or "Other",
            "ai_confidence": int(self.ai_confidence or 0),
            "ai_reason": self.ai_reason or "",
            "validation_result": self.validation_result or {},
            "summary": self.summary or "",
            "body": self.body or "",
            "internalDate": str(internal_date) if internal_date is not None else None,
            "applicationStatus": self.application_status or "Discovered",
        }


class FetchMeta(Base):
    __tablename__ = "fetch_meta"

    user_email = Column(String(320), primary_key=True)
    range_key = Column(String(32), nullable=False)
    range_label = Column(String(128), default="")
    count = Column(Integer, default=0)
    email_address = Column(String(320), default="")
    fetched_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def to_api_dict(self):
        return {
            "range": self.range_key,
            "rangeLabel": self.range_label,
            "count": self.count,
            "emailAddress": self.email_address,
        }
