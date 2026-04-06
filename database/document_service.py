"""
Shared service for inserting documents manually (used by CLI and dashboard).
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import LegalDocumentORM
from .db_manager import DBManager

if TYPE_CHECKING:
    from analyzer.claude_analyzer import AnalysisResult


def insert_document(
    title: str,
    url: str,
    source: str,
    doc_type: str,
    content: str,
    reference: str,
    published_date: datetime | None,
    db_url: str = "",
    # optional manual analysis
    summary: str = "",
    impact_level: str = "faible",
    criticality_score: float = 0.0,
    key_points: list[str] | None = None,
    affected_sectors: list[str] | None = None,
    obligations: list[str] | None = None,
    deadlines: list[str] | None = None,
    tags: list[str] | None = None,
    analyze_with_claude: bool = False,
) -> tuple[bool, str]:
    """
    Insert a document into the database.
    Returns (success: bool, message: str).
    """
    from scrapers.base_scraper import LegalDocument
    from analyzer.criticality_scorer import CriticalityScorer
    from analyzer.claude_analyzer import AnalysisResult

    db_url = db_url or os.getenv("DATABASE_URL", "sqlite:///veille_juridique.db")
    db = DBManager(db_url)

    # Deduplicate by URL
    if url:
        with Session(db.engine) as s:
            existing = s.execute(
                select(LegalDocumentORM).where(LegalDocumentORM.url == url)
            ).scalar_one_or_none()
        if existing:
            return False, f"Un document avec cette URL existe déjà (id={existing.id})."

    doc = LegalDocument(
        source=source,
        title=title,
        url=url or f"manuel://{datetime.utcnow().isoformat()}",
        published_date=published_date,
        content=content,
        doc_type=doc_type,
        reference=reference,
    )

    orm_doc = db.upsert_document(doc)
    scorer = CriticalityScorer()
    score_result = scorer.score(doc)
    final_score = criticality_score or float(score_result.score)

    if analyze_with_claude and os.getenv("ANTHROPIC_API_KEY"):
        from analyzer.claude_analyzer import ClaudeAnalyzer
        analyzer = ClaudeAnalyzer()
        result = analyzer.analyze(doc)
        db.save_analysis(orm_doc.id, result, final_score, analyzer.model)
        return True, f"Document ajouté et analysé par Claude (id={orm_doc.id}, impact={result.impact_level})."

    result = AnalysisResult(
        summary=summary,
        impact_level=impact_level or score_result.level,
        key_points=key_points or [],
        affected_sectors=affected_sectors or [],
        obligations=obligations or [],
        deadlines=deadlines or [],
        tags=tags or [],
    )
    db.save_analysis(orm_doc.id, result, final_score, "manuel")
    return True, f"Document enregistré (id={orm_doc.id}, score={int(final_score)}/100)."
