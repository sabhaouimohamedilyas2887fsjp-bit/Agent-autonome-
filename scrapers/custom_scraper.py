"""
Template pour ajouter un nouveau scraper personnalisé.

1. Copiez ce fichier et renommez-le  ex: hcp_scraper.py
2. Modifiez SOURCE_NAME, BASE_URL et les sections à scraper
3. Importez-le dans scrapers/__init__.py et ajoutez-le à ALL_SCRAPERS
"""
import logging
import re
from datetime import datetime

from .base_scraper import BaseScraper, LegalDocument

logger = logging.getLogger(__name__)


class CustomScraper(BaseScraper):
    SOURCE_NAME = "Ma Source"          # ← nom affiché dans le dashboard
    BASE_URL    = "https://exemple.ma" # ← URL racine du site

    # Pages à scraper (chemins relatifs)
    SECTIONS = [
        "/fr/publications",
        "/fr/actualites",
    ]

    def fetch_documents(self) -> list[LegalDocument]:
        docs: list[LegalDocument] = []

        for section in self.SECTIONS:
            url = self.BASE_URL + section
            try:
                page = self.soup(url)
            except Exception as exc:
                logger.warning("%s section indisponible [%s]: %s", self.SOURCE_NAME, section, exc)
                continue

            # ── Adaptez le sélecteur CSS à la structure HTML du site ──────────
            for item in page.select(".views-row, article, li.item"):
                try:
                    link = item.find("a", href=True)
                    if not link:
                        continue

                    href = link["href"]
                    if not href.startswith("http"):
                        href = self.BASE_URL + href

                    title = self.clean_text(link.get_text())
                    if not title:
                        continue

                    # Date de publication (adapter le sélecteur)
                    date_tag = item.select_one("time, .date, span.date")
                    pub_date = None
                    if date_tag:
                        raw = date_tag.get("datetime") or date_tag.get_text()
                        pub_date = self._parse_date(raw.strip())

                    doc = LegalDocument(
                        source=self.SOURCE_NAME,
                        title=title,
                        url=href,
                        published_date=pub_date,
                        doc_type=self._infer_type(title),
                        reference=self._extract_reference(title),
                    )
                    docs.append(doc)

                except Exception as exc:
                    logger.debug("%s item ignoré: %s", self.SOURCE_NAME, exc)

        return docs

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _parse_date(self, raw: str) -> datetime | None:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(raw[:10], fmt[:10])
            except ValueError:
                pass
        return None

    def _infer_type(self, title: str) -> str:
        t = title.lower()
        for kw, dtype in [
            ("dahir",      "dahir"),
            ("décret",     "décret"),
            ("loi",        "loi"),
            ("arrêté",     "arrêté"),
            ("circulaire", "circulaire"),
            ("décision",   "décision"),
            ("avis",       "avis"),
        ]:
            if kw in t:
                return dtype
        return "texte"

    def _extract_reference(self, title: str) -> str:
        m = re.search(r"n[°º]\s*[\d\-\.]+", title, re.I)
        return m.group(0) if m else ""
