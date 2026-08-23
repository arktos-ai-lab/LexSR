"""
Batch processing orchestrator for ingestion pipeline.

Workflow:
1. Scrape government websites for documents
2. Download PDFs/HTML
3. Process through OCR pipeline
4. Convert to FRBR models
5. Store in canonical database
6. Index for search

This ties together: scrapers → OCR → FRBR → storage → search

Supports:
- Sequential processing (default)
- Parallel processing (multiple scrapers at once)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..core.store import CanonicalStore
from ..ocr.pipeline import OCRPipeline, PipelineConfig, PipelineResult
from .scrapers import ScrapedDocument, ScrapeResult

logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    """Result of batch processing."""
    total_scraped: int = 0
    total_downloaded: int = 0
    total_processed: int = 0
    total_stored: int = 0
    total_indexed: int = 0

    successful: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    metadata: Dict[str, any] = field(default_factory=dict)


class BatchProcessor:
    """
    Orchestrates the complete ingestion pipeline.

    Usage:
        processor = BatchProcessor(
            raw_dir=Path("data/raw"),
            canonical_db="data/canonical.db",
            search_db="data/search.db",
        )

        # Scrape DNA website
        from lexsr.ingestion.scrapers import DNAScraper

        scraper = DNAScraper()
        result = processor.process_scraper(scraper, limit=10)

        print(f"Processed {result.total_processed} documents")
    """

    def __init__(
        self,
        raw_dir: Path,
        canonical_db: str,
        search_db: Optional[str] = None,
        ocr_config: Optional[PipelineConfig] = None,
    ):
        """
        Initialize batch processor.

        Args:
            raw_dir: Directory for raw downloads
            canonical_db: Path to canonical store database
            search_db: Path to search database (optional)
            ocr_config: OCR pipeline configuration (optional)
        """
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.store = CanonicalStore(canonical_db)
        self.ocr_pipeline = OCRPipeline(config=ocr_config)
        self.search_db = search_db

    def process_scraper(
        self,
        scraper,
        limit: Optional[int] = None,
        skip_existing: bool = True,
    ) -> BatchResult:
        """
        Process all documents from a scraper.

        Args:
            scraper: Scraper instance (e.g., DNAScraper())
            limit: Maximum number of documents to process (None = all)
            skip_existing: Skip documents already in database

        Returns:
            BatchResult with statistics
        """
        logger.info(f"Starting batch processing from {scraper.source_name}")

        result = BatchResult()

        try:
            # Step 1: Scrape website
            logger.info("Step 1: Scraping website...")
            scrape_result = scraper.scrape()
            result.total_scraped = len(scrape_result.documents)
            result.errors.extend(scrape_result.errors)
            result.warnings.extend(scrape_result.warnings)

            logger.info(f"Scraped {result.total_scraped} documents")

            # Limit if requested
            documents = scrape_result.documents[:limit] if limit else scrape_result.documents

            # Step 2: Download documents concurrently (faster)
            logger.info("Step 2: Downloading documents concurrently...")
            initial_failed_count = len(result.failed)
            downloaded_docs = self._download_documents_concurrent(scraper, documents, skip_existing, result)

            # Step 2.5: Retry failed downloads
            failed_titles = result.failed[initial_failed_count:]  # Get newly failed ones
            if failed_titles:
                # Find failed documents from original list
                failed_docs = [doc for doc in documents if doc.title in failed_titles]

                if failed_docs:
                    logger.info(f"Step 2.5: Retrying {len(failed_docs)} failed downloads...")
                    retried_docs = self._retry_failed_downloads(scraper, failed_docs, max_retry_attempts=2)

                    if retried_docs:
                        downloaded_docs.extend(retried_docs)
                        logger.info(f"Recovered {len(retried_docs)} documents via retry")

            # Use downloaded docs for processing
            documents = downloaded_docs

            # Step 2.6: Filter out documents that already exist in database
            if skip_existing:
                logger.info("Step 2.6: Filtering out existing documents...")
                filtered_docs = []
                for doc in documents:
                    if not self._document_exists(doc):
                        filtered_docs.append(doc)
                    else:
                        logger.debug(f"Skipping (exists): {doc.title[:50]}...")
                        result.warnings.append(f"Skipped (exists): {doc.title}")

                if len(documents) > len(filtered_docs):
                    logger.info(f"Filtered out {len(documents) - len(filtered_docs)} existing documents")
                documents = filtered_docs

            # Step 2.7: Deduplicate by content hash (find identical docs with different URLs)
            logger.info("Step 2.7: Deduplicating by content hash...")
            original_count = len(documents)
            documents = self._deduplicate_by_hash(documents)
            if len(documents) < original_count:
                logger.info(f"Removed {original_count - len(documents)} duplicate documents")

            # Step 3: Process each downloaded document
            for i, doc in enumerate(documents, 1):
                logger.info(f"Processing {i}/{len(documents)}: {doc.title}")

                try:
                    # Skip if download failed (marked with None content)
                    if doc.content is None:
                        logger.warning("  ⊘ Skipping (download failed or already exists)")
                        continue

                    # Save to raw directory
                    source_dir = self.raw_dir / doc.source
                    local_path = self._save_document(doc, source_dir)

                    if not local_path:
                        logger.error("  ✗ Save failed")
                        result.failed.append(doc.title)
                        continue

                    # Process through OCR pipeline (if PDF)
                    if doc.document_type == "pdf":
                        logger.info("  📄 OCR processing...")
                        ocr_result = self._process_pdf(doc, local_path)

                        if ocr_result and ocr_result.success:
                            logger.info(f"  ✓ OCR complete: {len(ocr_result.fragments)} fragments")
                            result.total_processed += 1

                            # Store in canonical database
                            self._store_result(ocr_result)
                            result.total_stored += 1

                            # Index for search
                            if self.search_db:
                                self._index_result(ocr_result)
                                result.total_indexed += 1

                            result.successful.append(doc.title)
                        else:
                            logger.error("  ✗ OCR failed")
                            result.failed.append(doc.title)
                            if ocr_result:
                                result.errors.extend(ocr_result.errors)
                    else:
                        # HTML content - extract PDF links and process them
                        logger.info("  📄 Processing HTML page for PDF links...")
                        pdf_docs = self._extract_pdfs_from_html(doc)

                        if pdf_docs:
                            logger.info(f"  ✓ Found {len(pdf_docs)} PDFs in HTML page")

                            for pdf_doc in pdf_docs:
                                # Process each PDF
                                try:
                                    pdf_path = self._save_document(pdf_doc, source_dir)
                                    if pdf_path:
                                        ocr_result = self._process_pdf(pdf_doc, pdf_path)

                                        if ocr_result and ocr_result.success:
                                            result.total_processed += 1
                                            self._store_result(ocr_result)
                                            result.total_stored += 1

                                            if self.search_db:
                                                self._index_result(ocr_result)
                                                result.total_indexed += 1

                                            result.successful.append(pdf_doc.title)
                                        else:
                                            result.failed.append(pdf_doc.title)
                                except Exception as e:
                                    logger.error(f"  ✗ PDF processing failed: {e}")
                                    result.failed.append(pdf_doc.title)
                        else:
                            logger.warning("  ⚠ No PDFs found in HTML page")
                            result.warnings.append(f"No PDFs in HTML: {doc.title}")

                except Exception as e:
                    logger.error(f"  ✗ Processing failed: {e}", exc_info=True)
                    result.failed.append(doc.title)
                    result.errors.append(f"{doc.title}: {str(e)}")

            logger.info(f"Batch processing complete: {result.total_processed}/{len(documents)} successful")

        except Exception as e:
            logger.error(f"Batch processing failed: {e}", exc_info=True)
            result.errors.append(str(e))

        return result

    def _document_exists(self, doc: ScrapedDocument) -> bool:
        """
        Check if document already exists in database.

        Uses multiple strategies:
        1. Check by source URL (exact match)
        2. Check by title + source combination
        3. Check by content hash (if content available)

        Returns:
            True if duplicate found, False if new document
        """
        import sqlite3
        import hashlib

        try:
            # Strategy 1: Check by source URL
            if doc.url:
                result = self.store._conn.execute(
                    """
                    SELECT COUNT(*) FROM expressions
                    WHERE metadata LIKE ?
                    """,
                    (f'%"source_url": "{doc.url}"%',)
                ).fetchone()

                if result and result[0] > 0:
                    logger.debug(f"Duplicate found by URL: {doc.url}")
                    return True

            # Strategy 2: Check by title + source
            if doc.title and doc.source:
                # Normalize title (remove extra whitespace, lowercase)
                normalized_title = ' '.join(doc.title.lower().split())

                # Check in works table
                result = self.store._conn.execute(
                    """
                    SELECT COUNT(*) FROM works w
                    JOIN expressions e ON w.id = e.work_id
                    WHERE LOWER(REPLACE(w.title, '  ', ' ')) = ?
                    AND e.metadata LIKE ?
                    """,
                    (normalized_title, f'%"source": "{doc.source}"%')
                ).fetchone()

                if result and result[0] > 0:
                    logger.debug(f"Duplicate found by title+source: {doc.title}")
                    return True

            # Strategy 3: Check by content hash
            if doc.content:
                content_hash = hashlib.sha256(doc.content).hexdigest()

                result = self.store._conn.execute(
                    """
                    SELECT COUNT(*) FROM expressions
                    WHERE metadata LIKE ?
                    """,
                    (f'%"content_hash": "{content_hash}"%',)
                ).fetchone()

                if result and result[0] > 0:
                    logger.debug(f"Duplicate found by content hash: {content_hash[:16]}...")
                    return True

            # Not a duplicate
            return False

        except Exception as e:
            logger.error(f"Duplicate check failed: {e}")
            # On error, assume not duplicate to avoid skipping valid docs
            return False

    def _download_documents_concurrent(
        self,
        scraper,
        documents: List[ScrapedDocument],
        skip_existing: bool,
        result: BatchResult,
        max_workers: int = 8,
    ) -> List[ScrapedDocument]:
        """
        Download documents concurrently using ThreadPoolExecutor.

        Args:
            scraper: Scraper instance to use for downloading
            documents: List of documents to download
            skip_existing: Whether to skip documents already in database
            result: BatchResult to update with download statistics
            max_workers: Number of concurrent download threads (default 8)

        Returns:
            List of documents with content (excludes failed downloads)
        """
        def download_single(doc: ScrapedDocument) -> Optional[ScrapedDocument]:
            """Download a single document."""
            try:
                # NOTE: Skip duplicate check here due to SQLite threading issues
                # Duplicate check will happen after downloads complete (in main thread)

                # Download if content not already present
                if doc.content is None:
                    downloaded_doc = scraper.scrape_document(doc.url)
                    if downloaded_doc and downloaded_doc.content:
                        logger.debug(f"[OK] Downloaded: {doc.title[:50]}...")
                        return downloaded_doc
                    else:
                        logger.warning(f"[X] Download failed: {doc.title[:50]}...")
                        result.failed.append(doc.title)
                        result.errors.append(f"Download failed: {doc.title}")
                        return None
                else:
                    # Content already present
                    return doc

            except Exception as e:
                logger.error(f"[X] Download error ({doc.title[:50]}...): {e}")
                result.failed.append(doc.title)
                result.errors.append(f"Download error ({doc.title}): {str(e)}")
                return None

        logger.info(f"Downloading {len(documents)} documents using {max_workers} workers...")

        downloaded_docs = []
        successful = 0
        failed = 0

        # Use ThreadPoolExecutor for concurrent downloads
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all download tasks
            future_to_doc = {
                executor.submit(download_single, doc): doc
                for doc in documents
            }

            # Collect results as they complete
            for i, future in enumerate(as_completed(future_to_doc), 1):
                original_doc = future_to_doc[future]

                try:
                    downloaded_doc = future.result()

                    if downloaded_doc:
                        downloaded_docs.append(downloaded_doc)
                        successful += 1
                        result.total_downloaded += 1
                    else:
                        failed += 1

                    # Progress update every 10 documents
                    if i % 10 == 0:
                        logger.info(f"  Progress: {i}/{len(documents)} - {successful} OK, {failed} failed")

                except Exception as e:
                    logger.error(f"Future exception for {original_doc.title}: {e}")
                    failed += 1
                    result.failed.append(original_doc.title)
                    result.errors.append(f"Download exception ({original_doc.title}): {str(e)}")

        logger.info(f"Download complete: {successful} successful, {failed} failed/skipped")

        return downloaded_docs

    def _retry_failed_downloads(
        self,
        scraper,
        failed_documents: List[ScrapedDocument],
        max_retry_attempts: int = 2,
    ) -> List[ScrapedDocument]:
        """
        Retry failed downloads with exponential backoff.

        Args:
            scraper: Scraper instance to use
            failed_documents: List of documents that failed to download
            max_retry_attempts: Maximum retry attempts per document

        Returns:
            List of successfully downloaded documents
        """
        import time

        if not failed_documents:
            return []

        logger.info(f"Retrying {len(failed_documents)} failed downloads (up to {max_retry_attempts} attempts)...")

        successful_retries = []
        permanently_failed = []

        for attempt in range(1, max_retry_attempts + 1):
            # Wait before retry (exponential backoff: 5s, 15s, 45s, ...)
            if attempt > 1:
                wait_time = 5 * (3 ** (attempt - 2))  # 5, 15, 45 seconds...
                logger.info(f"Waiting {wait_time}s before retry attempt {attempt}...")
                time.sleep(wait_time)

            logger.info(f"Retry attempt {attempt}/{max_retry_attempts}...")

            # Track what still needs retrying
            still_failed = []

            for i, doc in enumerate(failed_documents, 1):
                try:
                    logger.debug(f"  [{i}/{len(failed_documents)}] Retrying: {doc.title[:50]}...")

                    # Attempt download
                    downloaded_doc = scraper.scrape_document(doc.url)

                    if downloaded_doc and downloaded_doc.content:
                        logger.info(f"  [OK] Retry successful: {doc.title[:50]}...")
                        successful_retries.append(downloaded_doc)
                    else:
                        logger.debug(f"  [X] Retry failed: {doc.title[:50]}...")
                        still_failed.append(doc)

                except Exception as e:
                    logger.debug(f"  [X] Retry error: {doc.title[:50]}... ({e})")
                    still_failed.append(doc)

            logger.info(f"  Attempt {attempt}: {len(successful_retries)} recovered, {len(still_failed)} still failing")

            # Update list for next attempt
            failed_documents = still_failed

            # If all succeeded, stop retrying
            if not failed_documents:
                break

        # Documents that failed all retry attempts
        permanently_failed = failed_documents

        if permanently_failed:
            logger.warning(f"{len(permanently_failed)} documents failed permanently after {max_retry_attempts} retry attempts")
            for doc in permanently_failed[:5]:  # Show first 5
                logger.warning(f"  - {doc.title[:50]}...")

        logger.info(f"Retry complete: {len(successful_retries)} recovered, {len(permanently_failed)} permanent failures")

        return successful_retries

    def _compute_content_hash(self, content: bytes) -> str:
        """
        Compute SHA-256 hash of content.

        Args:
            content: Raw bytes content

        Returns:
            Hex digest of SHA-256 hash
        """
        import hashlib
        return hashlib.sha256(content).hexdigest()

    def _deduplicate_by_hash(
        self,
        documents: List[ScrapedDocument],
    ) -> List[ScrapedDocument]:
        """
        Deduplicate documents by content hash.

        Computes hash for each document and removes duplicates.
        Useful for finding identical PDFs with different URLs/titles.

        Args:
            documents: List of documents to deduplicate

        Returns:
            Deduplicated list of documents
        """
        seen_hashes = set()
        deduplicated = []
        duplicates_found = 0

        for doc in documents:
            # Compute hash if content available
            if doc.content:
                content_hash = self._compute_content_hash(doc.content)

                # Store hash in metadata
                if not doc.metadata:
                    doc.metadata = {}
                doc.metadata["content_hash"] = content_hash

                # Check for duplicate
                if content_hash in seen_hashes:
                    logger.debug(f"Duplicate detected (hash): {doc.title[:50]}...")
                    duplicates_found += 1
                    continue

                seen_hashes.add(content_hash)

            deduplicated.append(doc)

        if duplicates_found > 0:
            logger.info(f"Removed {duplicates_found} duplicate documents by content hash")

        return deduplicated

    def _save_document(self, doc: ScrapedDocument, output_dir: Path) -> Optional[Path]:
        """Save document to disk."""
        try:
            output_dir.mkdir(parents=True, exist_ok=True)

            # Generate safe filename
            safe_title = "".join(
                c if c.isalnum() or c in ['-', '_', ' '] else '_'
                for c in doc.title[:100]
            )
            safe_title = safe_title.strip().replace(' ', '_')

            ext = ".pdf" if doc.document_type == "pdf" else ".html"
            filename = f"{safe_title}{ext}"

            output_path = output_dir / filename

            # Ensure content exists
            if doc.content:
                output_path.write_bytes(doc.content)
                doc.local_path = output_path
                return output_path

        except Exception as e:
            logger.error(f"Failed to save document: {e}")

        return None

    def _process_pdf(
        self,
        doc: ScrapedDocument,
        pdf_path: Path,
    ) -> Optional[PipelineResult]:
        """Process PDF through OCR pipeline."""
        try:
            # Generate work_id from title
            work_id = self._generate_work_id(doc.title)

            # Use published date or today
            version_date = doc.date_published or date.today()

            # Calculate content hash for deduplication
            import hashlib
            content_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

            # Process through pipeline
            result = self.ocr_pipeline.process_pdf(
                pdf_path=str(pdf_path),
                work_id=work_id,
                title=doc.title,
                version_date=version_date,
                official_id=doc.official_id or work_id,
                metadata={
                    "source": doc.source,
                    "source_url": doc.url,
                    "content_hash": content_hash,
                    "scraped_at": doc.scraped_at.isoformat() if doc.scraped_at else None,
                },
            )

            return result

        except Exception as e:
            logger.error(f"PDF processing failed: {e}", exc_info=True)
            return None

    def _extract_pdfs_from_html(self, html_doc: ScrapedDocument, max_depth: int = 2) -> List[ScrapedDocument]:
        """
        Extract PDF links from HTML content with smart deep extraction.

        Strategy:
        1. Extract direct PDF links from the page
        2. Follow links to detail pages (up to max_depth)
        3. Extract PDFs from those detail pages
        4. Look for embedded PDFs in iframes and WordPress structures

        Args:
            html_doc: HTML document to parse
            max_depth: Maximum recursion depth for following links

        Returns:
            List of ScrapedDocument objects for PDFs found
        """
        pdf_documents = []
        visited_urls = set()

        def extract_from_page(url: str, content: bytes, depth: int = 0):
            """Recursively extract PDFs from a page."""
            if url in visited_urls or depth > max_depth:
                return

            visited_urls.add(url)

            try:
                from bs4 import BeautifulSoup
                from urllib.parse import urljoin, urlparse

                html = content.decode('utf-8', errors='ignore')
                soup = BeautifulSoup(html, 'html.parser')

                # Strategy 1: Direct PDF links
                for link in soup.find_all('a', href=True):
                    href = link.get('href')

                    # Check if it's a PDF link
                    if '.pdf' in href.lower():
                        absolute_url = urljoin(url, href)

                        if absolute_url not in [doc.url for doc in pdf_documents]:
                            title = link.get_text(strip=True)

                            if not title or len(title) < 3:
                                from pathlib import Path
                                title = Path(href).stem.replace('-', ' ').replace('_', ' ')

                            pdf_doc = ScrapedDocument(
                                title=title or "Untitled PDF",
                                url=absolute_url,
                                document_type="pdf",
                                source=html_doc.source,
                                date_published=html_doc.date_published,
                                scraped_at=html_doc.scraped_at,
                            )

                            pdf_documents.append(pdf_doc)
                            logger.debug(f"  Found PDF: {title} ({absolute_url})")

                # Strategy 2: Follow detail page links (if depth allows)
                if depth < max_depth:
                    # Look for links that might lead to document detail pages
                    detail_patterns = [
                        '/document/', '/doc/', '/wet/', '/law/', '/staatsblad/',
                        '/beschikking/', '/besluit/', '/resolutie/', '/sb-', '/s.b.'
                    ]

                    for link in soup.find_all('a', href=True):
                        href = link.get('href')

                        # Skip if it's already a PDF or external link
                        if '.pdf' in href.lower():
                            continue

                        # Check if URL suggests a document detail page
                        if any(pattern in href.lower() for pattern in detail_patterns):
                            absolute_url = urljoin(url, href)

                            # Only follow links on same domain
                            if urlparse(absolute_url).netloc == urlparse(url).netloc:
                                try:
                                    # Fetch the detail page
                                    import requests
                                    import time
                                    time.sleep(0.5)  # Rate limiting

                                    response = requests.get(absolute_url, timeout=10)
                                    if response.status_code == 200:
                                        # Recursively extract from detail page
                                        extract_from_page(absolute_url, response.content, depth + 1)
                                except Exception as e:
                                    logger.debug(f"  Failed to fetch detail page {absolute_url}: {e}")

                # Strategy 3: Look for embedded PDFs in iframes
                for iframe in soup.find_all('iframe', src=True):
                    src = iframe.get('src')
                    if '.pdf' in src.lower():
                        absolute_url = urljoin(url, src)

                        if absolute_url not in [doc.url for doc in pdf_documents]:
                            pdf_doc = ScrapedDocument(
                                title=f"Embedded PDF from {urlparse(url).path}",
                                url=absolute_url,
                                document_type="pdf",
                                source=html_doc.source,
                                scraped_at=html_doc.scraped_at,
                            )
                            pdf_documents.append(pdf_doc)

            except Exception as e:
                logger.debug(f"Error extracting from {url}: {e}")

        # Start extraction from the original HTML document
        try:
            if html_doc.content:
                extract_from_page(html_doc.url, html_doc.content, depth=0)
        except Exception as e:
            logger.error(f"Failed to extract PDFs from HTML: {e}", exc_info=True)

        return pdf_documents

    def _generate_work_id(self, title: str) -> str:
        """Generate work ID from title."""
        # Convert to lowercase, remove special chars, limit length
        work_id = title.lower()
        work_id = "".join(c if c.isalnum() or c == ' ' else '' for c in work_id)
        normalized = " ".join(work_id.split())  # collapse whitespace, matches hash input below
        work_id = normalized.replace(' ', '-')[:50]

        # Add a hash suffix for uniqueness. Hash the SAME normalized form
        # used for the slug (not the raw title) — otherwise re-scraping the
        # same document with trivial title differences (case, whitespace,
        # punctuation) produces a different work_id and a silent duplicate
        # work, since _document_exists dedup doesn't catch this either.
        import hashlib
        hash_suffix = hashlib.md5(normalized.encode()).hexdigest()[:8]
        work_id = f"{work_id}-{hash_suffix}"

        return work_id

    def _store_result(self, result: PipelineResult):
        """Store OCR result in canonical database."""
        try:
            self.store.save_work(result.work)
            self.store.save_expression(result.expression)

            for fragment in result.fragments:
                self.store.save_fragment(fragment)

            logger.info(f"Stored: {result.work.title}")

        except Exception as e:
            logger.error(f"Storage failed: {e}", exc_info=True)
            raise

    def _index_result(self, result: PipelineResult):
        """Index result in search database."""
        try:
            from ..search.bm25 import BM25Indexer

            indexer = BM25Indexer(self.search_db)

            for fragment in result.fragments:
                metadata = {
                    "work_title": result.work.title,
                    "version_date": result.expression.version_date.isoformat(),
                }
                indexer.index_fragment(fragment, metadata)

            logger.info(f"Indexed {len(result.fragments)} fragments")

        except Exception as e:
            logger.error(f"Indexing failed: {e}", exc_info=True)
            # Don't raise - indexing failure shouldn't stop the pipeline


def quick_ingest(
    scraper,
    output_dir: str = "data",
    limit: Optional[int] = None,
) -> BatchResult:
    """
    Quick ingestion from a scraper.

    Args:
        scraper: Scraper instance
        output_dir: Base output directory
        limit: Maximum documents to process

    Returns:
        BatchResult
    """
    from pathlib import Path

    base_dir = Path(output_dir)

    processor = BatchProcessor(
        raw_dir=base_dir / "raw",
        canonical_db=str(base_dir / "canonical.db"),
        search_db=str(base_dir / "search.db"),
    )

    return processor.process_scraper(scraper, limit=limit)
