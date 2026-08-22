"""
DNA (De Nationale Assemblee) scraper.

Scrapes legislation from the Suriname parliament website.
URL: https://www.dna.sr/wetgeving/surinaamse-wetten/

This is the primary source for Suriname legislation.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import List, Optional

from .base import BaseScraper, ScrapedDocument, ScrapeResult

logger = logging.getLogger(__name__)


class DNAScraper(BaseScraper):
    """
    Scraper for DNA (De Nationale Assemblee) website.

    The parliament website contains:
    - Laws (Wetten)
    - Decrees (Besluiten)
    - Bills (Wetsontwerpen)
    - Parliamentary documents

    Most documents are PDFs.
    """

    def __init__(self, rate_limit: float = 2.0):
        """
        Initialize DNA scraper.

        Args:
            rate_limit: Seconds between requests (respect parliament server)
        """
        super().__init__(
            base_url="https://www.dna.sr",
            source_name="dna",
            rate_limit=rate_limit,
        )

        # All the actual document archive URLs - the deep category pages
        self.legislation_urls = [
            "https://www.dna.sr/wetgeving/surinaamse-wetten/geldende-teksten-t-m-2005/",
            "https://www.dna.sr/wetgeving/surinaamse-wetten/wetten-na-2005/",
            "https://www.dna.sr/wetgeving/surinaamse-wetten/overeenkomsten-verdragen/",
            "https://www.dna.sr/wetgeving/surinaamse-wetten/naturalisatie-wetten/",
            "https://www.dna.sr/wetgeving/surinaamse-wetten/begrotingen/",
            "https://www.dna.sr/wetgeving/surinaamse-wetten/",  # Main page
        ]

    def scrape(self) -> ScrapeResult:
        """
        Scrape all legislation from DNA website category archives (with pagination).

        Returns:
            ScrapeResult with discovered documents
        """
        logger.info(f"Scraping DNA legislation from {len(self.legislation_urls)} category pages")

        result = ScrapeResult()
        seen_urls = set()  # Track to avoid duplicates

        # Scrape each category page
        for category_url in self.legislation_urls:
            try:
                logger.info(f"Scraping DNA category: {category_url}")
                content = self._fetch_url(category_url)
                if not content:
                    logger.warning(f"Failed to fetch {category_url}")
                    continue

                html = content.decode('utf-8', errors='ignore')

                # Extract document links from initial page
                documents = self._extract_documents(html, category_url)

                # Filter out duplicates
                for doc in documents:
                    if doc.url not in seen_urls:
                        result.documents.append(doc)
                        seen_urls.add(doc.url)

                logger.info(f"Found {len(documents)} documents in {category_url} (page 1)")

                # Discover and process pagination for this category
                pagination_urls = self._find_pagination_urls(html, category_url)

                if pagination_urls:
                    logger.info(f"  Found {len(pagination_urls)} pagination URLs for this category")

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
                logger.warning(f"Failed to scrape {category_url}: {e}")
                continue

        logger.info(f"Total unique documents found on DNA: {len(result.documents)}")

        return result

    def _extract_documents(self, html: str, base_url: str) -> List[ScrapedDocument]:
        """Extract documents from legislation page."""
        documents = []

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # DNA typically lists documents in tables or lists
            # Look for PDF links with relevant keywords

            links = soup.find_all('a', href=True)

            for link in links:
                href = link['href']

                # Skip navigation links, home links, etc.
                if any(skip in href.lower() for skip in ['#', 'javascript:', 'mailto:']):
                    continue

                # Look for PDFs or pages that might contain laws
                is_relevant = (
                    self._is_pdf_url(href) or
                    any(keyword in href.lower() for keyword in ['wet', 'law', 'decree', 'besluit'])
                )

                if is_relevant:
                    # Get link text as title
                    title = self._normalize_title(link.get_text())

                    if not title or len(title) < 3:
                        # Try to get title from surrounding context
                        parent = link.find_parent(['td', 'li', 'div'])
                        if parent:
                            title = self._normalize_title(parent.get_text())

                    # Build absolute URL
                    from urllib.parse import urljoin
                    absolute_url = urljoin(base_url, href)

                    # Determine document type
                    doc_type = "pdf" if self._is_pdf_url(absolute_url) else "html"

                    # Try to extract date
                    doc_date = self._extract_date_from_text(title)

                    # Create document
                    doc = ScrapedDocument(
                        title=title or "Untitled",
                        url=absolute_url,
                        document_type=doc_type,
                        source=self.source_name,
                        date_published=doc_date,
                        scraped_at=date.today(),
                    )

                    documents.append(doc)
                    logger.debug(f"Found document: {title} ({doc_type})")

        except ImportError:
            logger.error("BeautifulSoup required for scraping. Install with: pip install beautifulsoup4")
            return []

        except Exception as e:
            logger.error(f"Failed to extract documents: {e}", exc_info=True)

        return documents

    def scrape_document(self, url: str) -> Optional[ScrapedDocument]:
        """
        Scrape a specific document from DNA.

        Args:
            url: URL of the document

        Returns:
            ScrapedDocument with content, or None on failure
        """
        logger.info(f"Scraping document: {url}")

        try:
            content = self._fetch_url(url)
            if not content:
                return None

            # Determine document type
            doc_type = "pdf" if self._is_pdf_url(url) else "html"

            # Extract title from URL or content
            if doc_type == "pdf":
                # Extract from URL
                from pathlib import Path
                title = Path(url).stem.replace('-', ' ').replace('_', ' ')
            else:
                # Extract from HTML
                html = content.decode('utf-8', errors='ignore')
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, 'html.parser')
                    title_tag = soup.find('title') or soup.find('h1')
                    title = title_tag.get_text() if title_tag else ""
                except:
                    title = ""

            title = self._normalize_title(title) or "Untitled"

            doc = ScrapedDocument(
                title=title,
                url=url,
                document_type=doc_type,
                source=self.source_name,
                content=content,
                scraped_at=date.today(),
            )

            return doc

        except Exception as e:
            logger.error(f"Failed to scrape document {url}: {e}")
            return None

    def download_and_save(
        self,
        doc: ScrapedDocument,
        output_dir: Path,
    ) -> Optional[Path]:
        """
        Download document and save to disk.

        Args:
            doc: Document to download
            output_dir: Directory to save to

        Returns:
            Path to saved file, or None on failure
        """
        if doc.content is None:
            # Fetch content if not already fetched
            content = self._fetch_url(doc.url)
            if not content:
                return None
            doc.content = content

        try:
            # Create output directory
            output_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename
            from urllib.parse import urlparse
            filename = Path(urlparse(doc.url).path).name

            if not filename:
                # Generate from title
                safe_title = "".join(c if c.isalnum() or c in ['-', '_'] else '_' for c in doc.title[:50])
                ext = ".pdf" if doc.document_type == "pdf" else ".html"
                filename = f"{safe_title}{ext}"

            output_path = output_dir / filename

            # Save content
            output_path.write_bytes(doc.content)
            doc.local_path = output_path

            logger.info(f"Saved: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Failed to save document: {e}")
            return None
