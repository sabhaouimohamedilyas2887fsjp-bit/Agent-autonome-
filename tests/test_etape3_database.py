"""
ÉTAPE 3 — Test de la couche Base de Données (DBManager)
Utilise une base SQLite en mémoire pour ne pas polluer la base de production.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from datetime import datetime
from scrapers.base_scraper import LegalDocument
from analyzer.claude_analyzer import AnalysisResult
from database.db_manager import DBManager


@pytest.fixture
def db():
    """Base SQLite en mémoire, isolée par test."""
    manager = DBManager("sqlite:///:memory:")
    return manager


def _make_doc(n=1):
    return LegalDocument(
        source="Bulletin Officiel",
        title=f"Dahir de test n°{n}",
        url=f"https://bo.ma/test-{n}",
        doc_type="dahir",
        content="Protection des données personnelles au Maroc.",
        reference=f"n°1-24-0{n}",
        published_date=datetime(2024, 1, n),
    )


def _make_analysis():
    return AnalysisResult(
        summary="Ce dahir établit le cadre légal de protection des données personnelles.",
        key_points=["Obligation de consentement", "Droit d'accès garanti"],
        affected_sectors=["Numérique", "Finance"],
        obligations=["Déclaration à la CNDP", "Nomination d'un DPO"],
        deadlines=["6 mois après publication"],
        impact_level="élevé",
        tags=["données personnelles", "CNDP", "loi 09-08"],
    )


# ─── Test 1 : Insertion d'un document ───────────────────────────────────────
def test_insert_document(db):
    doc = _make_doc(1)
    orm = db.upsert_document(doc)
    assert orm.id is not None
    assert orm.source == "Bulletin Officiel"
    assert orm.title == doc.title
    print(f"✅ Test 1 : Insertion document → id={orm.id} — OK")


# ─── Test 2 : Déduplication par URL ─────────────────────────────────────────
def test_deduplication(db):
    doc = _make_doc(1)
    orm1 = db.upsert_document(doc)
    orm2 = db.upsert_document(doc)  # même URL
    assert orm1.id == orm2.id
    print(f"✅ Test 2 : Déduplication → même id={orm1.id} — OK")


# ─── Test 3 : Sauvegarde d'une analyse ──────────────────────────────────────
def test_save_analysis(db):
    doc = _make_doc(1)
    orm_doc = db.upsert_document(doc)
    analysis = _make_analysis()
    orm_an = db.save_analysis(
        document_id=orm_doc.id,
        result=analysis,
        criticality_score=72.0,
        model_used="claude-sonnet-4-6",
    )
    assert orm_an.impact_level == "élevé"
    assert orm_an.criticality_score == 72.0
    assert "Finance" in orm_an.affected_sectors
    print(f"✅ Test 3 : Sauvegarde analyse → impact={orm_an.impact_level}, score={orm_an.criticality_score} — OK")


# ─── Test 4 : has_analysis() ────────────────────────────────────────────────
def test_has_analysis(db):
    doc = _make_doc(2)
    orm_doc = db.upsert_document(doc)
    assert not db.has_analysis(orm_doc.id)
    db.save_analysis(orm_doc.id, _make_analysis(), criticality_score=50.0)
    assert db.has_analysis(orm_doc.id)
    print("✅ Test 4 : has_analysis() — OK")


# ─── Test 5 : Suppression d'un document ─────────────────────────────────────
def test_delete_document(db):
    doc = _make_doc(3)
    orm_doc = db.upsert_document(doc)
    doc_id = orm_doc.id
    result = db.delete_document(doc_id)
    assert result is True
    result2 = db.delete_document(doc_id)
    assert result2 is False  # déjà supprimé
    print("✅ Test 5 : Suppression document — OK")


# ─── Test 6 : get_recent_documents() ────────────────────────────────────────
def test_get_recent_documents(db):
    for i in range(1, 4):
        db.upsert_document(_make_doc(i))
    docs = db.get_recent_documents(hours=24)
    assert len(docs) == 3
    print(f"✅ Test 6 : get_recent_documents() → {len(docs)} documents — OK")


# ─── Test 7 : get_high_impact_documents() ───────────────────────────────────
def test_get_high_impact(db):
    doc_low  = _make_doc(4)
    doc_high = _make_doc(5)
    orm_low  = db.upsert_document(doc_low)
    orm_high = db.upsert_document(doc_high)

    low_an = AnalysisResult(summary="Faible", impact_level="faible")
    high_an = AnalysisResult(summary="Critique", impact_level="critique")

    db.save_analysis(orm_low.id,  low_an,  criticality_score=20.0)
    db.save_analysis(orm_high.id, high_an, criticality_score=85.0)

    results = db.get_high_impact_documents(min_score=50.0)
    assert len(results) == 1
    assert results[0].id == orm_high.id
    print(f"✅ Test 7 : get_high_impact_documents() → {len(results)} document critique — OK")
