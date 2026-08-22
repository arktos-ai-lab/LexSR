"""
MAS (Monetaire Autoriteit Suriname) scraper.

Scrapes financial sector legislation from Suriname Central Bank.
URL: https://mas.sr/nl/wetten-en-verdragen/

Contains:
- Banking laws
- Monetary regulations
- Financial sector supervision rules
- Insurance regulations
- Pension fund regulations
"""

from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional

from .base import BaseScraper, ScrapedDocument, ScrapeResult

logger = logging.getLogger(__name__)


class MASScraper(BaseScraper):
    """Scraper for MAS (Central Bank) website."""

    def __init__(self, rate_limit: float = 2.0):
        super().__init__(
            base_url="https://mas.sr",
            source_name="mas",
            rate_limit=rate_limit,
        )
        self.legislation_url = "https://mas.sr/nl/wetten-en-verdragen/"

    def scrape(self) -> ScrapeResult:
        """Scrape all financial sector legislation."""
        logger.info(f"Scraping MAS from {self.legislation_url}")

        result = ScrapeResult()

        try:
            content = self._fetch_url(self.legislation_url)
            if not content:
                result.errors.append("Failed to fetch MAS legislation page")
                return result

            html = content.decode('utf-8', errors='ignore')
            documents = self._extract_documents(html, self.legislation_url)
            result.documents.extend(documents)

            logger.info(f"Found {len(documents)} documents on MAS")

        except Exception as e:
            logger.error(f"MAS scraping failed: {e}", exc_info=True)
            result.errors.append(str(e))

        return result

    def _extract_documents(self, html: str, base_url: str) -> List[ScrapedDocument]:
        """Extract financial legislation documents."""
        documents = []

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            links = soup.find_all('a', href=True)

            for link in links:
                href = link['href']

                if any(skip in href.lower() for skip in ['#', 'javascript:', 'mailto:']):
                    continue

                # Financial sector keywords
                is_financial_doc = (
                    self._is_pdf_url(href) or
                    any(keyword in href.lower() for keyword in [
                        'wet', 'bank', 'verzekering', 'insurance', 'pensioen',
                        'pension', 'monetair', 'monetary', 'financial', 'toezicht',
                        'supervision', 'regeling', 'regulation'
                    ])
                )

                if is_financial_doc:
                    title = self._normalize_title(link.get_text())

                    if not title or len(title) < 3:
                        parent = link.find_parent(['td', 'li', 'div'])
                        if parent:
                            title = self._normalize_title(parent.get_text())

                    from urllib.parse import urljoin
                    absolute_url = urljoin(base_url, href)

                    doc_type = "pdf" if self._is_pdf_url(absolute_url) else "html"
                    doc_date = self._extract_date_from_text(title)
                    category = self._categorize_financial_document(title)

                    doc = ScrapedDocument(
                        title=title or "Untitled Financial Document",
                        url=absolute_url,
                        document_type=doc_type,
                        source=self.source_name,
                        category=category,
                        date_published=doc_date,
                        scraped_at=date.today(),
                    )

                    documents.append(doc)
                    logger.debug(f"Found financial document: {title} ({category})")

        except ImportError:
            logger.error("BeautifulSoup required")
            return []
        except Exception as e:
            logger.error(f"Document extraction failed: {e}", exc_info=True)

        return documents

    def _categorize_financial_document(self, title: str) -> str:
        """Categorize financial document by type."""
        title_lower = title.lower()

        if any(word in title_lower for word in ['bankwet', 'banking law', 'bank act']):
            return "bankwet"
        elif any(word in title_lower for word in ['verzekering', 'insurance']):
            return "verzekeringswet"
        elif any(word in title_lower for word in ['pensioen', 'pension']):
            return "pensioenwet"
        elif any(word in title_lower for word in ['toezicht', 'supervision', 'supervisie']):
            return "toezicht"
        elif any(word in title_lower for word in ['deviezenregeling', 'foreign exchange']):
            return "deviezenwet"
        elif any(word in title_lower for word in ['witwassen', 'money laundering', 'aml']):
            return "antiwitwas"
        elif any(word in title_lower for word in ['krediet', 'credit', 'lending']):
            return "kredietwet"
        else:
            return "algemeen"

    def scrape_document(self, url: str) -> Optional[ScrapedDocument]:
        """Scrape specific financial document."""
        logger.info(f"Scraping financial document: {url}")

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
            category = self._categorize_financial_document(title)

            doc = ScrapedDocument(
                title=title,
                url=url,
                document_type=doc_type,
                source=self.source_name,
                category=category,
                content=content,
                scraped_at=date.today(),
            )

            return doc

        except Exception as e:
            logger.error(f"Failed to scrape {url}: {e}")
            return None
