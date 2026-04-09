"""
ÉTAPE 4 — Test du ClaudeAnalyzer (sans appel API réel)
Utilise des mocks pour simuler les réponses Claude.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import pytest
from unittest.mock import MagicMock, patch
from scrapers.base_scraper import LegalDocument
from analyzer.claude_analyzer import ClaudeAnalyzer, AnalysisResult


def _make_doc():
    return LegalDocument(
        source="CNDP",
        title="Délibération n°02-2024 relative au traitement des données biométriques",
        url="https://cndp.ma/deliberation-02-2024",
        doc_type="délibération",
        content="La CNDP interdit le traitement des données biométriques sans consentement explicite. "
                "Toute entreprise doit se conformer dans un délai de 6 mois.",
    )


def _mock_response(data: dict):
    """Crée un faux objet response Anthropic."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(data))]
    return mock_msg


# ─── Test 1 : Analyse complète simulée ──────────────────────────────────────
def test_analyze_mock_complet():
    fake_data = {
        "summary": "La CNDP interdit le traitement biométrique sans consentement.",
        "key_points": ["Interdiction biométrie", "Délai 6 mois"],
        "affected_sectors": ["Numérique", "RH"],
        "obligations": ["Consentement explicite requis", "Déclaration CNDP"],
        "deadlines": ["6 mois après publication"],
        "impact_level": "élevé",
        "tags": ["biométrie", "CNDP", "données personnelles"],
    }
    with patch("anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_client.messages.create.return_value = _mock_response(fake_data)

        analyzer = ClaudeAnalyzer(api_key="fake-key")
        analyzer.client = mock_client

        result = analyzer.analyze(_make_doc())

    assert result.impact_level == "élevé"
    assert "biométrie" in result.tags
    assert len(result.obligations) == 2
    print(f"✅ Test 1 : Analyse mock complète → impact={result.impact_level} — OK")


# ─── Test 2 : Parsing JSON avec balises markdown ────────────────────────────
def test_parse_json_avec_markdown():
    raw = '```json\n{"summary":"Test","key_points":[],"affected_sectors":[],"obligations":[],"deadlines":[],"impact_level":"modéré","tags":["test"]}\n```'
    with patch("anthropic.Anthropic"):
        analyzer = ClaudeAnalyzer.__new__(ClaudeAnalyzer)
        result = analyzer._parse(raw)
    assert result.impact_level == "modéré"
    assert result.tags == ["test"]
    print("✅ Test 2 : Parsing JSON avec balises markdown — OK")


# ─── Test 3 : Fallback si JSON invalide ─────────────────────────────────────
def test_parse_json_invalide():
    raw = "Voici mon analyse : le document est important pour la conformité."
    with patch("anthropic.Anthropic"):
        analyzer = ClaudeAnalyzer.__new__(ClaudeAnalyzer)
        result = analyzer._parse(raw)
    assert result.summary != ""
    assert result.impact_level == "faible"  # valeur par défaut
    print("✅ Test 3 : Fallback JSON invalide — OK")


# ─── Test 4 : Troncature du contenu long ────────────────────────────────────
def test_content_truncation():
    doc = _make_doc()
    doc.content = "A" * 20_000  # très long
    with patch("anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        fake_response = {"summary":"ok","key_points":[],"affected_sectors":[],
                         "obligations":[],"deadlines":[],"impact_level":"faible","tags":[]}
        mock_client.messages.create.return_value = _mock_response(fake_response)

        analyzer = ClaudeAnalyzer(api_key="fake-key")
        analyzer.client = mock_client
        analyzer.analyze(doc)

        call_args = mock_client.messages.create.call_args
        prompt_content = call_args[1]["messages"][0]["content"]
        assert len(prompt_content) <= 9000  # prompt + 8000 chars content
    print(f"✅ Test 4 : Troncature contenu long — OK")


# ─── Test 5 : AnalysisResult valeurs par défaut ─────────────────────────────
def test_analysis_result_defaults():
    result = AnalysisResult()
    assert result.impact_level == "faible"
    assert result.key_points == []
    assert result.tags == []
    assert result.summary == ""
    print("✅ Test 5 : AnalysisResult valeurs par défaut — OK")


# ─── Test 6 : to_dict() ─────────────────────────────────────────────────────
def test_analysis_result_to_dict():
    result = AnalysisResult(
        summary="Résumé test",
        impact_level="critique",
        tags=["dahir", "finances"],
    )
    d = result.to_dict()
    assert d["impact_level"] == "critique"
    assert "dahir" in d["tags"]
    assert "summary" in d
    print("✅ Test 6 : to_dict() — OK")
