"""
Rule-based criticality scorer that enriches / overrides Claude's impact_level.
Useful as a fast pre-filter before spending API tokens on full analysis.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapers.base_scraper import LegalDocument


@dataclass
class ScoreResult:
    score: int          # 0-100
    level: str          # faible / modéré / élevé / critique
    reasons: list[str]  # human-readable explanation


# Keywords that raise the criticality score
_HIGH_IMPACT_KEYWORDS = [
    # Legislation types
    r"\bdahir\b", r"\bloi\b", r"\bordonnance\b",
    # Topics
    r"protect[io]+n des donn[eé]es", r"cybersécurité", r"sécurité des systèmes",
    r"télécommunications?", r"intelligence artificielle",
    r"finances? publiques?", r"code (du travail|pénal|civil)",
    r"marché(s)? financier", r"banque centrale", r"bank al-maghrib",
    r"investissement(s)?", r"concurrence", r"propriété intellectuelle",
    r"data protection", r"rgpd", r"loi 09-08", r"loi 05-20",
]

_MEDIUM_IMPACT_KEYWORDS = [
    r"\bdécret\b", r"\barrêté\b", r"\bcirculaire\b",
    r"procédure(s)?", r"conformité", r"obligation", r"sanction",
    r"mise en conformité", r"délai", r"amende", r"peine",
]

_URGENT_KEYWORDS = [
    r"urgent", r"immédiat", r"entrée en vigueur", r"applicable dès",
    r"avant le \d", r"dans un délai de",
]


class CriticalityScorer:
    """
    Scores a document 0-100 based on keyword matching and metadata.
    Can be used standalone (before Claude) or to validate Claude's output.
    """

    def score(self, doc: LegalDocument) -> ScoreResult:
        text = f"{doc.title} {doc.content}".lower()
        total = 0
        reasons: list[str] = []

        # Source weight
        source_weights = {
            "Bulletin Officiel": 20,
            "SGG": 15,
            "CNDP": 15,
            "DGSSI": 12,
            "ANRT": 12,
            "Cour de Cassation": 10,
        }
        src_score = source_weights.get(doc.source, 5)
        total += src_score
        reasons.append(f"Source '{doc.source}' (+{src_score})")

        # Doc type weight
        type_weights = {
            "dahir": 25, "loi": 20, "ordonnance": 18,
            "décret": 12, "arrêté": 8, "circulaire": 6,
            "délibération": 10, "décision": 10,
            "alerte sécurité": 15,
        }
        type_score = type_weights.get(doc.doc_type, 3)
        total += type_score
        reasons.append(f"Type '{doc.doc_type}' (+{type_score})")

        # High-impact keyword matches
        hi_hits = [kw for kw in _HIGH_IMPACT_KEYWORDS if re.search(kw, text)]
        hi_score = min(len(hi_hits) * 5, 20)
        if hi_hits:
            total += hi_score
            reasons.append(f"Mots-clés critiques: {hi_hits[:3]} (+{hi_score})")

        # Medium-impact keywords
        med_hits = [kw for kw in _MEDIUM_IMPACT_KEYWORDS if re.search(kw, text)]
        med_score = min(len(med_hits) * 2, 10)
        if med_hits:
            total += med_score
            reasons.append(f"Mots-clés modérés: {med_hits[:3]} (+{med_score})")

        # Urgency boost
        urg_hits = [kw for kw in _URGENT_KEYWORDS if re.search(kw, text)]
        if urg_hits:
            total += 10
            reasons.append(f"Urgence détectée: {urg_hits[:2]} (+10)")

        total = min(total, 100)

        level = "faible"
        if total >= 75:
            level = "critique"
        elif total >= 50:
            level = "élevé"
        elif total >= 30:
            level = "modéré"

        return ScoreResult(score=total, level=level, reasons=reasons)

    def should_analyze(self, doc: LegalDocument, threshold: int = 20) -> bool:
        """Quick pre-filter: only send to Claude if score exceeds threshold."""
        result = self.score(doc)
        return result.score >= threshold
