"""
Claude-powered analysis of Moroccan legal documents.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

import anthropic

if TYPE_CHECKING:
    from scrapers.base_scraper import LegalDocument

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un expert juridique spécialisé dans le droit marocain.
Tu analyses des textes législatifs et réglementaires publiés au Maroc.
Réponds toujours en JSON valide, sans markdown ni balises.
"""

ANALYSIS_PROMPT = """Analyse le document juridique suivant et retourne un objet JSON avec exactement ces clés :
- "summary"        : résumé en 3-5 phrases (français)
- "key_points"     : liste de points clés (max 5)
- "affected_sectors": secteurs/domaines impactés (liste de strings)
- "obligations"    : nouvelles obligations légales identifiées (liste)
- "deadlines"      : échéances ou dates importantes mentionnées (liste)
- "impact_level"   : "faible" | "modéré" | "élevé" | "critique"
- "tags"           : mots-clés pertinents (liste, max 10)

Titre : {title}
Source : {source}
Type : {doc_type}
Contenu :
{content}
"""


@dataclass
class AnalysisResult:
    summary: str = ""
    key_points: list[str] = None
    affected_sectors: list[str] = None
    obligations: list[str] = None
    deadlines: list[str] = None
    impact_level: str = "faible"
    tags: list[str] = None
    raw_response: str = ""

    def __post_init__(self):
        for field in ("key_points", "affected_sectors", "obligations", "deadlines", "tags"):
            if getattr(self, field) is None:
                setattr(self, field, [])

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "key_points": self.key_points,
            "affected_sectors": self.affected_sectors,
            "obligations": self.obligations,
            "deadlines": self.deadlines,
            "impact_level": self.impact_level,
            "tags": self.tags,
        }


class ClaudeAnalyzer:
    """Sends legal documents to Claude and parses structured analysis."""

    DEFAULT_MODEL = "claude-sonnet-4-6"
    MAX_CONTENT_CHARS = 8_000   # truncate very long documents

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.client = anthropic.Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
        self.model = model or self.DEFAULT_MODEL

    def analyze(self, doc: LegalDocument) -> AnalysisResult:
        content = (doc.content or doc.title)[: self.MAX_CONTENT_CHARS]
        prompt = ANALYSIS_PROMPT.format(
            title=doc.title,
            source=doc.source,
            doc_type=doc.doc_type,
            content=content,
        )

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text
            return self._parse(raw)
        except anthropic.APIError as exc:
            logger.error("Claude API error for '%s': %s", doc.title, exc)
            return AnalysisResult(summary="Analyse indisponible (erreur API).")

    def analyze_batch(self, docs: list[LegalDocument]) -> list[tuple[LegalDocument, AnalysisResult]]:
        results = []
        for doc in docs:
            result = self.analyze(doc)
            results.append((doc, result))
        return results

    # ------------------------------------------------------------------

    def _parse(self, raw: str) -> AnalysisResult:
        import json

        raw = raw.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Could not parse Claude response as JSON")
            return AnalysisResult(summary=raw[:500], raw_response=raw)

        return AnalysisResult(
            summary=data.get("summary", ""),
            key_points=data.get("key_points", []),
            affected_sectors=data.get("affected_sectors", []),
            obligations=data.get("obligations", []),
            deadlines=data.get("deadlines", []),
            impact_level=data.get("impact_level", "faible"),
            tags=data.get("tags", []),
            raw_response=raw,
        )
