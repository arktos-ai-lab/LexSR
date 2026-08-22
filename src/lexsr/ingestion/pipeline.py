"""
End-to-end ingestion pipeline: Bronze -> Silver -> Store.

Orchestrates the full data flow from raw scraper output to the canonical store.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.store import CanonicalStore
from ..ocr.citation_extractor import CitationExtractor
from .bronze import BronzeRecord, BronzeStore
from .silver import ProcessingResult, SilverProcessor

logger = logging.getLogger(__name__)


@dataclass
class IngestionStats:
    """Statistics from an ingestion run."""
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: Optional[str] = None
    bronze_stored: int = 0
    bronze_duplicates: int = 0
    silver_processed: int = 0
    silver_errors: int = 0
    works_saved: int = 0
    expressions_saved: int = 0
    fragments_saved: int = 0
    citations_saved: int = 0
    errors: List[str] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "bronze": {
                "stored": self.bronze_stored,
                "duplicates": self.bronze_duplicates,
            },
            "silver": {
                "processed": self.silver_processed,
                "errors": self.silver_errors,
            },
            "store": {
                "works": self.works_saved,
                "expressions": self.expressions_saved,
                "fragments": self.fragments_saved,
                "citations": self.citations_saved,
            },
            "total_errors": len(self.errors),
        }


class IngestionPipeline:
    """
    Full ingestion pipeline: raw data -> Bronze -> Silver -> Store.

    Usage:
        pipeline = IngestionPipeline(
            bronze_store=BronzeStore("data/bronze.db"),
            canonical_store=CanonicalStore("data/canonical.db"),
        )
        stats = pipeline.ingest_records([record1, record2, ...])
        print(stats.summary())
    """

    def __init__(
        self,
        bronze_store: BronzeStore,
        canonical_store: CanonicalStore,
        processor: Optional[SilverProcessor] = None,
    ):
        self.bronze = bronze_store
        self.store = canonical_store
        self.processor = processor or SilverProcessor()

    def ingest_records(self, records: List[BronzeRecord]) -> IngestionStats:
        """
        Ingest a batch of raw records through the full pipeline.

        1. Store raw bytes in Bronze (deduplicated)
        2. Process each into Silver (Work, Expression, Fragment)
        3. Save Silver objects to the canonical store
        """
        stats = IngestionStats()

        for record in records:
            # Step 1: Bronze storage
            is_new = self.bronze.store(record)
            if is_new:
                stats.bronze_stored += 1
            else:
                stats.bronze_duplicates += 1

            # Step 2: Silver processing
            result = self.processor.process(record)
            stats.silver_processed += 1

            if result.errors:
                stats.silver_errors += 1
                stats.errors.extend(result.errors)
                continue

            # Step 3: Save to canonical store
            try:
                self._save_result(result, stats)
            except Exception as e:
                stats.errors.append(f"Store save failed for {record.id}: {e}")
                logger.exception("Failed to save to store: %s", record.id)

        stats.finished_at = datetime.now().isoformat()
        logger.info(
            "Ingestion complete: %d records, %d works, %d expressions, %d fragments, %d errors",
            stats.silver_processed, stats.works_saved, stats.expressions_saved,
            stats.fragments_saved, len(stats.errors),
        )
        return stats

    def _save_result(self, result: ProcessingResult, stats: IngestionStats) -> None:
        """Save a Silver processing result to the canonical store."""
        if result.work:
            self.store.save_work(result.work)
            stats.works_saved += 1

        for expr in result.expressions:
            self.store.save_expression(expr)
            stats.expressions_saved += 1

        for frag in result.fragments:
            self.store.save_fragment(frag)
            stats.fragments_saved += 1

        # Extract and persist citations from each expression's fragments.
        # Run after all fragments are saved so URI lookups succeed.
        extractor = CitationExtractor(self.store)
        for expr in result.expressions:
            expr_frags = [f for f in result.fragments if f.expression_id == expr.id]
            if not expr_frags:
                continue
            citations = extractor.extract_from_fragments(
                expr_frags, source_version_date=expr.version_date
            )
            stats.citations_saved += extractor.save_to_store(citations)

    def ingest_single(self, record: BronzeRecord) -> ProcessingResult:
        """Ingest a single record and return the processing result."""
        self.bronze.store(record)
        result = self.processor.process(record)
        if result.success:
            stats = IngestionStats()
            self._save_result(result, stats)
        return result
