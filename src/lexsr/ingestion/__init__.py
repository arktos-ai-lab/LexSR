"""
Ingestion module for Suriname legislation.

Complete pipeline:
1. Web scraping (government websites)
2. Document downloading (PDF/HTML)
3. OCR processing (PyPDF2/Tesseract)
4. FRBR conversion (Work/Expression/Fragment)
5. Canonical storage (SQLite)
6. Search indexing (BM25/Vector)

Data sources:
- DNA (Parliament): https://www.dna.sr/wetgeving/surinaamse-wetten/
- Belastingdienst (Tax): https://belastingdienst.sr/wetten-page/
- SSB (State Oil): https://www.ssb.sr/over-ssb/wet-en-regelgeving/
- MAS (Central Bank): https://mas.sr/nl/wetten-en-verdragen/
- SRIS (Case Law): https://www.sris.sr/

Usage:
    from lexsr.ingestion.scrapers import DNAScraper
    from lexsr.ingestion.batch_processor import quick_ingest

    # Quick ingestion
    result = quick_ingest(DNAScraper(), limit=10)
    print(f"Processed {result.total_processed} documents")

    # Or manual control
    from lexsr.ingestion.batch_processor import BatchProcessor

    processor = BatchProcessor(
        raw_dir="data/raw",
        canonical_db="data/canonical.db",
        search_db="data/search.db",
    )

    scraper = DNAScraper()
    result = processor.process_scraper(scraper, limit=10)
"""

from .batch_processor import BatchProcessor, BatchResult, quick_ingest
from .scrapers import (
    BaseScraper,
    ScrapedDocument,
    ScrapeResult,
    DNAScraper,
)

__all__ = [
    "BatchProcessor",
    "BatchResult",
    "quick_ingest",
    "BaseScraper",
    "ScrapedDocument",
    "ScrapeResult",
    "DNAScraper",
]
