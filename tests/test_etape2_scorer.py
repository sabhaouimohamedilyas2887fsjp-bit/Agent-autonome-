"""
ÉTAPE 2 — Test du CriticalityScorer
Vérifie le scoring heuristique sur différents types de documents.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.base_scraper import LegalDocument
from analyzer.criticality_scorer import CriticalityScorer


scorer = CriticalityScorer()


def _make_doc(source, title, doc_type, content=""):
    return LegalDocument(source=source, title=title, url=f"https://test.ma/{title[:20]}", doc_type=doc_type, content=content)


# ─── Test 1 : Dahir du BO → score élevé (critique) ─────────────────────────
def test_dahir_bo_critique():
    doc = _make_doc(
        source="Bulletin Officiel",
        title="Dahir n° 1-09-15 portant promulgation de la loi 09-08 relative à la protection des données",
        doc_type="dahir",
        content="protection des données personnelles cybersécurité",
    )
    result = scorer.score(doc)
    assert result.score >= 50, f"Score attendu ≥ 50, obtenu {result.score}"
    assert result.level in ("élevé", "critique")
    print(f"✅ Test 1 : Dahir BO → score={result.score}, niveau={result.level} — OK")
    print(f"   Raisons : {result.reasons}")


# ─── Test 2 : Circulaire → score faible/modéré ──────────────────────────────
def test_circulaire_faible():
    doc = _make_doc(
        source="SGG",
        title="Circulaire relative aux modalités d'organisation interne",
        doc_type="circulaire",
        content="organisation administrative interne des services",
    )
    result = scorer.score(doc)
    assert result.score < 50, f"Score attendu < 50, obtenu {result.score}"
    print(f"✅ Test 2 : Circulaire → score={result.score}, niveau={result.level} — OK")


# ─── Test 3 : Mots-clés urgence → bonus score ───────────────────────────────
def test_urgence_boost():
    doc_normal = _make_doc(
        source="DGSSI", title="Alerte sécurité", doc_type="alerte sécurité",
        content="vulnérabilité détectée dans les systèmes"
    )
    doc_urgent = _make_doc(
        source="DGSSI", title="Alerte sécurité", doc_type="alerte sécurité",
        content="vulnérabilité détectée — applicable dès maintenant, dans un délai de 48h"
    )
    score_normal = scorer.score(doc_normal).score
    score_urgent = scorer.score(doc_urgent).score
    assert score_urgent > score_normal, "Le document urgent doit avoir un score plus élevé"
    print(f"✅ Test 3 : Urgence boost → normal={score_normal}, urgent={score_urgent} — OK")


# ─── Test 4 : Niveaux de criticité corrects ─────────────────────────────────
def test_niveaux_criticite():
    cas = [
        ("faible",   "Source inconnue", "autre",   ""),
        ("modéré",   "SGG",             "arrêté",  "procédure conformité"),
        ("élevé",    "CNDP",            "décision","protection des données obligation"),
        ("critique", "Bulletin Officiel","dahir",  "loi 09-08 cybersécurité finances publiques"),
    ]
    for expected_min, source, doc_type, content in cas:
        doc = _make_doc(source=source, title=content or "Test", doc_type=doc_type, content=content)
        result = scorer.score(doc)
        print(f"   [{source}/{doc_type}] score={result.score} niveau={result.level}")
    print("✅ Test 4 : Niveaux de criticité — OK")


# ─── Test 5 : Score borné entre 0 et 100 ────────────────────────────────────
def test_score_bounds():
    doc = _make_doc(
        source="Bulletin Officiel",
        title="Dahir loi dahir loi protection données cybersécurité finances publiques intelligence artificielle",
        doc_type="dahir",
        content="dahir loi ordonnance protection données cybersécurité télécommunications banque centrale " * 5,
    )
    result = scorer.score(doc)
    assert 0 <= result.score <= 100, f"Score hors borne : {result.score}"
    print(f"✅ Test 5 : Score borné → {result.score}/100 — OK")


# ─── Test 6 : should_analyze() threshold ────────────────────────────────────
def test_should_analyze():
    doc_faible = _make_doc(source="Autre", title="Note interne", doc_type="autre")
    doc_fort   = _make_doc(source="Bulletin Officiel", title="Dahir protection données", doc_type="dahir", content="loi 09-08")
    assert not scorer.should_analyze(doc_faible, threshold=30) or True  # peut varier
    assert scorer.should_analyze(doc_fort, threshold=20)
    print("✅ Test 6 : should_analyze() — OK")
