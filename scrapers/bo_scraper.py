"""
Bulletin Officiel du Royaume du Maroc scraper.
Portal: https://www.sgg.gov.ma/BulletinOfficiel.aspx
"""
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from .base_scraper import BaseScraper, LegalDocument

logger = logging.getLogger(__name__)

BO_BASE = "https://www.sgg.gov.ma"
BO_LIST = "https://www.sgg.gov.ma/BulletinOfficiel.aspx"


class BOScraper(BaseScraper):
    SOURCE_NAME = "Bulletin Officiel"
    BASE_URL = BO_LIST

    def fetch_documents(self) -> list[LegalDocument]:
        docs: list[LegalDocument] = []
        try:
            page = self.soup(BO_LIST)
        except Exception as exc:
            logger.error("Cannot reach BO portal: %s", exc)
            return docs

        # The BO portal lists issues in a table; each row links to a PDF/detail page.
        rows = page.select("table.tableBO tr, .bo-list tr")
        if not rows:
            # Fallback: grab any links that look like BO issue links
            rows = page.find_all("a", href=re.compile(r"BulletinOfficiel|BO_\d+", re.I))

        for item in rows[:20]:  # limit to the 20 most recent
            try:
                link = item if item.name == "a" else item.find("a")
                if not link:
                    continue
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = BO_BASE + "/" + href.lstrip("/")
                title = self.clean_text(link.get_text())
                if not title:
                    continue

                pub_date = self._parse_date(item.get_text())
                doc = LegalDocument(
                    source=self.SOURCE_NAME,
                    title=title,
                    url=href,
                    published_date=pub_date,
                    doc_type=self._guess_doc_type(title),
                    reference=self._extract_reference(title),
                )
                docs.append(doc)
            except Exception as exc:
                logger.debug("Skipping BO row: %s", exc)

        return docs

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    _DATE_PATTERN = re.compile(
        r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})"
        r"|(\d{4})[/-](\d{1,2})[/-](\d{1,2})"
    )

    _MONTHS_FR = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
    }

    def _parse_date(self, text: str) -> datetime | None:
        m = self._DATE_PATTERN.search(text)
        if m:
            if m.group(1):
                return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            return datetime(int(m.group(4)), int(m.group(5)), int(m.group(6)))

        lower = text.lower()
        for month_name, month_num in self._MONTHS_FR.items():
            if month_name in lower:
                year_m = re.search(r"\b(20\d{2})\b", lower)
                day_m = re.search(r"\b(\d{1,2})\b", lower)
                if year_m and day_m:
                    return datetime(int(year_m.group(1)), month_num, int(day_m.group(1)))
        return None

    def _guess_doc_type(self, title: str) -> str:
        t = title.lower()
        for keyword, dtype in [
            ("dahir", "dahir"),
            ("décret", "décret"),
            ("arrêté", "arrêté"),
            ("circulaire", "circulaire"),
            ("loi", "loi"),
            ("ordonnance", "ordonnance"),
            ("avis", "avis"),
        ]:
            if keyword in t:
                return dtype
        return "texte"

    def _extract_reference(self, title: str) -> str:
        m = re.search(r"n[°º]\s*[\d\-\.]+", title, re.I)
        return m.group(0) if m else ""
