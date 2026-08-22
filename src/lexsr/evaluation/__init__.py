"""
Evaluation framework for the LexSR pipeline.

Provides:
- KnownAnswer / KnownAnswerDataset  — gold-standard benchmark cases
- CitationMetrics / TemporalMetrics / CompletenessMetrics / QualityReport — quality metrics
- BenchmarkCase / BenchmarkResult / BenchmarkSuite — end-to-end evaluation runner
"""

from .dataset import KnownAnswer, KnownAnswerDataset
from .metrics import (
    CitationMetrics,
    CompletenessMetrics,
    QualityReport,
    TemporalMetrics,
)
from .benchmark import BenchmarkCase, BenchmarkResult, BenchmarkSuite

__all__ = [
    "KnownAnswer",
    "KnownAnswerDataset",
    "CitationMetrics",
    "TemporalMetrics",
    "CompletenessMetrics",
    "QualityReport",
    "BenchmarkCase",
    "BenchmarkResult",
    "BenchmarkSuite",
]
