"""
SGG – Secrétariat Général du Gouvernement.
Portal: https://www.sgg.gov.ma
Covers: textes législatifs & réglementaires, projets de loi.
"""
import logging
import re
from datetime import datetime

from .base_scraper import BaseScraper, LegalDocument

logger = logging.getLogger(__name__)

SGG_BASE = "https://www.sgg.gov.ma"
SECTIONS = [
    "/TextesLegislatifs.aspx",
    "/TextesReglementaires.aspx",
    "/ProjetsDeLoiAdoptes.aspx",
]


class SGGScraper(BaseScraper):
    SOURCE_NAME = "SGG"
    BASE_URL = SGG_BASE

    def fetch_documents(self) -> list[LegalDocument]:
        docs: list[LegalDocument] = []
        for section in SECTIONS:
            url = SGG_BASE + section
            try:
                page = self.soup(url)
            except Exception as exc:
                logger.warning("SGG section unavailable [%s]: %s", section, exc)
                continue

            # SGG uses ASP.NET GridViews / repeaters
            for row in page.select("table.grille tr, .listTextes li, .repeater-item"):
                try:
                    link = row.find("a", href=True)
                    if not link:
                        continue
                    href = link["href"]
                    if not href.startswith("http"):
                        href = SGG_BASE + "/" + href.lstrip("/")
                    title = self.clean_text(link.get_text())
                    if not title:
                        continue

                    cells = row.find_all("td")
                    raw_date = cells[1].get_text() if len(cells) > 1 else ""
                    pub_date = self._parse_date(raw_date)

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
                    logger.debug("SGG row skip: %s", exc)

        return docs

    def _parse_date(self, raw: str) -> datetime | None:
        raw = raw.strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                pass
        m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", raw)
        if m:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return None

    def _infer_type(self, section: str, title: str) -> str:
        t = title.lower()
        for kw, dt in [
            ("dahir", "dahir"),
            ("décret", "décret"),
            ("loi", "loi"),
            ("arrêté", "arrêté"),
            ("circulaire", "circulaire"),
        ]:
            if kw in t:
                return dt
        if "Reglementaires" in section:
            return "texte réglementaire"
        return "texte législatif"

    def _extract_reference(self, title: str) -> str:
        m = re.search(r"n[°º]\s*[\d\-\.]+", title, re.I)
        return m.group(0) if m else ""
