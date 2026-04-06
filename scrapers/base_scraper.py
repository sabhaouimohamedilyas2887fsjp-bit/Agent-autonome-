import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class LegalDocument:
    source: str
    title: str
    url: str
    published_date: Optional[datetime] = None
    content: str = ""
    doc_type: str = "unknown"      # loi, décret, arrêté, circulaire, avis, ...
    reference: str = ""            # e.g. "Dahir n° 1-09-15"
    raw_html: str = ""
    scraped_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "published_date": self.published_date.isoformat() if self.published_date else None,
            "content": self.content,
            "doc_type": self.doc_type,
            "reference": self.reference,
            "scraped_at": self.scraped_at.isoformat(),
        }


class BaseScraper(ABC):
    SOURCE_NAME: str = "unknown"
    BASE_URL: str = ""
    REQUEST_DELAY: float = 1.5   # seconds between requests

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "fr-MA,fr;q=0.9,ar;q=0.8,en;q=0.7",
    }

    def __init__(self, timeout: int = 30):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def scrape(self) -> list[LegalDocument]:
        """Entry point called by the scheduler."""
        logger.info("Starting scrape: %s", self.SOURCE_NAME)
        try:
            docs = self.fetch_documents()
            logger.info("Fetched %d documents from %s", len(docs), self.SOURCE_NAME)
            return docs
        except Exception as exc:
            logger.exception("Scrape failed for %s: %s", self.SOURCE_NAME, exc)
            return []

    # ------------------------------------------------------------------
    # Abstract methods
    # ------------------------------------------------------------------

    @abstractmethod
    def fetch_documents(self) -> list[LegalDocument]:
        """Fetch and return new legal documents."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get(self, url: str, **kwargs) -> requests.Response:
        time.sleep(self.REQUEST_DELAY)
        resp = self.session.get(url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp

    def soup(self, url: str, **kwargs) -> BeautifulSoup:
        resp = self.get(url, **kwargs)
        return BeautifulSoup(resp.text, "html.parser")

    @staticmethod
    def clean_text(text: str) -> str:
        return " ".join(text.split())
