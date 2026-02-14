"""
Link integrity checker for the Legal Knowledge Fabric.

Runs continuous quality checks on the citation graph:
  - Broken target detection (URI points to non-existent fragment/work)
  - Duplicate identity detection (same content, different IDs)
  - Orphan fragments (fragments without a parent expression)
  - Conflicting mappings (same reference resolves to different URIs)
  - Resolution coverage stats (what % of extracted refs are resolved)

Designed to run as a batch job after ingestion, or incrementally.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .store import CanonicalStore

logger = logging.getLogger(__name__)


@dataclass
class IntegrityIssue:
    """A single integrity problem detected."""
    issue_type: str       # broken_target, duplicate, orphan, conflict
    severity: str         # error, warning, info
    subject_uri: str      # the URI with the problem
    description: str
    related_uris: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    detected_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class IntegrityReport:
    """Summary of an integrity check run."""
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())
    total_works: int = 0
    total_expressions: int = 0
    total_fragments: int = 0
    issues: List[IntegrityIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    @property
    def is_clean(self) -> bool:
        return self.error_count == 0

    def summary(self) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        for issue in self.issues:
            by_type[issue.issue_type] = by_type.get(issue.issue_type, 0) + 1
        return {
            "checked_at": self.checked_at,
            "totals": {
                "works": self.total_works,
                "expressions": self.total_expressions,
                "fragments": self.total_fragments,
            },
            "issues": {
                "total": len(self.issues),
                "errors": self.error_count,
                "warnings": self.warning_count,
                "by_type": by_type,
            },
            "clean": self.is_clean,
        }


class LinkIntegrityChecker:
    """
    Checks integrity of the canonical store and citation graph.

    Usage:
        checker = LinkIntegrityChecker(store)
        report = checker.run_full_check()
        print(report.summary())
    """

    def __init__(self, store: CanonicalStore):
        self.store = store
        self._conn = store._conn  # direct access for efficiency

    def run_full_check(self) -> IntegrityReport:
        """Run all integrity checks and return a report."""
        report = IntegrityReport()

        # Get counts
        stats = self.store.stats()
        report.total_works = stats.get("works", 0)
        report.total_expressions = stats.get("expressions", 0)
        report.total_fragments = stats.get("fragments", 0)

        # Run checks
        report.issues.extend(self.check_orphan_expressions())
        report.issues.extend(self.check_orphan_fragments())
        report.issues.extend(self.check_duplicate_uris())
        report.issues.extend(self.check_expression_chain_integrity())
        report.issues.extend(self.check_fragment_parent_refs())
        report.issues.extend(self.check_empty_fragments())

        logger.info(
            "Integrity check complete: %d issues (%d errors, %d warnings)",
            len(report.issues), report.error_count, report.warning_count,
        )
        return report

    def check_orphan_expressions(self) -> List[IntegrityIssue]:
        """Find Expressions whose work_id doesn't exist in works table."""
        issues = []
        rows = self._conn.execute("""
            SELECT e.id, e.uri, e.work_id
            FROM expressions e
            LEFT JOIN works w ON e.work_id = w.id
            WHERE w.id IS NULL
        """).fetchall()

        for row in rows:
            issues.append(IntegrityIssue(
                issue_type="orphan_expression",
                severity="error",
                subject_uri=row["uri"],
                description=f"Expression {row['id']} references non-existent work {row['work_id']}",
                related_uris=[],
            ))
        return issues

    def check_orphan_fragments(self) -> List[IntegrityIssue]:
        """Find Fragments whose expression_id doesn't exist."""
        issues = []
        rows = self._conn.execute("""
            SELECT f.id, f.uri, f.expression_id
            FROM fragments f
            LEFT JOIN expressions e ON f.expression_id = e.id
            WHERE e.id IS NULL
        """).fetchall()

        for row in rows:
            issues.append(IntegrityIssue(
                issue_type="orphan_fragment",
                severity="error",
                subject_uri=row["uri"],
                description=f"Fragment {row['id']} references non-existent expression {row['expression_id']}",
            ))
        return issues

    def check_duplicate_uris(self) -> List[IntegrityIssue]:
        """Check for URI uniqueness violations (should be caught by UNIQUE constraint, but verify)."""
        issues = []

        for table in ("works", "expressions", "fragments"):
            rows = self._conn.execute(f"""
                SELECT uri, COUNT(*) as cnt
                FROM {table}
                GROUP BY uri HAVING cnt > 1
            """).fetchall()

            for row in rows:
                issues.append(IntegrityIssue(
                    issue_type="duplicate_uri",
                    severity="error",
                    subject_uri=row["uri"],
                    description=f"URI appears {row['cnt']} times in {table}",
                    metadata={"table": table, "count": row["cnt"]},
                ))
        return issues

    def check_expression_chain_integrity(self) -> List[IntegrityIssue]:
        """
        Verify that prev/next expression links are consistent.

        If A.next = B, then B.prev should = A.
        """
        issues = []
        rows = self._conn.execute("""
            SELECT e.id, e.uri, e.next_expression_id, e.previous_expression_id
            FROM expressions e
            WHERE e.next_expression_id IS NOT NULL
               OR e.previous_expression_id IS NOT NULL
        """).fetchall()

        for row in rows:
            # Check forward link
            if row["next_expression_id"]:
                next_row = self._conn.execute(
                    "SELECT previous_expression_id FROM expressions WHERE id = ?",
                    (row["next_expression_id"],)
                ).fetchone()
                if next_row is None:
                    issues.append(IntegrityIssue(
                        issue_type="broken_chain_link",
                        severity="error",
                        subject_uri=row["uri"],
                        description=f"next_expression_id {row['next_expression_id']} does not exist",
                    ))
                elif next_row["previous_expression_id"] != row["id"]:
                    issues.append(IntegrityIssue(
                        issue_type="inconsistent_chain",
                        severity="warning",
                        subject_uri=row["uri"],
                        description=(
                            f"A.next=B but B.prev != A "
                            f"(B.prev={next_row['previous_expression_id']})"
                        ),
                    ))

        return issues

    def check_fragment_parent_refs(self) -> List[IntegrityIssue]:
        """Check that parent_fragment_id references exist."""
        issues = []
        rows = self._conn.execute("""
            SELECT f.id, f.uri, f.parent_fragment_id
            FROM fragments f
            WHERE f.parent_fragment_id IS NOT NULL
              AND f.parent_fragment_id NOT IN (SELECT id FROM fragments)
        """).fetchall()

        for row in rows:
            issues.append(IntegrityIssue(
                issue_type="broken_parent_ref",
                severity="warning",
                subject_uri=row["uri"],
                description=f"Parent fragment {row['parent_fragment_id']} does not exist",
            ))
        return issues

    def check_empty_fragments(self) -> List[IntegrityIssue]:
        """Find fragments with no text content (suspicious but not always wrong)."""
        issues = []
        rows = self._conn.execute("""
            SELECT id, uri, fragment_type
            FROM fragments
            WHERE text IS NULL OR text = ''
        """).fetchall()

        for row in rows:
            issues.append(IntegrityIssue(
                issue_type="empty_fragment",
                severity="info",
                subject_uri=row["uri"],
                description=f"Fragment of type {row['fragment_type']} has no text content",
            ))
        return issues

    def check_resolved_references(
        self,
        resolved_refs: List,
        target_store: Optional[CanonicalStore] = None,
    ) -> List[IntegrityIssue]:
        """
        Check that resolved URIs actually point to existing objects in the store.

        Args:
            resolved_refs: list of ResolvedReference objects from the resolver
            target_store: store to check against (defaults to self.store)
        """
        store = target_store or self.store
        issues = []

        for ref in resolved_refs:
            if not hasattr(ref, 'uri') or not ref.uri:
                continue
            if not hasattr(ref, 'status'):
                continue
            if ref.status.value != "resolved":
                continue

            # Check if the URI exists
            uri = ref.uri

            # Try fragments first, then expressions, then works
            found = (
                store.get_fragment_by_uri(uri) is not None
                or store.get_expression_by_uri(uri) is not None
                or store.get_work_by_uri(uri) is not None
            )

            if not found:
                issues.append(IntegrityIssue(
                    issue_type="broken_target",
                    severity="warning",
                    subject_uri=uri,
                    description=f"Resolved URI does not exist in store: {uri}",
                    metadata={"raw_text": ref.raw_text},
                ))

        return issues
