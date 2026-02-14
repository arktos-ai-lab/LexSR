"""
Ingestion pipeline for the Legal Knowledge Fabric.

Handles the Bronze -> Silver data flow:
  - Bronze: raw bytes from scrapers/APIs, stored immutably with provenance
  - Silver: cleaned, normalized documents with canonical IDs and fragments

Sprint 4: Connects existing scrapers (Local-SRU-Scrapers-Sorted) to the
canonical data model from core.
"""

from .bronze import BronzeStore, BronzeRecord
from .silver import SilverProcessor, ProcessingResult
from .pipeline import IngestionPipeline, IngestionStats

__all__ = [
    "BronzeStore",
    "BronzeRecord",
    "SilverProcessor",
    "ProcessingResult",
    "IngestionPipeline",
    "IngestionStats",
]
