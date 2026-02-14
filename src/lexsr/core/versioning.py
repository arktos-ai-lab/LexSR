"""
Temporal versioning for Dutch legal documents.

Legislation changes over time through amendments (wijzigingswetten).
This module manages version chains so you can answer:
  - "What was article 6:162 BW on 2020-03-15?"
  - "When was this article last amended?"
  - "Show me all versions of this law"

Key concepts:
  - VersionChain: ordered list of Expressions for a single Work
  - VersionDiff: what changed between two consecutive Expressions
  - TemporalIndex: fast lookup of "expression valid at date X"
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from .models import Expression, TemporalExtent, Work


@dataclass
class VersionDiff:
    """
    Records what changed between two consecutive Expressions of a Work.

    This is metadata about the amendment, not a full text diff.
    """
    from_expression_id: str
    to_expression_id: str
    effective_date: date              # when the new version took effect
    change_type: str = ""             # "amendment", "correction", "consolidation"
    change_law_id: Optional[str] = None  # BWB ID of the wijzigingswet
    change_law_title: Optional[str] = None
    affected_fragments: List[str] = field(default_factory=list)  # fragment URIs
    summary: str = ""                 # human-readable change description
    staatsblad_ref: Optional[str] = None  # Stb. 2024, 123
    metadata: Dict[str, Any] = field(default_factory=dict)


class VersionChain:
    """
    An ordered sequence of Expressions for a single Work, sorted by version_date.

    Provides O(log n) lookup for "which version was valid on date X?"
    """

    def __init__(self, work: Work):
        self.work = work
        self._expressions: List[Expression] = []
        self._dates: List[date] = []  # parallel sorted list for bisect
        self._diffs: Dict[str, VersionDiff] = {}  # keyed by to_expression_id

    @property
    def expressions(self) -> List[Expression]:
        """All expressions in chronological order."""
        return list(self._expressions)

    @property
    def latest(self) -> Optional[Expression]:
        """The most recent expression."""
        return self._expressions[-1] if self._expressions else None

    @property
    def earliest(self) -> Optional[Expression]:
        """The earliest expression."""
        return self._expressions[0] if self._expressions else None

    @property
    def count(self) -> int:
        return len(self._expressions)

    def add_expression(self, expression: Expression,
                       diff: Optional[VersionDiff] = None) -> None:
        """
        Insert an Expression into the chain, maintaining chronological order.

        Automatically links previous/next expression IDs.
        """
        if expression.work_id != self.work.id:
            raise ValueError(
                f"Expression work_id {expression.work_id!r} doesn't match "
                f"chain work {self.work.id!r}"
            )

        # Find insertion point
        idx = bisect.bisect_left(self._dates, expression.version_date)

        # Check for duplicate date
        if idx < len(self._dates) and self._dates[idx] == expression.version_date:
            raise ValueError(
                f"Expression with version_date {expression.version_date} "
                f"already exists in chain for work {self.work.id}"
            )

        # Insert into sorted lists
        self._dates.insert(idx, expression.version_date)
        self._expressions.insert(idx, expression)

        # Re-link prev/next pointers
        self._relink(idx)

        # Store diff if provided
        if diff is not None:
            self._diffs[expression.id] = diff

    def _relink(self, idx: int) -> None:
        """Fix prev/next pointers around insertion point."""
        expr = self._expressions[idx]

        # Link to previous
        if idx > 0:
            prev_expr = self._expressions[idx - 1]
            expr.previous_expression_id = prev_expr.id
            prev_expr.next_expression_id = expr.id

        # Link to next
        if idx < len(self._expressions) - 1:
            next_expr = self._expressions[idx + 1]
            expr.next_expression_id = next_expr.id
            next_expr.previous_expression_id = expr.id

    def at_date(self, query_date: date) -> Optional[Expression]:
        """
        Find the Expression that was valid on *query_date*.

        Returns the latest Expression whose version_date <= query_date,
        or None if the Work didn't exist yet.
        """
        if not self._dates:
            return None

        # bisect_right gives us the index *after* the last date <= query_date
        idx = bisect.bisect_right(self._dates, query_date)
        if idx == 0:
            return None  # query_date is before the earliest version

        return self._expressions[idx - 1]

    def versions_between(self, start: date, end: date) -> List[Expression]:
        """Return all Expressions whose version_date falls in [start, end]."""
        lo = bisect.bisect_left(self._dates, start)
        hi = bisect.bisect_right(self._dates, end)
        return self._expressions[lo:hi]

    def diff_for(self, expression_id: str) -> Optional[VersionDiff]:
        """Get the VersionDiff that produced this Expression (if recorded)."""
        return self._diffs.get(expression_id)

    def all_diffs(self) -> List[VersionDiff]:
        """All recorded diffs in chronological order."""
        result = []
        for expr in self._expressions:
            d = self._diffs.get(expr.id)
            if d:
                result.append(d)
        return result

    def timeline(self) -> List[Dict[str, Any]]:
        """
        Return a human-friendly timeline of all versions.

        Useful for display and debugging.
        """
        entries = []
        for expr in self._expressions:
            diff = self._diffs.get(expr.id)
            entry = {
                "expression_id": expr.id,
                "version_date": expr.version_date.isoformat(),
                "uri": expr.uri,
                "status": expr.status.value if expr.status else "unknown",
                "in_force_start": (
                    expr.in_force.start.isoformat()
                    if expr.in_force and expr.in_force.start else None
                ),
                "in_force_end": (
                    expr.in_force.end.isoformat()
                    if expr.in_force and expr.in_force.end else None
                ),
            }
            if diff:
                entry["change_type"] = diff.change_type
                entry["change_law"] = diff.change_law_title or diff.change_law_id
                entry["summary"] = diff.summary
            entries.append(entry)
        return entries


class TemporalIndex:
    """
    Index across multiple Works for fast temporal lookups.

    Supports queries like:
      - "Give me the version of BWB X valid on date Y"
      - "What laws changed between date A and date B?"
      - "List all works that were in force on date Z"
    """

    def __init__(self):
        self._chains: Dict[str, VersionChain] = {}  # keyed by Work.id

    @property
    def work_count(self) -> int:
        return len(self._chains)

    def add_chain(self, chain: VersionChain) -> None:
        """Register a VersionChain for a Work."""
        self._chains[chain.work.id] = chain

    def get_chain(self, work_id: str) -> Optional[VersionChain]:
        """Get the VersionChain for a Work."""
        return self._chains.get(work_id)

    def expression_at(self, work_id: str, query_date: date) -> Optional[Expression]:
        """Find the Expression of a Work that was valid on query_date."""
        chain = self._chains.get(work_id)
        if chain is None:
            return None
        return chain.at_date(query_date)

    def works_in_force_on(self, query_date: date) -> List[Work]:
        """List all Works that had an expression valid on query_date."""
        results = []
        for chain in self._chains.values():
            expr = chain.at_date(query_date)
            if expr is not None:
                results.append(chain.work)
        return results

    def changes_between(
        self, start: date, end: date
    ) -> Dict[str, List[Expression]]:
        """
        Find all Works that had new Expressions published between start and end.

        Returns {work_id: [expressions]} for works that changed.
        """
        changes = {}
        for work_id, chain in self._chains.items():
            versions = chain.versions_between(start, end)
            if versions:
                changes[work_id] = versions
        return changes

    def remove_chain(self, work_id: str) -> bool:
        """Remove a VersionChain. Returns True if it existed."""
        return self._chains.pop(work_id, None) is not None

    def all_chains(self) -> List[VersionChain]:
        """Return all chains, sorted by work ID."""
        return [self._chains[k] for k in sorted(self._chains.keys())]

    def stats(self) -> Dict[str, Any]:
        """Summary statistics about the temporal index."""
        total_versions = sum(c.count for c in self._chains.values())
        return {
            "works": len(self._chains),
            "total_expressions": total_versions,
            "avg_versions_per_work": (
                total_versions / len(self._chains) if self._chains else 0
            ),
        }
