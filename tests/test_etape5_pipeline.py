"""
ÉTAPE 5 — Test du pipeline complet (intégration)
Scraping → DB → Scoring → Analyse → Sauvegarde
Sans appels réseau ni API réels.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from scrapers.base_scraper import LegalDocument
from analyzer.criticality_scorer import CriticalityScorer
from analyzer.claude_analyzer import ClaudeAnalyzer, AnalysisResult
from database.db_manager import DBManager


def _fake_scrape():
    """Simule le résultat d'un scraper."""
    return [
        LegalDocument(
            source="Bulletin Officiel",
            title="Dahir n° 1-24-10 portant promulgation de la loi n° 55-19 relative à la simplification des procédures",
            url="https://bo.ma/dahir-1-24-10",
            doc_type="dahir",
            content="Loi relative à la simplification des procédures administratives. Entrée en vigueur immédiate.",
            reference="n° 1-24-10",
            published_date=datetime(2024, 4, 1),
        ),
        LegalDocument(
            source="DGSSI",
            title="Alerte sécurité : vulnérabilité critique dans les systèmes de télécommunications",
            url="https://dgssi.gov.ma/alerte-2024-04",
            doc_type="alerte sécurité",
            content="Vulnérabilité critique détectée. Mise à jour obligatoire dans un délai de 72h.",
            published_date=datetime(2024, 4, 2),
        ),
        LegalDocument(
            source="SGG",
            title="Circulaire relative à l'organisation des réunions",
            url="https://sgg.gov.ma/circulaire-reunion",
            doc_type="circulaire",
            content="Organisation des réunions internes des administrations.",
            published_date=datetime(2024, 3, 28),
        ),
    ]


# ─── Test 1 : Pipeline Scraping → DB ────────────────────────────────────────
def test_pipeline_scraping_to_db():
    db = DBManager("sqlite:///:memory:")
    docs = _fake_scrape()

    inserted = []
    for doc in docs:
        orm = db.upsert_document(doc)
        inserted.append(orm)

    assert len(inserted) == 3
    assert all(o.id is not None for o in inserted)
    print(f"✅ Test 1 : Scraping → DB → {len(inserted)} documents insérés — OK")


# ─── Test 2 : Pipeline DB → Scorer ──────────────────────────────────────────
def test_pipeline_scorer():
    scorer = CriticalityScorer()
    docs = _fake_scrape()

    results = [(doc, scorer.score(doc)) for doc in docs]
    scores = [r.score for _, r in results]

    # Le Dahir BO doit avoir le score le plus élevé
    dahir_result = results[0][1]
    assert dahir_result.score >= scores[2], "Le Dahir doit scorer plus haut que la circulaire"

    for doc, result in results:
        print(f"   [{doc.source}/{doc.doc_type}] score={result.score} niveau={result.level}")
    print("✅ Test 2 : Scoring différentiel — OK")


# ─── Test 3 : Pipeline Scorer → Filtrage ────────────────────────────────────
def test_pipeline_filtrage():
    scorer = CriticalityScorer()
    docs = _fake_scrape()

    a_analyser = [doc for doc in docs if scorer.should_analyze(doc, threshold=20)]
    assert len(a_analyser) >= 2  # Dahir + Alerte doivent passer le seuil
    print(f"✅ Test 3 : Filtrage → {len(a_analyser)}/{len(docs)} documents à analyser — OK")


# ─── Test 4 : Pipeline Analyse → DB (mock Claude) ───────────────────────────
def test_pipeline_analyse_to_db():
    db = DBManager("sqlite:///:memory:")
    scorer = CriticalityScorer()
    docs = _fake_scrape()

    fake_analysis_data = {
        "summary": "Analyse simulée du document juridique.",
        "key_points": ["Point 1", "Point 2"],
        "affected_sectors": ["Administration"],
        "obligations": ["Mise en conformité"],
        "deadlines": ["30 jours"],
        "impact_level": "élevé",
        "tags": ["dahir", "simplification"],
    }

    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(fake_analysis_data))]
    mock_client.messages.create.return_value = mock_msg

    with patch("anthropic.Anthropic", return_value=mock_client):
        analyzer = ClaudeAnalyzer(api_key="fake-key")
        analyzer.client = mock_client

        for doc in docs:
            orm_doc = db.upsert_document(doc)
            score_result = scorer.score(doc)

            if scorer.should_analyze(doc, threshold=20):
                analysis = analyzer.analyze(doc)
            else:
                analysis = AnalysisResult(
                    summary="Non analysé (score insuffisant).",
                    impact_level=score_result.level,
                )

            db.save_analysis(
                document_id=orm_doc.id,
                result=analysis,
                criticality_score=float(score_result.score),
                model_used="claude-sonnet-4-6",
            )

    # Vérification
    high_docs = db.get_high_impact_documents(min_score=30.0)
    assert len(high_docs) >= 1
    print(f"✅ Test 4 : Pipeline complet → {len(high_docs)} docs à fort impact en base — OK")


# ─── Test 5 : Idempotence du pipeline ───────────────────────────────────────
def test_pipeline_idempotence():
    """Exécuter 2 fois le pipeline ne doit pas créer de doublons."""
    db = DBManager("sqlite:///:memory:")
    docs = _fake_scrape()

    for _ in range(2):
        for doc in docs:
            db.upsert_document(doc)

    recent = db.get_recent_documents(hours=24 * 365)
    assert len(recent) == 3  # pas de doublons
    print(f"✅ Test 5 : Idempotence → {len(recent)} documents (pas de doublons) — OK")
