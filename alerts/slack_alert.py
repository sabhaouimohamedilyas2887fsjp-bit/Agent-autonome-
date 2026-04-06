"""
Slack alert sender using Incoming Webhooks.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from database.models import AnalysisORM, LegalDocumentORM

logger = logging.getLogger(__name__)

# Colour per impact level (Slack attachment colours)
_COLOURS = {
    "critique": "#c0392b",
    "élevé":    "#e67e22",
    "modéré":   "#f1c40f",
    "faible":   "#27ae60",
}

_ICONS = {
    "critique": ":rotating_light:",
    "élevé":    ":warning:",
    "modéré":   ":information_source:",
    "faible":   ":white_check_mark:",
}


class SlackAlert:
    def __init__(self, webhook_url: str, channel: str = ""):
        self.webhook_url = webhook_url
        self.channel = channel   # optional override

    def send(self, doc: LegalDocumentORM, analysis: AnalysisORM) -> bool:
        if not self.webhook_url:
            logger.warning("Slack webhook URL not configured.")
            return False

        level = analysis.impact_level or "faible"
        icon = _ICONS.get(level, ":memo:")
        colour = _COLOURS.get(level, "#95a5a6")

        fields = []
        if doc.source:
            fields.append({"title": "Source", "value": doc.source, "short": True})
        if doc.doc_type:
            fields.append({"title": "Type", "value": doc.doc_type, "short": True})
        if doc.published_date:
            fields.append({
                "title": "Date de publication",
                "value": doc.published_date.strftime("%d/%m/%Y"),
                "short": True,
            })
        fields.append({
            "title": "Score de criticité",
            "value": f"{int(analysis.criticality_score)}/100",
            "short": True,
        })
        if analysis.affected_sectors:
            fields.append({
                "title": "Secteurs impactés",
                "value": ", ".join(analysis.affected_sectors[:5]),
                "short": False,
            })
        if analysis.deadlines:
            fields.append({
                "title": "Échéances",
                "value": "\n".join(analysis.deadlines[:3]),
                "short": False,
            })

        key_points_text = (
            "\n".join(f"• {p}" for p in (analysis.key_points or [])[:5])
            or "N/A"
        )

        payload: dict = {
            "attachments": [
                {
                    "color": colour,
                    "pretext": f"{icon} *Veille Juridique Maroc* – Nouveau document détecté",
                    "title": doc.title,
                    "title_link": doc.url,
                    "text": f"*Résumé:*\n{analysis.summary}\n\n*Points clés:*\n{key_points_text}",
                    "fields": fields,
                    "footer": "Agent de veille juridique marocaine",
                    "mrkdwn_in": ["text", "pretext"],
                }
            ]
        }

        if self.channel:
            payload["channel"] = self.channel

        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info("Slack alert sent for doc id=%d", doc.id)
            return True
        except requests.RequestException as exc:
            logger.error("Slack send failed: %s", exc)
            return False
