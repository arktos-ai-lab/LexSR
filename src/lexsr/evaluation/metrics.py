"""
Quality metrics for the Legal Knowledge Fabric.

Computes precision, recall, F1, and domain-specific quality indicators
for citation resolution, temporal queries, and data completeness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set


@dataclass
class CitationMetrics:
    """Metrics for citation resolution quality."""
    total_references: int = 0
    resolved_count: int = 0
    partial_count: int = 0
    unresolved_count: int = 0
    true_positives: int = 0     # correctly resolved
    false_positives: int = 0    # resolved to wrong URI
    false_negatives: int = 0    # missed references

    @property
    def resolution_rate(self) -> float:
        if self.total_references == 0:
            return 0.0
        return self.resolved_count / self.total_references

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    def summary(self) -> Dict[str, Any]:
        return {
            "total_references": self.total_references,
            "resolved": self.resolved_count,
            "partial": self.partial_count,
            "unresolved": self.unresolved_count,
            "resolution_rate": round(self.resolution_rate, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


@dataclass
class TemporalMetrics:
    """Metrics for temporal correctness."""
    total_queries: int = 0
    correct_version: int = 0    # returned the right expression for date
    wrong_version: int = 0      # returned wrong expression
    no_result: int = 0          # returned None when should have found something
    false_result: int = 0       # returned something when should have been None

    @property
    def accuracy(self) -> float:
        if self.total_queries == 0:
            return 0.0
        return self.correct_version / self.total_queries

    def summary(self) -> Dict[str, Any]:
        return {
            "total_queries": self.total_queries,
            "correct": self.correct_version,
            "wrong_version": self.wrong_version,
            "no_result": self.no_result,
            "false_result": self.false_result,
            "accuracy": round(self.accuracy, 4),
        }


@dataclass
class CompletenessMetrics:
    """Metrics for data completeness per source."""
    source_type: str
    total_works: int = 0
    total_expressions: int = 0
    total_fragments: int = 0
    works_with_expressions: int = 0
    expressions_with_fragments: int = 0
    works_with_full_text: int = 0

    @property
    def expression_coverage(self) -> float:
        if self.total_works == 0:
            return 0.0
        return self.works_with_expressions / self.total_works

    @property
    def fragment_coverage(self) -> float:
        if self.total_expressions == 0:
            return 0.0
        return self.expressions_with_fragments / self.total_expressions

    def summary(self) -> Dict[str, Any]:
        return {
            "source_type": self.source_type,
            "works": self.total_works,
            "expressions": self.total_expressions,
            "fragments": self.total_fragments,
            "expression_coverage": round(self.expression_coverage, 4),
            "fragment_coverage": round(self.fragment_coverage, 4),
        }


@dataclass
class QualityReport:
    """Aggregate quality report combining all metric types."""
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    citation_metrics: Optional[CitationMetrics] = None
    temporal_metrics: Optional[TemporalMetrics] = None
    completeness: List[CompletenessMetrics] = field(default_factory=list)
    integrity_summary: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"generated_at": self.generated_at}
        if self.citation_metrics:
            result["citations"] = self.citation_metrics.summary()
        if self.temporal_metrics:
            result["temporal"] = self.temporal_metrics.summary()
        if self.completeness:
            result["completeness"] = [c.summary() for c in self.completeness]
        if self.integrity_summary:
            result["integrity"] = self.integrity_summary
        return result
