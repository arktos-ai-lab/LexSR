"""
Benchmark suite for automated quality testing.

Runs known-answer datasets against the resolver and store,
producing metrics that track quality over time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from .dataset import KnownAnswer, KnownAnswerDataset
from .metrics import CitationMetrics, QualityReport, TemporalMetrics

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkCase:
    """Result of running a single benchmark case."""
    case_id: str
    category: str
    passed: bool
    expected_uris: List[str]
    actual_uris: List[str]
    details: str = ""
    duration_ms: float = 0.0


@dataclass
class BenchmarkResult:
    """Aggregate result of a benchmark run."""
    suite_name: str
    run_at: str = field(default_factory=lambda: datetime.now().isoformat())
    total_cases: int = 0
    passed: int = 0
    failed: int = 0
    cases: List[BenchmarkCase] = field(default_factory=list)
    quality_report: Optional[QualityReport] = None

    @property
    def pass_rate(self) -> float:
        if self.total_cases == 0:
            return 0.0
        return self.passed / self.total_cases

    def summary(self) -> Dict[str, Any]:
        result = {
            "suite": self.suite_name,
            "run_at": self.run_at,
            "total": self.total_cases,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(self.pass_rate, 4),
        }
        if self.quality_report:
            result["quality"] = self.quality_report.summary()
        return result

    def failed_cases(self) -> List[BenchmarkCase]:
        return [c for c in self.cases if not c.passed]


class BenchmarkSuite:
    """
    Runs evaluation benchmarks against the resolver and store.

    Usage:
        suite = BenchmarkSuite(resolver=resolver, store=store)
        result = suite.run(dataset)
        print(result.summary())
    """

    def __init__(self, resolver=None, store=None):
        self.resolver = resolver
        self.store = store

    def run(
        self,
        dataset: KnownAnswerDataset,
        version_date: Optional[date] = None,
    ) -> BenchmarkResult:
        """Run all cases in a dataset and return results."""
        vdate = version_date or date.today()
        result = BenchmarkResult(suite_name=dataset.name)

        citation_metrics = CitationMetrics()
        temporal_metrics = TemporalMetrics()

        for case in dataset.cases():
            case_result = self._run_case(case, vdate, citation_metrics, temporal_metrics)
            result.cases.append(case_result)
            result.total_cases += 1
            if case_result.passed:
                result.passed += 1
            else:
                result.failed += 1

        # Build quality report
        result.quality_report = QualityReport(
            citation_metrics=citation_metrics if citation_metrics.total_references > 0 else None,
            temporal_metrics=temporal_metrics if temporal_metrics.total_queries > 0 else None,
        )

        logger.info(
            "Benchmark '%s': %d/%d passed (%.1f%%)",
            dataset.name, result.passed, result.total_cases,
            result.pass_rate * 100,
        )

        return result

    def _run_case(
        self,
        case: KnownAnswer,
        vdate: date,
        citation_metrics: CitationMetrics,
        temporal_metrics: TemporalMetrics,
    ) -> BenchmarkCase:
        """Run a single benchmark case."""

        if case.category == "citation":
            return self._run_citation_case(case, vdate, citation_metrics)
        elif case.category == "temporal":
            return self._run_temporal_case(case, temporal_metrics)
        else:
            return BenchmarkCase(
                case_id=case.id,
                category=case.category,
                passed=False,
                expected_uris=case.expected_uris,
                actual_uris=[],
                details=f"Unknown category: {case.category}",
            )

    def _run_citation_case(
        self,
        case: KnownAnswer,
        vdate: date,
        metrics: CitationMetrics,
    ) -> BenchmarkCase:
        """Run a citation resolution benchmark case."""
        if not self.resolver:
            return BenchmarkCase(
                case_id=case.id, category="citation",
                passed=False, expected_uris=case.expected_uris, actual_uris=[],
                details="No resolver configured",
            )

        results = self.resolver.resolve_text(case.input_text, version_date=vdate)
        actual_uris = []
        for r in results:
            metrics.total_references += 1
            if r.status.value == "resolved":
                metrics.resolved_count += 1
                if r.uri:
                    actual_uris.append(r.uri)
            elif r.status.value == "partial":
                metrics.partial_count += 1
            else:
                metrics.unresolved_count += 1

        # Check if expected URIs are found (substring match on work URIs)
        expected_found = 0
        for expected in case.expected_uris:
            for actual in actual_uris:
                if expected in actual or actual in expected:
                    expected_found += 1
                    metrics.true_positives += 1
                    break
            else:
                metrics.false_negatives += 1

        passed = expected_found == len(case.expected_uris)

        return BenchmarkCase(
            case_id=case.id,
            category="citation",
            passed=passed,
            expected_uris=case.expected_uris,
            actual_uris=actual_uris,
            details=f"Found {expected_found}/{len(case.expected_uris)} expected URIs",
        )

    def _run_temporal_case(
        self,
        case: KnownAnswer,
        metrics: TemporalMetrics,
    ) -> BenchmarkCase:
        """Run a temporal correctness benchmark case."""
        metrics.total_queries += 1

        if not self.store or not case.query_date:
            return BenchmarkCase(
                case_id=case.id, category="temporal",
                passed=False, expected_uris=case.expected_uris, actual_uris=[],
                details="No store or query_date configured",
            )

        # For temporal cases, we check if the resolver can at least identify the work
        if self.resolver:
            results = self.resolver.resolve_text(
                case.input_text, version_date=case.query_date
            )
            actual_uris = [r.uri for r in results if r.uri]
            expected_found = sum(
                1 for exp in case.expected_uris
                if any(exp in act or act in exp for act in actual_uris)
            )
            if expected_found == len(case.expected_uris):
                metrics.correct_version += 1
                return BenchmarkCase(
                    case_id=case.id, category="temporal",
                    passed=True, expected_uris=case.expected_uris,
                    actual_uris=actual_uris,
                )
            else:
                metrics.wrong_version += 1
                return BenchmarkCase(
                    case_id=case.id, category="temporal",
                    passed=False, expected_uris=case.expected_uris,
                    actual_uris=actual_uris,
                    details=f"Found {expected_found}/{len(case.expected_uris)}",
                )

        metrics.no_result += 1
        return BenchmarkCase(
            case_id=case.id, category="temporal",
            passed=False, expected_uris=case.expected_uris, actual_uris=[],
            details="No resolver configured",
        )
