"""
Benchmark suite for end-to-end evaluation of the LexSR pipeline.

BenchmarkCase   — result for a single known-answer case
BenchmarkResult — aggregate result for a full dataset run
BenchmarkSuite  — runner: feeds KnownAnswerDataset through a resolver
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from .dataset import KnownAnswer, KnownAnswerDataset
from .metrics import CitationMetrics, QualityReport, TemporalMetrics

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkCase:
    """Result for a single KnownAnswer case."""

    case_id: str
    category: str
    passed: bool
    expected_uris: List[str]
    actual_uris: List[str]
    score: float = 0.0
    message: str = ""


@dataclass
class BenchmarkResult:
    """Aggregate result from running a BenchmarkSuite over a dataset."""

    suite_name: str
    total_cases: int = 0
    passed: int = 0
    failed: int = 0
    cases: List[BenchmarkCase] = field(default_factory=list)
    quality_report: Optional[QualityReport] = None

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total_cases if self.total_cases else 0.0

    def summary(self) -> Dict[str, Any]:
        return {
            "suite": self.suite_name,
            "total_cases": self.total_cases,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
        }

    def failed_cases(self) -> List[BenchmarkCase]:
        return [c for c in self.cases if not c.passed]


class BenchmarkSuite:
    """
    Run a KnownAnswerDataset through a CitationResolver and score results.

    Parameters
    ----------
    resolver:
        CitationResolver instance.  If None, all cases will fail (used to
        verify that the baseline is correctly set up).
    """

    def __init__(self, resolver=None) -> None:
        self.resolver = resolver

    # ── Public API ────────────────────────────────────────────────────────

    def run(self, dataset: KnownAnswerDataset) -> BenchmarkResult:
        """
        Evaluate all cases in the dataset.

        Returns a BenchmarkResult with per-case details and a QualityReport.
        """
        result = BenchmarkResult(suite_name=dataset.name, total_cases=dataset.count)

        for ka in dataset.cases():
            case = self._run_case(ka)
            result.cases.append(case)
            if case.passed:
                result.passed += 1
            else:
                result.failed += 1

        result.quality_report = self._build_quality_report(result, dataset)
        return result

    # ── Case dispatch ─────────────────────────────────────────────────────

    def _run_case(self, ka: KnownAnswer) -> BenchmarkCase:
        if self.resolver is None:
            return BenchmarkCase(
                case_id=ka.id,
                category=ka.category,
                passed=False,
                expected_uris=ka.expected_uris,
                actual_uris=[],
                message="No resolver configured",
            )

        if ka.category in ("citation", "temporal"):
            return self._run_resolution_case(ka)

        return BenchmarkCase(
            case_id=ka.id,
            category=ka.category,
            passed=False,
            expected_uris=ka.expected_uris,
            actual_uris=[],
            message=f"Unknown category: {ka.category!r}",
        )

    def _run_resolution_case(self, ka: KnownAnswer) -> BenchmarkCase:
        """
        Resolve ka.input_text and check expected URIs against results.

        Matching rule: an expected URI is satisfied if it appears exactly
        in the set of resolved URIs (both fragment and work-level URIs
        are collected so work-level expectations match fragment-level results).
        """
        try:
            refs = self.resolver.resolve_text(
                ka.input_text,
                version_date=ka.query_date,
            )
        except Exception as exc:
            logger.warning("Resolver error for case %s: %s", ka.id, exc)
            return BenchmarkCase(
                case_id=ka.id,
                category=ka.category,
                passed=False,
                expected_uris=ka.expected_uris,
                actual_uris=[],
                message=f"Resolver error: {exc}",
            )

        # Collect all non-None URI strings from each resolved reference.
        # Include both the fragment URI and the work URI so that a work-level
        # expected URI (e.g. "/id/law/arbeidswet-1963") matches even when
        # the resolver returns a more specific fragment URI.
        uri_set: set[str] = set()
        for ref in refs:
            if ref.uri:
                uri_set.add(ref.uri)
            if ref.work_uri:
                uri_set.add(ref.work_uri)

        actual_uris = sorted(uri_set)

        # A case passes when every expected URI is satisfied.
        # Satisfaction: exact membership OR the expected URI is a prefix of
        # any actual URI (handles work-URI expectations against fragment results).
        def _satisfied(expected: str) -> bool:
            if expected in uri_set:
                return True
            return any(actual.startswith(expected) for actual in uri_set)

        if not ka.expected_uris:
            passed = len(uri_set) == 0
        else:
            passed = all(_satisfied(e) for e in ka.expected_uris)

        score = sum(1.0 for e in ka.expected_uris if _satisfied(e)) / max(len(ka.expected_uris), 1)

        return BenchmarkCase(
            case_id=ka.id,
            category=ka.category,
            passed=passed,
            expected_uris=ka.expected_uris,
            actual_uris=actual_uris,
            score=score,
        )

    # ── Quality report ────────────────────────────────────────────────────

    def _build_quality_report(
        self, result: BenchmarkResult, dataset: KnownAnswerDataset
    ) -> QualityReport:
        """Build a QualityReport from the benchmark run."""
        citation_cases = [c for c in result.cases if c.category == "citation"]
        temporal_cases = [c for c in result.cases if c.category == "temporal"]

        # Citation metrics
        cit_tp = sum(len(c.expected_uris) for c in citation_cases if c.passed)
        cit_fn = sum(len(c.expected_uris) for c in citation_cases if not c.passed)
        cit_resolved = sum(1 for c in citation_cases if c.actual_uris)

        citation_metrics = CitationMetrics(
            total_references=len(citation_cases),
            resolved_count=cit_resolved,
            true_positives=cit_tp,
            false_positives=0,  # we don't penalise extra results
            false_negatives=cit_fn,
        )

        # Temporal metrics
        temporal_metrics = TemporalMetrics(
            total_queries=len(temporal_cases),
            correct_version=sum(1 for c in temporal_cases if c.passed),
            wrong_version=sum(1 for c in temporal_cases if not c.passed and c.actual_uris),
            no_result=sum(1 for c in temporal_cases if not c.passed and not c.actual_uris),
        )

        return QualityReport(
            citation_metrics=citation_metrics,
            temporal_metrics=temporal_metrics,
        )
