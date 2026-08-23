"""
Generic government website scraper factory.

Creates scrapers for any Suriname government website following standard patterns.
Used to quickly implement scrapers for all 34+ sources.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Optional, Set

from .base import BaseScraper, ScrapedDocument, ScrapeResult

logger = logging.getLogger(__name__)


class GenericGovernmentScraper(BaseScraper):
    """
    Generic scraper for government websites.

    Configurable for any Suriname government source.
    """

    def __init__(
        self,
        base_url: str,
        source_name: str,
        legislation_url: str,
        keywords: List[str],
        description: str,
        rate_limit: float = 2.0,
    ):
        """
        Initialize generic government scraper.

        Args:
            base_url: Base URL of website
            source_name: Internal source identifier
            legislation_url: URL for legislation section
            keywords: Keywords to identify relevant documents
            description: Human-readable description
            rate_limit: Rate limiting (seconds between requests)
        """
        super().__init__(
            base_url=base_url,
            source_name=source_name,
            rate_limit=rate_limit,
        )

        self.legislation_url = legislation_url
        self.keywords = set(keywords)
        self.description = description

    def scrape(self) -> ScrapeResult:
        """Scrape all legislation (with pagination and WordPress API support)."""
        logger.info(f"Scraping {self.source_name} from {self.legislation_url}")

        result = ScrapeResult()
        seen_urls = set()  # Track unique document URLs

        try:
            # Fetch initial page
            content = self._fetch_url(self.legislation_url)
            if not content:
                result.errors.append(f"Failed to fetch {self.source_name} page")
                return result

            html = content.decode('utf-8', errors='ignore')
            documents = self._extract_documents(html, self.legislation_url)

            # Add documents, deduplicating by URL
            for doc in documents:
                if doc.url not in seen_urls:
                    result.documents.append(doc)
                    seen_urls.add(doc.url)

            logger.info(f"Found {len(documents)} documents on {self.source_name} (page 1)")

            # Discover and process pagination URLs
            pagination_urls = self._find_pagination_urls(html, self.legislation_url)

            if pagination_urls:
                logger.info(f"Found {len(pagination_urls)} pagination URLs, processing...")

                for i, page_url in enumerate(pagination_urls, start=2):
                    try:
                        page_content = self._fetch_url(page_url)
                        if not page_content:
                            # Already visited or fetch failed
                            continue

                        page_html = page_content.decode('utf-8', errors='ignore')
                        page_docs = self._extract_documents(page_html, page_url)

                        # Add with deduplication
                        for doc in page_docs:
                            if doc.url not in seen_urls:
                                result.documents.append(doc)
                                seen_urls.add(doc.url)

                        logger.info(f"  Page {i}: Found {len(page_docs)} documents")

                    except Exception as e:
                        logger.warning(f"Failed to process pagination page {page_url}: {e}")
                        result.warnings.append(f"Pagination page failed: {page_url}")
                        continue

            # Try WordPress REST API if site appears to be WordPress-based
            if 'wp-content' in html.lower() or 'wordpress' in html.lower():
                logger.info(f"Detected WordPress site, querying REST API...")
                wp_posts = self._fetch_wordpress_posts(self.base_url, max_pages=5)

                if wp_posts:
                    logger.info(f"Found {len(wp_posts)} posts via WordPress API")

                    for post in wp_posts:
                        # Convert WordPress post to ScrapedDocument
                        post_url = post.get("link")
                        if post_url and post_url not in seen_urls:
                            doc = ScrapedDocument(
                                title=self._normalize_title(post.get("title", "")),
                                url=post_url,
                                document_type="html",  # Will extract PDFs later
                                source=self.source_name,
                                date_published=self._extract_date_from_text(post.get("date", "")),
                                scraped_at=date.today(),
                                metadata={
                                    "description": self.description,
                                    "from_wp_api": True,
                                    "excerpt": post.get("excerpt", ""),
                                },
                            )
                            result.documents.append(doc)
                            seen_urls.add(post_url)

            # Fallback discovery (year-directory guessing, site search) is
            # expensive — up to ~250 requests per source, mostly 404s on
            # sites that don't use those URL schemes at all. Only try it
            # when direct link extraction from the legislation page came up
            # short; skip it when that page already yielded real results.
            FALLBACK_THRESHOLD = 5

            if len(result.documents) >= FALLBACK_THRESHOLD:
                logger.info(
                    f"Found {len(result.documents)} documents directly; "
                    f"skipping year-directory/search fallback discovery"
                )
                logger.info(f"Total unique documents: {len(result.documents)}")
                return result

            # Try year-based directory crawling (discover documents in /YYYY/ paths)
            logger.info(f"Crawling year-based directories...")
            year_doc_urls = self._crawl_year_directories(self.base_url)

            if year_doc_urls:
                logger.info(f"Found {len(year_doc_urls)} documents via year directory crawl")

                for doc_url in year_doc_urls:
                    if doc_url not in seen_urls:
                        # Extract title from URL
                        from pathlib import Path
                        from urllib.parse import urlparse
                        parsed = urlparse(doc_url)
                        filename = Path(parsed.path).stem
                        title = filename.replace('-', ' ').replace('_', ' ')

                        doc_type = "pdf" if self._is_pdf_url(doc_url) else "html"

                        doc = ScrapedDocument(
                            title=self._normalize_title(title) or "Untitled",
                            url=doc_url,
                            document_type=doc_type,
                            source=self.source_name,
                            scraped_at=date.today(),
                            metadata={
                                "description": self.description,
                                "from_year_crawl": True,
                            },
                        )
                        result.documents.append(doc)
                        seen_urls.add(doc_url)

            # Try search interface querying (discover via site search)
            logger.info(f"Querying search interface...")
            search_doc_urls = self._query_search_interface(self.base_url, max_results_per_term=30)

            if search_doc_urls:
                logger.info(f"Found {len(search_doc_urls)} documents via search interface")

                for doc_url in search_doc_urls:
                    if doc_url not in seen_urls:
                        # Extract title from URL
                        from pathlib import Path
                        from urllib.parse import urlparse
                        parsed = urlparse(doc_url)
                        filename = Path(parsed.path).stem
                        title = filename.replace('-', ' ').replace('_', ' ')

                        doc_type = "pdf" if self._is_pdf_url(doc_url) else "html"

                        doc = ScrapedDocument(
                            title=self._normalize_title(title) or "Untitled",
                            url=doc_url,
                            document_type=doc_type,
                            source=self.source_name,
                            scraped_at=date.today(),
                            metadata={
                                "description": self.description,
                                "from_search": True,
                            },
                        )
                        result.documents.append(doc)
                        seen_urls.add(doc_url)

            logger.info(f"Total unique documents: {len(result.documents)}")

        except Exception as e:
            logger.error(f"{self.source_name} scraping failed: {e}", exc_info=True)
            result.errors.append(str(e))

        return result

    def _extract_documents(self, html: str, base_url: str) -> List[ScrapedDocument]:
        """Extract documents from HTML with smart detection (including tables/lists)."""
        documents = []
        seen_urls = set()  # Track within this extraction

        # Strategy 1: Extract from structured tables and lists (often more reliable)
        try:
            table_docs = self._extract_from_tables_and_lists(html, base_url, self.source_name)
            for doc in table_docs:
                if doc.url not in seen_urls:
                    documents.append(doc)
                    seen_urls.add(doc.url)
            logger.debug(f"Extracted {len(table_docs)} documents from tables/lists")
        except Exception as e:
            logger.debug(f"Table/list extraction failed: {e}")

        # Strategy 2: General link extraction (original method)
        # Blacklist of common non-document links
        blacklist_keywords = [
            'vacature', 'job', 'nieuws', 'news', 'contact', 'about', 'over',
            'home', 'homepage', 'menu', 'login', 'search', 'zoeken',
            'cookie', 'privacy', 'disclaimer', 'sitemap', 'rss', 'feed',
            'facebook', 'twitter', 'linkedin', 'instagram', 'social',
            'print', 'email', 'share', 'delen',
            'agenda', 'event', 'calendar', 'foto', 'video', 'gallery',
            'faq', 'help', 'support', 'formulier', 'form', 'thumbnail'
        ]

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            links = soup.find_all('a', href=True)

            for link in links:
                href = link['href']
                link_text = link.get_text().lower()

                # Skip navigation and blacklisted links
                if any(skip in href.lower() for skip in ['#', 'javascript:', 'mailto:', 'tel:']):
                    continue

                # Skip blacklisted non-document links
                if any(black in href.lower() or black in link_text for black in blacklist_keywords):
                    continue

                # SMART DETECTION: Multiple strategies
                is_relevant = False

                # Strategy 1: Direct PDF links (highest priority)
                if self._is_pdf_url(href):
                    is_relevant = True

                # Strategy 2: WordPress uploads directory (contains PDFs)
                elif 'wp-content/uploads/' in href.lower():
                    is_relevant = True

                # Strategy 3: Staatsblad/Law identifiers in URL or text
                elif any(pattern in href.lower() for pattern in ['s.b.', 'sb-', 'staatsblad', '/wet-', '/law-']):
                    is_relevant = True

                # Strategy 4: Year patterns in URL (e.g., /2024/, /2025/)
                elif any(f'/{year}/' in href for year in range(2000, 2030)):
                    is_relevant = True

                # Strategy 5: Keyword matching (original method)
                elif (any(keyword.lower() in href.lower() for keyword in self.keywords) or
                      any(keyword.lower() in link_text for keyword in self.keywords)):
                    is_relevant = True

                # Strategy 6: Common document patterns
                elif any(pattern in href.lower() for pattern in ['/documents/', '/documenten/', '/files/', '/bestanden/']):
                    is_relevant = True

                if is_relevant:
                    title = self._normalize_title(link.get_text())

                    if not title or len(title) < 3:
                        parent = link.find_parent(['td', 'li', 'div', 'p'])
                        if parent:
                            title = self._normalize_title(parent.get_text())

                    from urllib.parse import urljoin
                    absolute_url = urljoin(base_url, href)

                    # Skip if already found (from tables/lists)
                    if absolute_url in seen_urls:
                        continue

                    doc_type = "pdf" if self._is_pdf_url(absolute_url) else "html"
                    doc_date = self._extract_date_from_text(title)

                    doc = ScrapedDocument(
                        title=title or f"Untitled {self.source_name} Document",
                        url=absolute_url,
                        document_type=doc_type,
                        source=self.source_name,
                        date_published=doc_date,
                        scraped_at=date.today(),
                        metadata={"description": self.description},
                    )

                    documents.append(doc)
                    seen_urls.add(absolute_url)
                    logger.debug(f"Found document: {title}")

        except ImportError:
            logger.error("BeautifulSoup required. Install: pip install beautifulsoup4")
            return []
        except Exception as e:
            logger.error(f"Document extraction failed: {e}", exc_info=True)

        return documents

    def scrape_document(self, url: str) -> Optional[ScrapedDocument]:
        """Scrape specific document."""
        logger.info(f"Scraping document: {url}")

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

            doc = ScrapedDocument(
                title=title,
                url=url,
                document_type=doc_type,
                source=self.source_name,
                content=content,
                scraped_at=date.today(),
                metadata={"description": self.description},
            )

            return doc

        except Exception as e:
            logger.error(f"Failed to scrape {url}: {e}")
            return None


# Factory functions for all sources

def create_ssb_scraper(rate_limit: float = 2.0) -> GenericGovernmentScraper:
    """Surinaams Standaarden Bureau (Suriname Standards Bureau) — NOT the
    state oil company (that's Staatsolie, an unrelated entity/domain).
    ssb.sr publishes the Standaardenwet, its amendments, and technical
    regulations (labeling, food safety, product specifications) as plain
    links under /media/{id}/{filename}.pdf on a single listing page —
    no pagination, no year-based archive structure."""
    return GenericGovernmentScraper(
        base_url="https://www.ssb.sr",
        source_name="ssb",
        legislation_url="https://www.ssb.sr/over-ssb/wet-en-regelgeving/",
        keywords=["wet", "regeling", "regulation", "standaard", "standard",
                   "beschikking", "technisch voorschrift"],
        description="Suriname Standards Bureau — standards law and technical regulations",
        rate_limit=rate_limit,
    )


def create_gov_portal_scraper(rate_limit: float = 2.0) -> GenericGovernmentScraper:
    """Main Government Portal."""
    return GenericGovernmentScraper(
        base_url="https://gov.sr",
        source_name="gov_portal",
        legislation_url="https://gov.sr/ministeries/ministerie-van-binnenlandse-zaken/staats-en-advertentiebladen/",
        keywords=["wet", "law", "regeling", "regulation", "besluit", "staatsblad", "sb"],
        description="Government portal - state bulletins and consolidated laws",
        rate_limit=rate_limit,
    )


def create_justice_scraper(rate_limit: float = 2.0) -> GenericGovernmentScraper:
    """Ministry of Justice."""
    return GenericGovernmentScraper(
        base_url="https://gov.sr",
        source_name="justice",
        legislation_url="https://gov.sr/ministeries/ministerie-van-justitie-en-politie/bekendmakingen/",
        keywords=["wet", "strafrecht", "criminal", "procedural", "penitentiair", "prison", "sb", "staatsblad"],
        description="Ministry of Justice - criminal law, procedural law",
        rate_limit=rate_limit,
    )


def create_finance_scraper(rate_limit: float = 2.0) -> GenericGovernmentScraper:
    """Ministry of Finance."""
    return GenericGovernmentScraper(
        base_url="https://gov.sr",
        source_name="finance",
        legislation_url="https://gov.sr/ministeries/ministerie-van-financien/",
        keywords=["wet", "financial", "budget", "begroting", "treasury", "sb", "staatsblad"],
        description="Ministry of Finance - financial legislation",
        rate_limit=rate_limit,
    )


def create_labor_scraper(rate_limit: float = 2.0) -> GenericGovernmentScraper:
    """Ministry of Labor."""
    return GenericGovernmentScraper(
        base_url="https://gov.sr",
        source_name="labor",
        legislation_url="https://gov.sr/ministeries/ministerie-van-arbeid/",
        keywords=["arbeid", "labor", "employment", "werkgelegenheid", "safety", "veiligheid", "sb", "staatsblad"],
        description="Ministry of Labor - labor laws, employment regulations",
        rate_limit=rate_limit,
    )


def create_education_scraper(rate_limit: float = 2.0) -> GenericGovernmentScraper:
    """Ministry of Education."""
    return GenericGovernmentScraper(
        base_url="https://gov.sr",
        source_name="education",
        legislation_url="https://gov.sr/ministeries/ministerie-van-onderwijs-wetenschap-en-cultuur/",
        keywords=["onderwijs", "education", "school", "university", "universiteit", "sb", "staatsblad"],
        description="Ministry of Education - education laws",
        rate_limit=rate_limit,
    )


def create_health_scraper(rate_limit: float = 2.0) -> GenericGovernmentScraper:
    """Ministry of Health."""
    return GenericGovernmentScraper(
        base_url="https://gov.sr",
        source_name="health",
        legislation_url="https://gov.sr/ministeries/ministerie-van-volksgezondheid/",
        keywords=["gezondheid", "health", "medical", "pharmacy", "apotheek", "ziekenhuis", "sb", "staatsblad"],
        description="Ministry of Health - health laws, medical regulations",
        rate_limit=rate_limit,
    )


def create_agriculture_scraper(rate_limit: float = 2.0) -> GenericGovernmentScraper:
    """Ministry of Agriculture."""
    return GenericGovernmentScraper(
        base_url="https://gov.sr",
        source_name="agriculture",
        legislation_url="https://gov.sr/ministeries/ministerie-van-landbouw-veeteelt-en-visserij/",
        keywords=["landbouw", "agriculture", "visserij", "fishing", "veeteelt", "livestock", "sb", "staatsblad"],
        description="Ministry of Agriculture - agricultural regulations, fishing laws",
        rate_limit=rate_limit,
    )


def create_natural_resources_scraper(rate_limit: float = 2.0) -> GenericGovernmentScraper:
    """Ministry of Natural Resources."""
    return GenericGovernmentScraper(
        base_url="https://gov.sr",
        source_name="natural_resources",
        legislation_url="https://gov.sr/ministeries/ministerie-van-natuurlijke-hulpbronnen/",
        keywords=["mining", "mijnbouw", "milieu", "environment", "natuurlijke", "sb", "staatsblad"],
        description="Ministry of Natural Resources - mining law, environmental regulations",
        rate_limit=rate_limit,
    )


def create_nimos_scraper(rate_limit: float = 2.0) -> GenericGovernmentScraper:
    """NIMOS - Environmental Institute."""
    return GenericGovernmentScraper(
        base_url="https://nimos.org",
        source_name="nimos",
        legislation_url="https://nimos.org/regulations/",
        keywords=["milieu", "environment", "eia", "milieueffect", "duurzaamheid"],
        description="NIMOS - environmental regulations, EIA requirements",
        rate_limit=rate_limit,
    )


def create_kos_scraper(rate_limit: float = 2.0) -> GenericGovernmentScraper:
    """KOS - Children's Ombudsman."""
    return GenericGovernmentScraper(
        base_url="https://kos.gov.sr",
        source_name="kos",
        legislation_url="https://kos.gov.sr/wp-content/uploads/",
        keywords=["kind", "child", "ombudsman", "wet", "law", "sb", "staatsblad"],
        description="Children's Ombudsman - child protection laws",
        rate_limit=rate_limit,
    )


def create_chs_scraper(rate_limit: float = 2.0) -> GenericGovernmentScraper:
    """CHS - Central Electoral Bureau."""
    return GenericGovernmentScraper(
        base_url="https://chs.gov.sr",
        source_name="chs",
        legislation_url="https://chs.gov.sr/wp-content/uploads/",
        keywords=["verkiezing", "election", "electoral", "wet", "law", "sb", "staatsblad"],
        description="Central Electoral Bureau - election laws",
        rate_limit=rate_limit,
    )


# Export factory functions
__all__ = [
    "GenericGovernmentScraper",
    "create_ssb_scraper",
    "create_gov_portal_scraper",
    "create_justice_scraper",
    "create_finance_scraper",
    "create_labor_scraper",
    "create_education_scraper",
    "create_health_scraper",
    "create_agriculture_scraper",
    "create_natural_resources_scraper",
    "create_nimos_scraper",
    "create_kos_scraper",
    "create_chs_scraper",
]
