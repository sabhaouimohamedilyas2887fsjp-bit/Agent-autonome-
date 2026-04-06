"""
ANRT – Agence Nationale de Réglementation des Télécommunications.
Portal: https://www.anrt.ma
"""
import logging
import re
from datetime import datetime

from .base_scraper import BaseScraper, LegalDocument

logger = logging.getLogger(__name__)

ANRT_BASE = "https://www.anrt.ma"
SECTIONS = [
    "/fr/textes-de-references",
    "/fr/decisions-et-recommandations",
    "/fr/actualites",
]


class ANRTScraper(BaseScraper):
    SOURCE_NAME = "ANRT"
    BASE_URL = ANRT_BASE

    def fetch_documents(self) -> list[LegalDocument]:
        docs: list[LegalDocument] = []
        for section in SECTIONS:
            url = ANRT_BASE + section
            try:
                page = self.soup(url)
            except Exception as exc:
                logger.warning("ANRT section unavailable [%s]: %s", section, exc)
                continue

            for item in page.select(".views-row, article, li.doc-item"):
                try:
                    link = item.find("a", href=True)
                    if not link:
                        continue
                    href = link["href"]
                    if not href.startswith("http"):
                        href = ANRT_BASE + href
                    title = self.clean_text(link.get_text())
                    if not title:
                        continue

                    date_tag = item.select_one("time, .date, .field-date")
                    pub_date = None
                    if date_tag:
                        raw = date_tag.get("datetime") or date_tag.get_text()
                        pub_date = self._parse_date(raw)

                    doc = LegalDocument(
                        source=self.SOURCE_NAME,
                        title=title,
                        url=href,
                        published_date=pub_date,
                        doc_type=self._infer_type(section, title),
                        reference=self._extract_reference(title),
                    )
                    docs.append(doc)
                except Exception as exc:
                    logger.debug("ANRT item skip: %s", exc)

        return docs

    def _parse_date(self, raw: str) -> datetime | None:
        raw = raw.strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(raw[:10], fmt[:10])
            except ValueError:
                pass
        return None

    def _infer_type(self, section: str, title: str) -> str:
        if "decisions" in section:
            return "décision"
        if "textes" in section:
            t = title.lower()
            for kw, dt in [("loi", "loi"), ("décret", "décret"), ("arrêté", "arrêté")]:
                if kw in t:
                    return dt
            return "texte de référence"
        return "actualité"

    def _extract_reference(self, title: str) -> str:
        m = re.search(r"n[°º]\s*[\d\-\.]+", title, re.I)
        return m.group(0) if m else ""
