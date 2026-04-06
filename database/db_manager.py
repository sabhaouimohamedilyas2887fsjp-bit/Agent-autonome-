"""
Database manager – handles sessions, upserts, and common queries.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Generator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .models import AlertLogORM, AnalysisORM, Base, LegalDocumentORM

if TYPE_CHECKING:
    from scrapers.base_scraper import LegalDocument
    from analyzer.claude_analyzer import AnalysisResult

logger = logging.getLogger(__name__)


class DBManager:
    def __init__(self, db_url: str = "sqlite:///veille_juridique.db"):
        self.engine = create_engine(db_url, echo=False, future=True)
        self._SessionFactory = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        logger.info("Database ready: %s", db_url)

    # ------------------------------------------------------------------
    # Session context manager
    # ------------------------------------------------------------------

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        s = self._SessionFactory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    # ------------------------------------------------------------------
    # Document operations
    # ------------------------------------------------------------------

    def upsert_document(self, doc: LegalDocument) -> LegalDocumentORM:
        """Insert a new document or return the existing one (by URL)."""
        with self.session() as s:
            existing = s.execute(
                select(LegalDocumentORM).where(LegalDocumentORM.url == doc.url)
            ).scalar_one_or_none()

            if existing:
                return existing

            orm_doc = LegalDocumentORM(
                source=doc.source,
                title=doc.title,
                url=doc.url,
                published_date=doc.published_date,
                content=doc.content,
                doc_type=doc.doc_type,
                reference=doc.reference,
                scraped_at=doc.scraped_at,
            )
            s.add(orm_doc)
            s.flush()
            s.refresh(orm_doc)
            logger.debug("Inserted document id=%d: %s", orm_doc.id, orm_doc.title[:60])
            return orm_doc

    def save_analysis(
        self,
        document_id: int,
        result: AnalysisResult,
        criticality_score: float = 0.0,
        model_used: str = "",
    ) -> AnalysisORM:
        with self.session() as s:
            existing = s.execute(
                select(AnalysisORM).where(AnalysisORM.document_id == document_id)
            ).scalar_one_or_none()

            if existing:
                existing.summary = result.summary
                existing.key_points = result.key_points
                existing.affected_sectors = result.affected_sectors
                existing.obligations = result.obligations
                existing.deadlines = result.deadlines
                existing.impact_level = result.impact_level
                existing.criticality_score = criticality_score
                existing.tags = result.tags
                existing.analyzed_at = datetime.utcnow()
                existing.model_used = model_used
                s.flush()
                return existing

            analysis = AnalysisORM(
                document_id=document_id,
                summary=result.summary,
                key_points=result.key_points,
                affected_sectors=result.affected_sectors,
                obligations=result.obligations,
                deadlines=result.deadlines,
                impact_level=result.impact_level,
                criticality_score=criticality_score,
                tags=result.tags,
                model_used=model_used,
            )
            s.add(analysis)
            s.flush()
            s.refresh(analysis)
            return analysis

    def log_alert(
        self,
        document_id: int,
        channel: str,
        recipient: str = "",
        success: bool = True,
        error_message: str = "",
    ) -> None:
        with self.session() as s:
            log = AlertLogORM(
                document_id=document_id,
                channel=channel,
                recipient=recipient,
                success=success,
                error_message=error_message,
            )
            s.add(log)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_recent_documents(self, hours: int = 24, limit: int = 100) -> list[LegalDocumentORM]:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        with self.session() as s:
            rows = s.execute(
                select(LegalDocumentORM)
                .where(LegalDocumentORM.scraped_at >= cutoff)
                .order_by(LegalDocumentORM.scraped_at.desc())
                .limit(limit)
            ).scalars().all()
        return rows

    def get_high_impact_documents(self, min_score: float = 50.0) -> list[LegalDocumentORM]:
        with self.session() as s:
            rows = s.execute(
                select(LegalDocumentORM)
                .join(AnalysisORM)
                .where(AnalysisORM.criticality_score >= min_score)
                .order_by(AnalysisORM.criticality_score.desc())
            ).scalars().all()
        return rows

    def has_analysis(self, document_id: int) -> bool:
        with self.session() as s:
            row = s.execute(
                select(AnalysisORM).where(AnalysisORM.document_id == document_id)
            ).scalar_one_or_none()
        return row is not None

    def get_document_with_analysis(self, document_id: int) -> LegalDocumentORM | None:
        from sqlalchemy.orm import selectinload
        with self.session() as s:
            row = s.execute(
                select(LegalDocumentORM)
                .options(selectinload(LegalDocumentORM.analysis))
                .where(LegalDocumentORM.id == document_id)
            ).scalar_one_or_none()
        return row

    def delete_document(self, document_id: int) -> bool:
        """Delete a document and all related data (analysis, alert logs). Returns True if found."""
        with self.session() as s:
            doc = s.get(LegalDocumentORM, document_id)
            if doc is None:
                return False
            s.delete(doc)   # cascade handles analysis + alert_logs
        logger.info("Deleted document id=%d", document_id)
        return True

    def already_alerted(self, document_id: int, channel: str) -> bool:
        with self.session() as s:
            row = s.execute(
                select(AlertLogORM)
                .where(
                    AlertLogORM.document_id == document_id,
                    AlertLogORM.channel == channel,
                    AlertLogORM.success == True,  # noqa: E712
                )
            ).scalar_one_or_none()
        return row is not None


if __name__ == "__main__":
    import os
    db_url = os.getenv("DATABASE_URL", "sqlite:///veille_juridique.db")
    db = DBManager(db_url)
    with db.session() as s:
        from sqlalchemy import func, select
        doc_count = s.execute(select(func.count()).select_from(LegalDocumentORM)).scalar()
        analysis_count = s.execute(select(func.count()).select_from(AnalysisORM)).scalar()
        alert_count = s.execute(select(func.count()).select_from(AlertLogORM)).scalar()
    print(f"Database: {db_url}")
    print(f"  Documents : {doc_count}")
    print(f"  Analyses  : {analysis_count}")
    print(f"  Alerts    : {alert_count}")
