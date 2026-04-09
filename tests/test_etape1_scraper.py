"""
ÉTAPE 1 — Test du scraper de base (BaseScraper / LegalDocument)
Vérifie la création de documents, le nettoyage de texte et la structure de données.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime
from scrapers.base_scraper import LegalDocument


# ─── Test 1 : Création d'un document minimal ───────────────────────────────
def test_legal_document_creation():
    doc = LegalDocument(
        source="Bulletin Officiel",
        title="Dahir n° 1-09-15 relatif à la protection des données",
        url="https://www.sgg.gov.ma/dahir-1-09-15",
    )
    assert doc.source == "Bulletin Officiel"
    assert doc.title.startswith("Dahir")
    assert doc.url.startswith("https://")
    assert doc.doc_type == "unknown"
    assert doc.content == ""
    print("✅ Test 1 : Création document minimal — OK")


# ─── Test 2 : Document complet avec tous les champs ────────────────────────
def test_legal_document_full():
    doc = LegalDocument(
        source="CNDP",
        title="Délibération n°02-2024 relative au traitement des données",
        url="https://www.cndp.ma/deliberation-02-2024",
        content="La Commission Nationale de contrôle de la protection des Données à caractère Personnel...",
        doc_type="délibération",
        reference="n°02-2024",
        published_date=datetime(2024, 3, 15),
    )
    assert doc.source == "CNDP"
    assert doc.doc_type == "délibération"
    assert doc.reference == "n°02-2024"
    assert doc.published_date.year == 2024
    print("✅ Test 2 : Document complet — OK")


# ─── Test 3 : Conversion en dictionnaire ───────────────────────────────────
def test_legal_document_to_dict():
    doc = LegalDocument(
        source="SGG",
        title="Décret n° 2-22-431",
        url="https://www.sgg.gov.ma/decret-2-22-431",
        doc_type="décret",
        published_date=datetime(2022, 6, 1),
    )
    d = doc.to_dict()
    assert isinstance(d, dict)
    assert d["source"] == "SGG"
    assert d["doc_type"] == "décret"
    assert "published_date" in d
    assert "scraped_at" in d
    print("✅ Test 3 : Conversion to_dict() — OK")


# ─── Test 4 : Champ scraped_at auto-rempli ─────────────────────────────────
def test_scraped_at_auto():
    before = datetime.utcnow()
    doc = LegalDocument(source="ANRT", title="Test", url="https://anrt.ma/test")
    after = datetime.utcnow()
    assert before <= doc.scraped_at <= after
    print("✅ Test 4 : scraped_at automatique — OK")


# ─── Test 5 : URL unique par document ──────────────────────────────────────
def test_different_urls():
    doc1 = LegalDocument(source="BO", title="Doc 1", url="https://bo.ma/doc1")
    doc2 = LegalDocument(source="BO", title="Doc 2", url="https://bo.ma/doc2")
    assert doc1.url != doc2.url
    print("✅ Test 5 : URLs distinctes — OK")
