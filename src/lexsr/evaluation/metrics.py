"""
Quality metrics for the LexSR pipeline.

CitationMetrics   — precision/recall/F1 for reference resolution
TemporalMetrics   — accuracy of version-aware (as-of-date) lookups
CompletenessMetrics — coverage of the canonical store
QualityReport     — aggregate of all metric types
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class CitationMetrics:
    """Precision/recall metrics for citation resolution."""

    total_references: int = 0
    resolved_count: int = 0
    partial_count: int = 0
    unresolved_count: int = 0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def resolution_rate(self) -> float:
        return self.resolved_count / self.total_references if self.total_references else 0.0

    def summary(self) -> Dict[str, Any]:
        return {
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "resolution_rate": self.resolution_rate,
            "total_references": self.total_references,
            "resolved_count": self.resolved_count,
            "partial_count": self.partial_count,
            "unresolved_count": self.unresolved_count,
        }


@dataclass
class TemporalMetrics:
    """Accuracy of version-aware (as-of-date) document lookups."""

    total_queries: int = 0
    correct_version: int = 0
    wrong_version: int = 0
    no_result: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct_version / self.total_queries if self.total_queries else 0.0

    def summary(self) -> Dict[str, Any]:
        return {
            "accuracy": self.accuracy,
            "total_queries": self.total_queries,
            "correct_version": self.correct_version,
            "wrong_version": self.wrong_version,
            "no_result": self.no_result,
        }


@dataclass
class CompletenessMetrics:
    """Coverage of the canonical store for a given source type."""

    source_type: str
    total_works: int = 0
    works_with_expressions: int = 0
    total_expressions: int = 0
    expressions_with_fragments: int = 0

    @property
    def expression_coverage(self) -> float:
        return self.works_with_expressions / self.total_works if self.total_works else 0.0

    @property
    def fragment_coverage(self) -> float:
        return (
            self.expressions_with_fragments / self.total_expressions
            if self.total_expressions
            else 0.0
        )

    def summary(self) -> Dict[str, Any]:
        return {
            "source_type": self.source_type,
            "total_works": self.total_works,
            "works_with_expressions": self.works_with_expressions,
            "expression_coverage": self.expression_coverage,
            "total_expressions": self.total_expressions,
            "expressions_with_fragments": self.expressions_with_fragments,
            "fragment_coverage": self.fragment_coverage,
        }


@dataclass
class QualityReport:
    """Aggregate quality report combining all metric types."""

    citation_metrics: Optional[CitationMetrics] = None
    temporal_metrics: Optional[TemporalMetrics] = None
    completeness: List[CompletenessMetrics] = field(default_factory=list)
    integrity_summary: Dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def summary(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"generated_at": self.generated_at}
        if self.citation_metrics is not None:
            result["citations"] = self.citation_metrics.summary()
        if self.temporal_metrics is not None:
            result["temporal"] = self.temporal_metrics.summary()
        if self.completeness:
            result["completeness"] = [m.summary() for m in self.completeness]
        if self.integrity_summary:
            result["integrity"] = self.integrity_summary
        return result
