"""
Scraper for rechtspraak.sr — the Hof van Justitie (Court of Justice of
Suriname) case-law database.

Site structure (verified against live pages, 2026-08):
  - WordPress-based; individual decisions are posts with URLs like
    /sru-hvj-2022-39/, /sru-k1-2019-3/, /sru-aa-2087/ (court-code +
    year + sequence, or a flat sequence for some courts).
  - No public listing/search API — decisions are discovered via the
    WordPress XML sitemap (sitemap.xml -> post-sitemap{N}.xml).
  - Each decision page has a metadata block of label/value pairs
    (div.list-label / div.list-value): Instantie (court), Zaaknummer
    (case number), Uitspraakdatum (decision date), Publicatiedatum
    (publication date), Rechtsgebied (legal area), Inhoudsindicatie
    (abstract) — followed by the full decision text in
    div.search-result.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import List, Optional

from .base import BaseScraper, ScrapedDocument, ScrapeResult

logger = logging.getLogger(__name__)

_SITEMAP_INDEX = "https://rechtspraak.sr/sitemap.xml"
_DECISION_URL_RE = re.compile(r"^https://rechtspraak\.sr/(sru-[a-z0-9-]+)/?$", re.IGNORECASE)

_DUTCH_MONTHS = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "augustus": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12,
}


def parse_dutch_date(raw: str) -> Optional[date]:
    """Parse '18 februari 2022' -> date(2022, 2, 18). Returns None on failure."""
    if not raw:
        return None
    parts = raw.strip().lower().split()
    if len(parts) == 3:
        try:
            day = int(parts[0])
            month = _DUTCH_MONTHS.get(parts[1])
            year = int(parts[2])
            if month and 1 <= day <= 31 and 1900 <= year <= 2100:
                return date(year, month, day)
        except (ValueError, TypeError):
            pass
    return None


class RechtspraakScraper(BaseScraper):
    """Scraper for rechtspraak.sr case-law decisions."""

    def __init__(self, rate_limit: float = 2.0):
        super().__init__(
            base_url="https://rechtspraak.sr",
            source_name="rechtspraak",
            rate_limit=rate_limit,
        )

    def discover_decision_urls(self) -> List[str]:
        """Discover all decision URLs via the WordPress sitemap index."""
        urls: List[str] = []

        index_content = self._fetch_url(_SITEMAP_INDEX)
        if not index_content:
            logger.error("Failed to fetch sitemap index")
            return urls

        sub_sitemaps = self._extract_sitemap_locs(index_content)
        logger.info(f"Sitemap index lists {len(sub_sitemaps)} sub-sitemaps")

        for sub_url in sub_sitemaps:
            # Decisions live in post-sitemap*.xml; skip page/category/date archives.
            if "post-sitemap" not in sub_url:
                continue

            content = self._fetch_url(sub_url)
            if not content:
                continue

            for loc in self._extract_sitemap_locs(content):
                if _DECISION_URL_RE.match(loc):
                    urls.append(loc)

        logger.info(f"Discovered {len(urls)} decision URLs")
        return urls

    @staticmethod
    def _extract_sitemap_locs(xml_content: bytes) -> List[str]:
        """Extract <loc> values from a sitemap or sitemap-index XML document."""
        try:
            from xml.etree import ElementTree
            root = ElementTree.fromstring(xml_content)
            ns = ""
            if "}" in root.tag:
                ns = root.tag.split("}")[0] + "}"
            return [el.text.strip() for el in root.iter(f"{ns}loc") if el.text]
        except ElementTree.ParseError as exc:
            logger.warning(f"Failed to parse sitemap XML: {exc}")
            return []

    def scrape_document(self, url: str) -> Optional[ScrapedDocument]:
        """Fetch and parse a single decision page (BaseScraper's required interface)."""
        return self.scrape_decision(url)

    def scrape_decision(self, url: str) -> Optional[ScrapedDocument]:
        """Fetch and parse a single decision page."""
        content = self._fetch_url(url)
        if not content:
            return None

        try:
            from bs4 import BeautifulSoup
            html = content.decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
        except ImportError:
            logger.error("BeautifulSoup required. Install with: pip install beautifulsoup4")
            return None

        labels = [el.get_text(strip=True) for el in soup.find_all(class_="list-label")]
        values = [el.get_text(strip=True) for el in soup.find_all(class_="list-value")]
        fields = dict(zip(labels, values))

        content_el = soup.find(class_="search-result")
        full_text = content_el.get_text("\n", strip=True) if content_el else ""

        slug_match = re.search(r"/(sru-[a-z0-9-]+)/?$", url, re.IGNORECASE)
        sru_id = slug_match.group(1).upper() if slug_match else url

        title_el = soup.find("title")
        title = title_el.get_text(strip=True) if title_el else sru_id

        decision_date = parse_dutch_date(fields.get("Uitspraakdatum", ""))
        publication_date = parse_dutch_date(fields.get("Publicatiedatum", ""))

        return ScrapedDocument(
            title=title,
            url=url,
            document_type="html",
            source=self.source_name,
            date_published=publication_date or decision_date,
            content=content,
            scraped_at=date.today(),
            metadata={
                "sru_id": sru_id,
                "court": fields.get("Instantie", ""),
                "case_number": fields.get("Zaaknummer", ""),
                "decision_date": decision_date.isoformat() if decision_date else None,
                "publication_date": publication_date.isoformat() if publication_date else None,
                "legal_area": fields.get("Rechtsgebied", ""),
                "abstract": fields.get("Inhoudsindicatie", ""),
                "full_text": full_text,
            },
        )

    def scrape(self, limit: Optional[int] = None) -> ScrapeResult:
        """Discover and fetch decisions. `limit` bounds how many are fetched."""
        result = ScrapeResult()

        urls = self.discover_decision_urls()
        if not urls:
            result.errors.append("No decision URLs discovered from sitemap")
            return result

        if limit:
            urls = urls[:limit]

        for i, url in enumerate(urls, 1):
            try:
                doc = self.scrape_decision(url)
                if doc:
                    result.documents.append(doc)
                else:
                    result.warnings.append(f"Failed to fetch: {url}")
            except Exception as exc:
                logger.warning(f"Failed to scrape decision {url}: {exc}")
                result.errors.append(f"{url}: {exc}")

            if i % 25 == 0:
                logger.info(f"  [{i}/{len(urls)}] decisions fetched")

        logger.info(f"Scraped {len(result.documents)} decisions ({len(result.errors)} errors)")
        return result
