"""
DGSSI – Direction Générale de la Sécurité des Systèmes d'Information.
Portal: https://www.dgssi.gov.ma
"""
import logging
import re
from datetime import datetime

from .base_scraper import BaseScraper, LegalDocument

logger = logging.getLogger(__name__)

DGSSI_BASE = "https://www.dgssi.gov.ma"
SECTIONS = [
    "/fr/content/textes-juridiques",
    "/fr/content/alertes-et-avis",
    "/fr/content/actualites",
]


class DGSSIScraper(BaseScraper):
    SOURCE_NAME = "DGSSI"
    BASE_URL = DGSSI_BASE

    def fetch_documents(self) -> list[LegalDocument]:
        docs: list[LegalDocument] = []
        for section in SECTIONS:
            url = DGSSI_BASE + section
            try:
                page = self.soup(url)
            except Exception as exc:
                logger.warning("DGSSI section unavailable [%s]: %s", section, exc)
                continue

            for item in page.select(".views-row, article, .node"):
                try:
                    link = item.find("a", href=True)
                    if not link:
                        continue
                    href = link["href"]
                    if not href.startswith("http"):
                        href = DGSSI_BASE + href
                    title = self.clean_text(link.get_text())
                    if not title:
                        continue

                    date_tag = item.select_one("time, .date, .field-date")
                    pub_date = self._parse_date(
                        (date_tag.get("datetime") or date_tag.get_text()) if date_tag else ""
                    )

                    doc = LegalDocument(
                        source=self.SOURCE_NAME,
                        title=title,
                        url=href,
                        published_date=pub_date,
                        doc_type=self._infer_type(section, title),
                    )
                    docs.append(doc)
                except Exception as exc:
                    logger.debug("DGSSI item skip: %s", exc)

        return docs

    def _parse_date(self, raw: str) -> datetime | None:
        raw = raw.strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(raw[:10], fmt[:len(raw[:10])])
            except ValueError:
                pass
        return None

    def _infer_type(self, section: str, title: str) -> str:
        if "alertes" in section:
            return "alerte sécurité"
        if "textes" in section:
            return "texte juridique"
        return "actualité"
