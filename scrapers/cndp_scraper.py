"""
CNDP – Commission Nationale de contrôle de la protection
des Données à caractère Personnel.
Portal: https://www.cndp.ma
"""
import logging
import re
from datetime import datetime

from .base_scraper import BaseScraper, LegalDocument

logger = logging.getLogger(__name__)

CNDP_BASE = "https://www.cndp.ma"
SECTIONS = [
    "/fr/textes-legislatifs-et-reglementaires",
    "/fr/deliberations",
    "/fr/actualites",
]


class CNDPScraper(BaseScraper):
    SOURCE_NAME = "CNDP"
    BASE_URL = CNDP_BASE

    def fetch_documents(self) -> list[LegalDocument]:
        docs: list[LegalDocument] = []
        for section in SECTIONS:
            url = CNDP_BASE + section
            try:
                page = self.soup(url)
            except Exception as exc:
                logger.warning("CNDP section unavailable [%s]: %s", section, exc)
                continue

            for article in page.select("article, .views-row, li.item"):
                try:
                    link = article.find("a", href=True)
                    if not link:
                        continue
                    href = link["href"]
                    if not href.startswith("http"):
                        href = CNDP_BASE + href
                    title = self.clean_text(link.get_text())
                    if not title:
                        continue

                    date_tag = article.select_one("time, .date, span.date-display-single")
                    pub_date = None
                    if date_tag:
                        pub_date = self._parse_date(date_tag.get("datetime", "") or date_tag.get_text())

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
                    logger.debug("CNDP item skip: %s", exc)

        return docs

    def _parse_date(self, raw: str) -> datetime | None:
        raw = raw.strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(raw[:len(fmt)], fmt)
            except ValueError:
                pass
        return None

    def _infer_type(self, section: str, title: str) -> str:
        if "deliberations" in section:
            return "délibération"
        if "textes" in section:
            t = title.lower()
            for kw, dt in [("loi", "loi"), ("décret", "décret"), ("arrêté", "arrêté")]:
                if kw in t:
                    return dt
            return "texte législatif"
        return "actualité"

    def _extract_reference(self, title: str) -> str:
        m = re.search(r"n[°º]\s*[\d\-\.]+", title, re.I)
        return m.group(0) if m else ""
