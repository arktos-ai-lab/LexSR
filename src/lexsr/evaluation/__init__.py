"""
Evaluation framework for the Legal Knowledge Fabric.

Provides automated quality assessment for:
  - Citation resolution accuracy (precision/recall)
  - Temporal correctness (legislation version on date X)
  - Data completeness (per source, per year)
  - Link integrity metrics
  - Known-answer benchmark suite

Sprint 3: Quality system per PLAN.md --
  "If you do this, quality improves every week instead of drifting."
"""

from .benchmark import BenchmarkSuite, BenchmarkResult, BenchmarkCase
from .metrics import (
    CitationMetrics,
    TemporalMetrics,
    CompletenessMetrics,
    QualityReport,
)
from .dataset import KnownAnswerDataset, KnownAnswer

__all__ = [
    "BenchmarkSuite",
    "BenchmarkResult",
    "BenchmarkCase",
    "CitationMetrics",
    "TemporalMetrics",
    "CompletenessMetrics",
    "QualityReport",
    "KnownAnswerDataset",
    "KnownAnswer",
]
