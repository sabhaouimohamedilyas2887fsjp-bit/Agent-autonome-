"""
Cour de Cassation du Maroc.
Portal: https://www.coursuprème.ma  /  https://www.courdecassation.ma
"""
import logging
import re
from datetime import datetime

from .base_scraper import BaseScraper, LegalDocument

logger = logging.getLogger(__name__)

CC_BASE = "https://www.courdecassation.ma"
SECTIONS = [
    "/fr/arrêts",
    "/fr/jurisprudence",
    "/fr/publications",
]


class CourCassationScraper(BaseScraper):
    SOURCE_NAME = "Cour de Cassation"
    BASE_URL = CC_BASE

    def fetch_documents(self) -> list[LegalDocument]:
        docs: list[LegalDocument] = []
        for section in SECTIONS:
            url = CC_BASE + section
            try:
                page = self.soup(url)
            except Exception as exc:
                logger.warning("Cour de Cassation section unavailable [%s]: %s", section, exc)
                continue

            for item in page.select(".views-row, article, li.arret-item, tr.decision"):
                try:
                    link = item.find("a", href=True)
                    if not link:
                        continue
                    href = link["href"]
                    if not href.startswith("http"):
                        href = CC_BASE + href
                    title = self.clean_text(link.get_text())
                    if not title:
                        continue

                    date_tag = item.select_one("time, .date, .field-date, td.date")
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
                    logger.debug("Cour Cassation item skip: %s", exc)

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
        if "arrêts" in section or "arret" in title.lower():
            return "arrêt"
        if "jurisprudence" in section:
            return "jurisprudence"
        return "publication"

    def _extract_reference(self, title: str) -> str:
        m = re.search(r"n[°º]\s*[\d\-\.]+", title, re.I)
        return m.group(0) if m else ""
