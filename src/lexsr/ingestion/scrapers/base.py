"""
Base scraper infrastructure for Suriname government websites.

Provides common functionality for:
- HTTP requests with proper headers
- Rate limiting and retries
- PDF/HTML detection
- Link extraction
- Error handling
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


@dataclass
class ScrapedDocument:
    """A document discovered by scraping."""
    title: str
    url: str
    document_type: str  # "pdf", "html", "unknown"
    source: str  # "dna", "belastingdienst", etc.

    # Optional metadata
    date_published: Optional[date] = None
    description: Optional[str] = None
    category: Optional[str] = None
    official_id: Optional[str] = None

    # Content
    content: Optional[bytes] = None  # Raw PDF/HTML content
    local_path: Optional[Path] = None

    # Tracking
    scraped_at: Optional[date] = None
    metadata: Dict[str, any] = field(default_factory=dict)


@dataclass
class ScrapeResult:
    """Result of a scraping operation."""
    documents: List[ScrapedDocument] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, any] = field(default_factory=dict)


class BaseScraper(ABC):
    """
    Base class for government website scrapers.

    Handles:
    - HTTP requests with retries
    - Rate limiting
    - Common extraction patterns
    - Error handling
    """

    def __init__(
        self,
        base_url: str,
        source_name: str,
        rate_limit: float = 1.0,  # Seconds between requests
        max_retries: int = 3,
        timeout: int = 30,
    ):
        """
        Initialize scraper.

        Args:
            base_url: Base URL of the website
            source_name: Name of the source (e.g., "dna", "belastingdienst")
            rate_limit: Minimum seconds between requests
            max_retries: Maximum number of retries on failure
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.source_name = source_name
        self.rate_limit = rate_limit
        self.max_retries = max_retries
        self.timeout = timeout

        # Request tracking
        self._last_request_time = 0.0
        self._visited_urls: Set[str] = set()

        # User agent - identify as a legal research bot
        self.headers = {
            'User-Agent': 'LexSR-Bot/1.0 (Suriname Legal Research; +https://github.com/yourusername/wetten-van-suriname)',
            'Accept': 'text/html,application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'nl,en;q=0.9',
        }

    def _wait_for_rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit:
            wait_time = self.rate_limit - elapsed
            logger.debug(f"Rate limiting: waiting {wait_time:.2f}s")
            time.sleep(wait_time)
        self._last_request_time = time.time()

    def _fetch_url(self, url: str, method: str = "GET") -> Optional[bytes]:
        """
        Fetch URL with retries and rate limiting.

        Args:
            url: URL to fetch
            method: HTTP method

        Returns:
            Response content as bytes, or None on failure
        """
        # Check if already visited
        if url in self._visited_urls:
            logger.debug(f"Already visited: {url}")
            return None

        self._visited_urls.add(url)

        for attempt in range(self.max_retries):
            try:
                self._wait_for_rate_limit()

                logger.info(f"Fetching: {url} (attempt {attempt + 1}/{self.max_retries})")

                # Use requests if available, otherwise urllib
                try:
                    import requests
                    response = requests.get(
                        url,
                        headers=self.headers,
                        timeout=self.timeout,
                        allow_redirects=True,
                    )
                    response.raise_for_status()
                    return response.content

                except ImportError:
                    # Fallback to urllib
                    import urllib.request
                    req = urllib.request.Request(url, headers=self.headers)
                    with urllib.request.urlopen(req, timeout=self.timeout) as response:
                        return response.read()

            except Exception as e:
                logger.warning(f"Fetch failed (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to fetch {url} after {self.max_retries} attempts")
                    return None

        return None

    def _is_pdf_url(self, url: str) -> bool:
        """Check if URL likely points to a PDF (enhanced detection)."""
        url_lower = url.lower()
        return (
            url_lower.endswith('.pdf') or
            '/pdf/' in url_lower or
            '.pdf?' in url_lower or  # PDFs with query strings
            'pdf=' in url_lower or   # PDF parameter
            'file=.pdf' in url_lower or
            '/wp-content/uploads/' in url_lower  # WordPress uploads often contain PDFs
        )

    def _extract_links(self, html: str, base_url: str) -> List[str]:
        """
        Extract all links from HTML.

        Args:
            html: HTML content
            base_url: Base URL for resolving relative links

        Returns:
            List of absolute URLs
        """
        links = []

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            for a in soup.find_all('a', href=True):
                href = a['href']
                absolute_url = urljoin(base_url, href)
                links.append(absolute_url)

        except ImportError:
            # Fallback to regex if BeautifulSoup not available
            import re
            pattern = r'href=["\']([^"\']+)["\']'
            matches = re.findall(pattern, html)
            links = [urljoin(base_url, m) for m in matches]

        return links

    def _extract_text(self, html: str, selector: Optional[str] = None) -> str:
        """
        Extract text from HTML, optionally using a CSS selector.

        Args:
            html: HTML content
            selector: Optional CSS selector

        Returns:
            Extracted text
        """
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            if selector:
                element = soup.select_one(selector)
                return element.get_text(strip=True) if element else ""
            else:
                return soup.get_text(strip=True)

        except ImportError:
            # Fallback: basic HTML tag removal
            import re
            text = re.sub(r'<[^>]+>', '', html)
            return text.strip()

    def _normalize_title(self, title: str) -> str:
        """Normalize document title."""
        # Remove extra whitespace
        title = ' '.join(title.split())

        # Common cleanup
        title = title.replace('\n', ' ').replace('\r', '')

        return title.strip()

    def _extract_date_from_text(self, text: str) -> Optional[date]:
        """
        Extract date from text using common Dutch patterns.

        Patterns:
        - "15 januari 2024"
        - "2024-01-15"
        - "15-01-2024"
        - "01/15/2024"
        """
        import re
        from datetime import datetime

        # Dutch month names
        months_nl = {
            'januari': 1, 'februari': 2, 'maart': 3, 'april': 4,
            'mei': 5, 'juni': 6, 'juli': 7, 'augustus': 8,
            'september': 9, 'oktober': 10, 'november': 11, 'december': 12,
        }

        # Pattern: "15 januari 2024"
        for month_name, month_num in months_nl.items():
            pattern = rf'(\d{{1,2}})\s+{month_name}\s+(\d{{4}})'
            match = re.search(pattern, text.lower())
            if match:
                day = int(match.group(1))
                year = int(match.group(2))
                try:
                    return date(year, month_num, day)
                except ValueError:
                    pass

        # Pattern: ISO date "2024-01-15"
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass

        # Pattern: "15-01-2024" or "15/01/2024"
        match = re.search(r'(\d{2})[-/](\d{2})[-/](\d{4})', text)
        if match:
            try:
                return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
            except ValueError:
                pass

        return None

    def _fetch_wordpress_posts(
        self,
        base_url: str,
        max_pages: int = 10,
        per_page: int = 100,
    ) -> List[Dict[str, any]]:
        """
        Fetch posts from WordPress REST API.

        Args:
            base_url: Base URL of WordPress site
            max_pages: Maximum pages to fetch
            per_page: Posts per page (max 100)

        Returns:
            List of post dictionaries with: title, link, date, content, excerpt
        """
        posts = []

        try:
            import requests
        except ImportError:
            logger.warning("requests library not available, skipping WordPress API")
            return []

        for page in range(1, max_pages + 1):
            try:
                self._wait_for_rate_limit()

                # Query WordPress REST API
                api_url = f"{base_url}/wp-json/wp/v2/posts"
                params = {
                    "page": page,
                    "per_page": per_page,
                    "_embed": "true",  # Include embedded data (attachments, media)
                }

                logger.debug(f"Querying WordPress API: {api_url} (page {page})")
                response = requests.get(api_url, params=params, timeout=self.timeout)

                # Check if WordPress API is available
                if response.status_code == 404:
                    logger.debug(f"WordPress API not found at {base_url}")
                    return []

                if response.status_code != 200:
                    logger.warning(f"WordPress API returned {response.status_code}")
                    break

                data = response.json()
                if not data:
                    # No more posts
                    break

                # Extract relevant post data
                for post in data:
                    try:
                        # Check if post is document-related
                        title = post.get("title", {}).get("rendered", "")
                        content = post.get("content", {}).get("rendered", "")
                        excerpt = post.get("excerpt", {}).get("rendered", "")

                        # Look for document indicators in title or content
                        combined_text = (title + " " + excerpt).lower()
                        is_document = any(
                            keyword in combined_text
                            for keyword in [
                                "wet", "law", "staatsblad", "s.b.", "g.b.",
                                "besluit", "decree", "regeling", "regulation",
                                "pdf", "download", "document"
                            ]
                        )

                        if is_document or self._has_pdf_in_content(content):
                            posts.append({
                                "title": title,
                                "link": post.get("link"),
                                "date": post.get("date"),
                                "content": content,
                                "excerpt": excerpt,
                            })

                    except Exception as e:
                        logger.warning(f"Failed to process post: {e}")
                        continue

                logger.debug(f"  Page {page}: Found {len(data)} posts")

            except requests.exceptions.RequestException as e:
                logger.warning(f"WordPress API request failed (page {page}): {e}")
                break
            except Exception as e:
                logger.warning(f"WordPress API processing failed (page {page}): {e}")
                break

        logger.info(f"Fetched {len(posts)} document-related posts from WordPress API")
        return posts

    def _has_pdf_in_content(self, html_content: str) -> bool:
        """Check if HTML content contains PDF links."""
        if not html_content:
            return False

        content_lower = html_content.lower()
        return (
            ".pdf" in content_lower or
            "application/pdf" in content_lower or
            "wp-content/uploads" in content_lower
        )

    def _crawl_year_directories(
        self,
        base_url: str,
        year_range: Optional[tuple[int, int]] = None,
    ) -> List[str]:
        """
        Crawl year-based directory structures for documents.

        Tries common patterns like:
        - /wetgeving/YYYY/
        - /documents/YYYY/
        - /staatsblad/YYYY/
        - /wp-content/uploads/YYYY/

        Args:
            base_url: Base URL to crawl
            year_range: Tuple of (start_year, end_year), defaults to (2000, current_year)

        Returns:
            List of discovered document URLs
        """
        from datetime import datetime

        if year_range is None:
            current_year = datetime.now().year
            year_range = (2000, current_year)

        document_urls = set()

        # Common year-based directory patterns
        patterns = [
            "wetgeving/{year}",
            "documents/{year}",
            "documenten/{year}",
            "staatsblad/{year}",
            "staatsbladden/{year}",
            "wp-content/uploads/{year}",
            "publicaties/{year}",
            "wetten/{year}",
            "{year}",  # Direct year path
        ]

        logger.info(f"Crawling year directories from {year_range[0]} to {year_range[1]}")

        for year in range(year_range[0], year_range[1] + 1):
            for pattern in patterns:
                try:
                    # Build year-based URL
                    year_path = pattern.format(year=year)
                    year_url = urljoin(base_url, year_path)

                    # Ensure trailing slash for directory
                    if not year_url.endswith('/'):
                        year_url += '/'

                    # Try to fetch this year directory
                    content = self._fetch_url(year_url)
                    if not content:
                        # 404 or already visited
                        continue

                    logger.debug(f"Found year directory: {year_url}")

                    # Extract and filter document links
                    html = content.decode('utf-8', errors='ignore')
                    links = self._extract_links(html, year_url)

                    # Filter for document-related links
                    for link in links:
                        link_lower = link.lower()

                        # Skip navigation and non-document links
                        if any(skip in link_lower for skip in ['#', 'javascript:', 'mailto:', 'tel:']):
                            continue

                        # Check if it's a document link
                        is_document = (
                            self._is_pdf_url(link) or
                            any(keyword in link_lower for keyword in [
                                'wet', 'law', 'staatsblad', 's.b.', 'g.b.',
                                'besluit', 'decree', 'regeling', 'pdf',
                                'document', '/wp-content/uploads/'
                            ])
                        )

                        if is_document:
                            document_urls.add(link)

                    logger.debug(f"  Found {len(links)} links in {year_url}")

                except Exception as e:
                    logger.debug(f"Failed to crawl {year_path}: {e}")
                    continue

        logger.info(f"Year directory crawl found {len(document_urls)} document URLs")
        return list(document_urls)

    def _extract_from_tables_and_lists(
        self,
        html: str,
        base_url: str,
        source_name: str,
    ) -> List[ScrapedDocument]:
        """
        Extract documents from HTML tables and lists.

        Government sites often list laws in structured tables or lists.
        This method extracts document links with associated metadata.

        Args:
            html: HTML content to parse
            base_url: Base URL for resolving relative links
            source_name: Source identifier for documents

        Returns:
            List of ScrapedDocument objects
        """
        documents = []

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # Extract from tables
            tables = soup.find_all('table')
            logger.debug(f"Found {len(tables)} tables")

            for table in tables:
                rows = table.find_all('tr')

                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if not cells:
                        continue

                    # Look for links in this row
                    links = row.find_all('a', href=True)

                    for link in links:
                        href = link['href']

                        # Skip navigation links
                        if any(skip in href.lower() for skip in ['#', 'javascript:', 'mailto:', 'tel:']):
                            continue

                        # Check if it's a document link
                        is_document = (
                            self._is_pdf_url(href) or
                            any(keyword in href.lower() for keyword in [
                                'wet', 'law', 'staatsblad', 's.b.', 'g.b.',
                                'besluit', 'document', 'publicatie'
                            ])
                        )

                        if is_document:
                            # Extract title from link text
                            title = self._normalize_title(link.get_text())

                            # If title is too short, try to get from entire row
                            if not title or len(title) < 5:
                                title = self._normalize_title(row.get_text())

                            # Extract date from row cells
                            row_text = row.get_text()
                            doc_date = self._extract_date_from_text(row_text)

                            # Build absolute URL
                            absolute_url = urljoin(base_url, href)
                            doc_type = "pdf" if self._is_pdf_url(absolute_url) else "html"

                            doc = ScrapedDocument(
                                title=title or "Untitled",
                                url=absolute_url,
                                document_type=doc_type,
                                source=source_name,
                                date_published=doc_date,
                                scraped_at=date.today(),
                                metadata={"extracted_from": "table"},
                            )

                            documents.append(doc)

            # Extract from lists (ul, ol)
            lists = soup.find_all(['ul', 'ol'])
            logger.debug(f"Found {len(lists)} lists")

            for lst in lists:
                items = lst.find_all('li')

                for item in items:
                    links = item.find_all('a', href=True)

                    for link in links:
                        href = link['href']

                        # Skip navigation links
                        if any(skip in href.lower() for skip in ['#', 'javascript:', 'mailto:', 'tel:']):
                            continue

                        # Check if it's a document link
                        is_document = (
                            self._is_pdf_url(href) or
                            any(keyword in href.lower() for keyword in [
                                'wet', 'law', 'staatsblad', 's.b.', 'g.b.',
                                'besluit', 'document', 'publicatie'
                            ])
                        )

                        if is_document:
                            # Extract title from link text or list item
                            title = self._normalize_title(link.get_text())
                            if not title or len(title) < 5:
                                title = self._normalize_title(item.get_text())

                            # Extract date
                            item_text = item.get_text()
                            doc_date = self._extract_date_from_text(item_text)

                            # Build absolute URL
                            absolute_url = urljoin(base_url, href)
                            doc_type = "pdf" if self._is_pdf_url(absolute_url) else "html"

                            doc = ScrapedDocument(
                                title=title or "Untitled",
                                url=absolute_url,
                                document_type=doc_type,
                                source=source_name,
                                date_published=doc_date,
                                scraped_at=date.today(),
                                metadata={"extracted_from": "list"},
                            )

                            documents.append(doc)

            logger.debug(f"Extracted {len(documents)} documents from tables and lists")

        except ImportError:
            logger.warning("BeautifulSoup not available for table/list extraction")
            return []
        except Exception as e:
            logger.warning(f"Table/list extraction failed: {e}")
            return []

        return documents

    def _find_pagination_urls(self, html: str, current_url: str, max_pages: int = 50) -> List[str]:
        """
        Find all pagination URLs from HTML content.

        Detects:
        - "Next", "Volgende", "→", "»" links
        - Numeric page links (1, 2, 3, ...)
        - page=N, p=N parameters

        Args:
            html: HTML content to parse
            current_url: Current page URL
            max_pages: Maximum pages to discover

        Returns:
            List of URLs for paginated pages (excluding current)
        """
        urls = []

        try:
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

            soup = BeautifulSoup(html, 'html.parser')

            # Pagination link patterns
            next_patterns = ['next', 'volgende', 'verder', '→', '»', '›', 'next page']
            numeric_found = set()

            for link in soup.find_all('a', href=True):
                href = link.get('href')
                text = link.get_text().strip().lower()

                # Strategy 1: "Next" button links
                if any(pattern in text for pattern in next_patterns):
                    absolute_url = urljoin(current_url, href)
                    if absolute_url not in urls and absolute_url != current_url:
                        urls.append(absolute_url)

                # Strategy 2: Numeric page links
                if text.isdigit():
                    page_num = int(text)
                    if page_num <= max_pages and page_num not in numeric_found:
                        absolute_url = urljoin(current_url, href)
                        if absolute_url not in urls:
                            urls.append(absolute_url)
                            numeric_found.add(page_num)

                # Strategy 3: page= or p= parameters in URL
                parsed = urlparse(href)
                params = parse_qs(parsed.query)
                if 'page' in params or 'p' in params:
                    absolute_url = urljoin(current_url, href)
                    if absolute_url not in urls and absolute_url != current_url:
                        urls.append(absolute_url)

            # Strategy 4: Generate page URLs if pattern detected
            # e.g., /documents/page/2/, /documents/?page=2
            parsed_current = urlparse(current_url)

            # Check for /page/N/ pattern
            if '/page/' in parsed_current.path:
                base_path = parsed_current.path.split('/page/')[0]
                for page_num in range(2, min(max_pages + 1, 11)):  # Try up to 10 pages
                    page_url = f"{parsed_current.scheme}://{parsed_current.netloc}{base_path}/page/{page_num}/"
                    if page_url not in urls:
                        urls.append(page_url)

            logger.debug(f"Found {len(urls)} pagination URLs")

        except Exception as e:
            logger.error(f"Pagination URL discovery failed: {e}")

        return urls[:max_pages]  # Limit total pages

    def _query_search_interface(
        self,
        base_url: str,
        search_terms: Optional[List[str]] = None,
        max_results_per_term: int = 50,
    ) -> List[str]:
        """
        Query website search interface for documents.

        Tries common search URL patterns and extracts document links
        from search results.

        Args:
            base_url: Base URL of website
            search_terms: List of terms to search for (defaults to legal terms)
            max_results_per_term: Maximum results to collect per search term

        Returns:
            List of discovered document URLs
        """
        from urllib.parse import quote_plus

        # Default search terms for Suriname legal documents
        if search_terms is None:
            search_terms = [
                "staatsblad",
                "wet",
                "besluit",
                "S.B.",
                "G.B.",
                "regeling",
                "law",
            ]

        discovered_urls = set()

        # Common search URL patterns
        search_patterns = [
            "?s={term}",           # WordPress
            "/search?q={term}",    # Generic
            "/zoeken?query={term}",  # Dutch
            "/?search={term}",     # Alternative
        ]

        logger.info(f"Querying search interface with {len(search_terms)} terms...")

        for term in search_terms:
            # URL-encode the search term
            encoded_term = quote_plus(term)

            for pattern in search_patterns:
                try:
                    # Build search URL
                    search_path = pattern.format(term=encoded_term)
                    search_url = urljoin(base_url, search_path)

                    logger.debug(f"Trying search: {search_url}")

                    # Fetch search results page
                    content = self._fetch_url(search_url)
                    if not content:
                        # 404 or already visited
                        continue

                    logger.debug(f"Search interface responded: {search_url}")

                    html = content.decode('utf-8', errors='ignore')

                    # Extract document links from search results
                    links = self._extract_links(html, search_url)

                    # Filter for document-related links
                    doc_links = []
                    for link in links:
                        link_lower = link.lower()

                        # Skip navigation and non-document links
                        if any(skip in link_lower for skip in ['#', 'javascript:', 'mailto:', 'tel:']):
                            continue

                        # Check if it's a document link
                        is_document = (
                            self._is_pdf_url(link) or
                            any(keyword in link_lower for keyword in [
                                'wet', 'law', 'staatsblad', 's.b.', 'g.b.',
                                'besluit', 'decree', 'regeling', 'document',
                                '/wp-content/uploads/', 'publicatie'
                            ])
                        )

                        if is_document:
                            doc_links.append(link)

                    if doc_links:
                        logger.info(f"  Search '{term}': Found {len(doc_links)} documents")
                        discovered_urls.update(doc_links[:max_results_per_term])

                        # If we found results with this pattern, no need to try others
                        break

                except Exception as e:
                    logger.debug(f"Search query failed for '{term}' with pattern '{pattern}': {e}")
                    continue

        logger.info(f"Search interface query found {len(discovered_urls)} unique document URLs")
        return list(discovered_urls)

    @abstractmethod
    def scrape(self) -> ScrapeResult:
        """
        Scrape the website for documents.

        Returns:
            ScrapeResult with discovered documents
        """
        pass

    @abstractmethod
    def scrape_document(self, url: str) -> Optional[ScrapedDocument]:
        """
        Scrape a specific document.

        Args:
            url: URL of the document

        Returns:
            ScrapedDocument or None on failure
        """
        pass
