"""
SQLAlchemy ORM models.
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class LegalDocumentORM(Base):
    __tablename__ = "legal_documents"
    __table_args__ = (UniqueConstraint("url", name="uq_document_url"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(100), nullable=False, index=True)
    title = Column(Text, nullable=False)
    url = Column(Text, nullable=False, unique=True)
    published_date = Column(DateTime, nullable=True, index=True)
    content = Column(Text, default="")
    doc_type = Column(String(50), default="unknown", index=True)
    reference = Column(String(200), default="")
    scraped_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    analysis = relationship("AnalysisORM", back_populates="document", uselist=False, cascade="all, delete-orphan")
    alerts_sent = relationship("AlertLogORM", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<LegalDocument id={self.id} source={self.source!r} title={self.title[:40]!r}>"


class AnalysisORM(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("legal_documents.id"), nullable=False, unique=True, index=True)
    summary = Column(Text, default="")
    key_points = Column(JSON, default=list)
    affected_sectors = Column(JSON, default=list)
    obligations = Column(JSON, default=list)
    deadlines = Column(JSON, default=list)
    impact_level = Column(String(20), default="faible", index=True)
    criticality_score = Column(Float, default=0.0)
    tags = Column(JSON, default=list)
    analyzed_at = Column(DateTime, default=datetime.utcnow)
    model_used = Column(String(50), default="")

    document = relationship("LegalDocumentORM", back_populates="analysis")

    def __repr__(self) -> str:
        return f"<Analysis id={self.id} doc_id={self.document_id} impact={self.impact_level!r}>"


class AlertLogORM(Base):
    __tablename__ = "alert_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("legal_documents.id"), nullable=False, index=True)
    channel = Column(String(50), nullable=False)   # "email" | "slack"
    recipient = Column(String(255), default="")
    sent_at = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=True)
    error_message = Column(Text, default="")

    document = relationship("LegalDocumentORM", back_populates="alerts_sent")
