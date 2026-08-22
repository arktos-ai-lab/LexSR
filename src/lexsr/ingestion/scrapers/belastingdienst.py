"""
Belastingdienst Suriname scraper.

Scrapes tax legislation from the Suriname tax authority.
URL: https://belastingdienst.sr/wetten-page/

Contains:
- Tax laws (Belastingwetten)
- Ministerial decrees (Ministeriële beschikkingen)
- Tax regulations
- Customs laws
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import List, Optional

from .base import BaseScraper, ScrapedDocument, ScrapeResult

logger = logging.getLogger(__name__)


class BelastingdienstScraper(BaseScraper):
    """Scraper for Belastingdienst (Tax Authority) website."""

    def __init__(self, rate_limit: float = 2.0):
        super().__init__(
            base_url="https://belastingdienst.sr",
            source_name="belastingdienst",
            rate_limit=rate_limit,
        )
        self.legislation_url = "https://belastingdienst.sr/wetten-page/"

    def scrape(self) -> ScrapeResult:
        """Scrape all tax legislation."""
        logger.info(f"Scraping Belastingdienst from {self.legislation_url}")

        result = ScrapeResult()

        try:
            content = self._fetch_url(self.legislation_url)
            if not content:
                result.errors.append("Failed to fetch legislation page")
                return result

            html = content.decode('utf-8', errors='ignore')
            documents = self._extract_documents(html, self.legislation_url)
            result.documents.extend(documents)

            logger.info(f"Found {len(documents)} documents on Belastingdienst")

        except Exception as e:
            logger.error(f"Belastingdienst scraping failed: {e}", exc_info=True)
            result.errors.append(str(e))

        return result

    def _extract_documents(self, html: str, base_url: str) -> List[ScrapedDocument]:
        """Extract tax documents from page."""
        documents = []

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # Look for tax law links
            # Belastingdienst typically has PDFs or dedicated pages
            links = soup.find_all('a', href=True)

            for link in links:
                href = link['href']

                # Skip navigation
                if any(skip in href.lower() for skip in ['#', 'javascript:', 'mailto:']):
                    continue

                # Look for tax-related keywords
                is_tax_doc = (
                    self._is_pdf_url(href) or
                    any(keyword in href.lower() for keyword in [
                        'wet', 'belasting', 'tax', 'douane', 'customs',
                        'omzetbelasting', 'inkomstenbelasting', 'loonbelasting',
                        'vat', 'income', 'wage'
                    ])
                )

                if is_tax_doc:
                    title = self._normalize_title(link.get_text())

                    if not title or len(title) < 3:
                        parent = link.find_parent(['td', 'li', 'div', 'p'])
                        if parent:
                            title = self._normalize_title(parent.get_text())

                    from urllib.parse import urljoin
                    absolute_url = urljoin(base_url, href)

                    doc_type = "pdf" if self._is_pdf_url(absolute_url) else "html"
                    doc_date = self._extract_date_from_text(title)

                    # Categorize by tax type
                    category = self._categorize_tax_document(title)

                    doc = ScrapedDocument(
                        title=title or "Untitled Tax Document",
                        url=absolute_url,
                        document_type=doc_type,
                        source=self.source_name,
                        category=category,
                        date_published=doc_date,
                        scraped_at=date.today(),
                    )

                    documents.append(doc)
                    logger.debug(f"Found tax document: {title} ({category})")

        except ImportError:
            logger.error("BeautifulSoup required. Install: pip install beautifulsoup4")
            return []
        except Exception as e:
            logger.error(f"Document extraction failed: {e}", exc_info=True)

        return documents

    def _categorize_tax_document(self, title: str) -> str:
        """Categorize tax document by type."""
        title_lower = title.lower()

        if any(word in title_lower for word in ['omzetbelasting', 'vat', 'ob']):
            return "omzetbelasting"  # VAT
        elif any(word in title_lower for word in ['inkomstenbelasting', 'income']):
            return "inkomstenbelasting"  # Income tax
        elif any(word in title_lower for word in ['loonbelasting', 'wage', 'payroll']):
            return "loonbelasting"  # Wage tax
        elif any(word in title_lower for word in ['douane', 'customs', 'invoerrechten']):
            return "douanewet"  # Customs
        elif any(word in title_lower for word in ['successie', 'inheritance', 'estate']):
            return "successiewet"  # Inheritance tax
        elif any(word in title_lower for word in ['schenking', 'gift']):
            return "schenkingswet"  # Gift tax
        else:
            return "algemeen"  # General tax law

    def scrape_document(self, url: str) -> Optional[ScrapedDocument]:
        """Scrape specific tax document."""
        logger.info(f"Scraping tax document: {url}")

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
            category = self._categorize_tax_document(title)

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
