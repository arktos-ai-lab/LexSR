"""
SRIS (Suriname Rechtspraak Informatie Systeem) scraper.

Scrapes case law and court decisions from Suriname judicial system.
URL: https://www.sris.sr/

Contains:
- Supreme Court decisions (Hoge Raad)
- Court of Justice decisions (Hof van Justitie)
- District Court decisions (Kantongerecht)
- Jurisprudence database
- ECLI identifiers

This is the PRIMARY source for Suriname case law.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import List, Optional

from .base import BaseScraper, ScrapedDocument, ScrapeResult

logger = logging.getLogger(__name__)


class SRISScraper(BaseScraper):
    """Scraper for SRIS (Case Law Database) website."""

    def __init__(self, rate_limit: float = 2.0):
        super().__init__(
            base_url="https://www.sris.sr",
            source_name="sris",
            rate_limit=rate_limit,
        )
        # All the actual document archive URLs - deep category pages
        self.urls_to_scrape = [
            # Law archives by category
            "https://www.sris.sr/wettenarchief/",  # Law archive - MAIN
            "https://www.sris.sr/administratief-recht/",  # Administrative law
            "https://www.sris.sr/burgerlijk-recht/",  # Civil law
            "https://www.sris.sr/strafrecht/",  # Criminal law
            "https://www.sris.sr/sociaal-recht/",  # Social law
            "https://www.sris.sr/staatsrecht/",  # Constitutional law
            "https://www.sris.sr/bestuursrecht/",  # Administrative law
            # State bulletins and other sections
            "https://www.sris.sr/staatsbladden/",  # State bulletins
            "https://www.sris.sr/",  # Homepage (fallback)
        ]

    def scrape(self) -> ScrapeResult:
        """Scrape case law database from multiple pages (with pagination)."""
        logger.info(f"Scraping SRIS from {len(self.urls_to_scrape)} entry points")

        result = ScrapeResult()
        seen_urls = set()  # Track to avoid duplicates

        # Try all entry points
        for entry_url in self.urls_to_scrape:
            try:
                logger.info(f"Scraping SRIS page: {entry_url}")
                content = self._fetch_url(entry_url)
                if not content:
                    logger.warning(f"Failed to fetch {entry_url}")
                    continue

                html = content.decode('utf-8', errors='ignore')
                documents = self._extract_documents(html, entry_url)

                # Filter out duplicates
                for doc in documents:
                    if doc.url not in seen_urls:
                        result.documents.append(doc)
                        seen_urls.add(doc.url)

                logger.info(f"Found {len(documents)} documents on {entry_url} (page 1)")

                # Discover and process pagination for this entry point
                pagination_urls = self._find_pagination_urls(html, entry_url)

                if pagination_urls:
                    logger.info(f"  Found {len(pagination_urls)} pagination URLs for this entry point")

                    for i, page_url in enumerate(pagination_urls, start=2):
                        try:
                            page_content = self._fetch_url(page_url)
                            if not page_content:
                                # Already visited or fetch failed
                                continue

                            page_html = page_content.decode('utf-8', errors='ignore')
                            page_docs = self._extract_documents(page_html, page_url)

                            # Filter out duplicates
                            for doc in page_docs:
                                if doc.url not in seen_urls:
                                    result.documents.append(doc)
                                    seen_urls.add(doc.url)

                            logger.info(f"  Page {i}: Found {len(page_docs)} documents")

                        except Exception as e:
                            logger.warning(f"Failed to process pagination page {page_url}: {e}")
                            continue

            except Exception as e:
                logger.warning(f"Failed to scrape {entry_url}: {e}")
                continue

        logger.info(f"Total unique documents found on SRIS: {len(result.documents)}")
        return result

    def _extract_documents(self, html: str, base_url: str) -> List[ScrapedDocument]:
        """Extract court decisions."""
        documents = []

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            links = soup.find_all('a', href=True)

            # Blacklist for non-document links
            blacklist = [
                'vacature', 'contact', 'about', 'over', 'home', 'login',
                'facebook', 'twitter', 'social', 'nieuws', 'news', 'agenda'
            ]

            for link in links:
                href = link['href']
                link_text = link.get_text().lower()

                if any(skip in href.lower() for skip in ['#', 'javascript:', 'mailto:', 'tel:']):
                    continue

                # Skip blacklisted links
                if any(black in href.lower() or black in link_text for black in blacklist):
                    continue

                # Broader document keywords (including Staatsblad - State Bulletins)
                is_document = (
                    self._is_pdf_url(href) or
                    any(keyword in href.lower() for keyword in [
                        'arrest', 'uitspraak', 'vonnis', 'decision', 'judgment',
                        'ecli', 'hoge-raad', 'hof', 'kantongerecht',
                        'rechtspraak', 'case', 'ruling', 'staatsblad', 's.b.',
                        'wet', 'law', 'regeling', 'regulation', 'besluit', 'decree',
                        'beschikking', 'resolution', 'publicatie', 'document'
                    ]) or
                    any(keyword in link_text for keyword in [
                        'staatsblad', 's.b.', 'wet ', 'law', 'regeling',
                        'besluit', 'beschikking', 'no.', 'artikel', 'article'
                    ])
                )

                if is_document:
                    title = self._normalize_title(link.get_text())

                    if not title or len(title) < 3:
                        parent = link.find_parent(['td', 'li', 'div'])
                        if parent:
                            title = self._normalize_title(parent.get_text())

                    from urllib.parse import urljoin
                    absolute_url = urljoin(base_url, href)

                    doc_type = "pdf" if self._is_pdf_url(absolute_url) else "html"
                    doc_date = self._extract_decision_date(title, href)

                    # Extract ECLI if present
                    ecli = self._extract_ecli(title + " " + href)

                    # Determine court level
                    court = self._identify_court(title, href)

                    doc = ScrapedDocument(
                        title=title or "Untitled Court Decision",
                        url=absolute_url,
                        document_type=doc_type,
                        source=self.source_name,
                        category=court,
                        official_id=ecli,  # Store ECLI as official ID
                        date_published=doc_date,
                        scraped_at=date.today(),
                        metadata={
                            "ecli": ecli,
                            "court": court,
                        },
                    )

                    documents.append(doc)
                    logger.debug(f"Found case: {title} ({court}, ECLI: {ecli})")

        except ImportError:
            logger.error("BeautifulSoup required")
            return []
        except Exception as e:
            logger.error(f"Document extraction failed: {e}", exc_info=True)

        return documents

    def _extract_ecli(self, text: str) -> Optional[str]:
        """
        Extract ECLI identifier from text.

        ECLI format: ECLI:SR:HR:2024:123
        - SR = Suriname
        - HR = Hoge Raad (Supreme Court)
        - 2024 = Year
        - 123 = Sequential number
        """
        pattern = r'ECLI:SR:[A-Z]+:\d{4}:\d+'
        match = re.search(pattern, text.upper())
        return match.group(0) if match else None

    def _extract_decision_date(self, title: str, url: str) -> Optional[date]:
        """Extract decision date from title or URL."""
        # Try title first
        doc_date = self._extract_date_from_text(title)
        if doc_date:
            return doc_date

        # Try URL
        doc_date = self._extract_date_from_text(url)
        if doc_date:
            return doc_date

        # Try to extract from ECLI (year component)
        ecli = self._extract_ecli(title + " " + url)
        if ecli:
            year_match = re.search(r':(\d{4}):', ecli)
            if year_match:
                year = int(year_match.group(1))
                # Return January 1st of that year as fallback
                return date(year, 1, 1)

        return None

    def _identify_court(self, title: str, url: str) -> str:
        """Identify which court issued the decision."""
        combined = (title + " " + url).lower()

        if any(word in combined for word in ['hoge raad', 'hogeraad', 'hr:', 'supreme']):
            return "hoge_raad"
        elif any(word in combined for word in ['hof van justitie', 'hof', 'hvj:', 'court of justice']):
            return "hof_van_justitie"
        elif any(word in combined for word in ['kantongerecht', 'kanton', 'district court']):
            return "kantongerecht"
        elif any(word in combined for word in ['raad van beroep', 'administrative']):
            return "raad_van_beroep"
        else:
            return "onbekend"

    def scrape_document(self, url: str) -> Optional[ScrapedDocument]:
        """Scrape specific court decision."""
        logger.info(f"Scraping court decision: {url}")

        try:
            content = self._fetch_url(url)
            if not content:
                return None

            doc_type = "pdf" if self._is_pdf_url(url) else "html"

            if doc_type == "pdf":
                from pathlib import Path
                title = Path(url).stem.replace('-', ' ').replace('_', ' ')
            else:
                html = content.decode('utf-8', errors='ignore')
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, 'html.parser')
                    title_tag = soup.find('title') or soup.find('h1')
                    title = title_tag.get_text() if title_tag else ""
                except:
                    title = ""

            title = self._normalize_title(title) or "Untitled"

            ecli = self._extract_ecli(title + " " + url)
            court = self._identify_court(title, url)
            doc_date = self._extract_decision_date(title, url)

            doc = ScrapedDocument(
                title=title,
                url=url,
                document_type=doc_type,
                source=self.source_name,
                category=court,
                official_id=ecli,
                date_published=doc_date,
                content=content,
                scraped_at=date.today(),
                metadata={
                    "ecli": ecli,
                    "court": court,
                },
            )

            return doc

        except Exception as e:
            logger.error(f"Failed to scrape {url}: {e}")
            return None
