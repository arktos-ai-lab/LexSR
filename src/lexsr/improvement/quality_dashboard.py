"""
Quality dashboard: tracks metrics over time.

Stores periodic snapshots of quality metrics so you can see
whether the system is improving, stable, or regressing.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class QualitySnapshot:
    """A point-in-time snapshot of quality metrics."""
    id: Optional[int] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    version: str = ""
    citation_precision: float = 0.0
    citation_recall: float = 0.0
    citation_f1: float = 0.0
    resolution_rate: float = 0.0
    temporal_accuracy: float = 0.0
    total_works: int = 0
    total_expressions: int = 0
    total_fragments: int = 0
    integrity_errors: int = 0
    integrity_warnings: int = 0
    benchmark_pass_rate: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "version": self.version,
            "citation": {
                "precision": round(self.citation_precision, 4),
                "recall": round(self.citation_recall, 4),
                "f1": round(self.citation_f1, 4),
                "resolution_rate": round(self.resolution_rate, 4),
            },
            "temporal_accuracy": round(self.temporal_accuracy, 4),
            "data": {
                "works": self.total_works,
                "expressions": self.total_expressions,
                "fragments": self.total_fragments,
            },
            "integrity": {
                "errors": self.integrity_errors,
                "warnings": self.integrity_warnings,
            },
            "benchmark_pass_rate": round(self.benchmark_pass_rate, 4),
        }


class QualityDashboard:
    """
    Tracks quality metrics over time with persistent snapshots.

    Usage:
        dashboard = QualityDashboard("data/quality.db")
        dashboard.record_snapshot(snapshot)
        history = dashboard.get_history(limit=30)
        trend = dashboard.trend("citation_f1")
    """

    def __init__(self, db_path: str = "data/quality.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS quality_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                version TEXT,
                citation_precision REAL DEFAULT 0.0,
                citation_recall REAL DEFAULT 0.0,
                citation_f1 REAL DEFAULT 0.0,
                resolution_rate REAL DEFAULT 0.0,
                temporal_accuracy REAL DEFAULT 0.0,
                total_works INTEGER DEFAULT 0,
                total_expressions INTEGER DEFAULT 0,
                total_fragments INTEGER DEFAULT 0,
                integrity_errors INTEGER DEFAULT 0,
                integrity_warnings INTEGER DEFAULT 0,
                benchmark_pass_rate REAL DEFAULT 0.0,
                metadata TEXT DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp
            ON quality_snapshots(timestamp);
        """)
        self._conn.commit()

    def record_snapshot(self, snapshot: QualitySnapshot) -> int:
        """Record a quality snapshot. Returns the snapshot ID."""
        cur = self._conn.execute("""
            INSERT INTO quality_snapshots
                (timestamp, version, citation_precision, citation_recall,
                 citation_f1, resolution_rate, temporal_accuracy,
                 total_works, total_expressions, total_fragments,
                 integrity_errors, integrity_warnings, benchmark_pass_rate,
                 metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            snapshot.timestamp, snapshot.version,
            snapshot.citation_precision, snapshot.citation_recall,
            snapshot.citation_f1, snapshot.resolution_rate,
            snapshot.temporal_accuracy,
            snapshot.total_works, snapshot.total_expressions, snapshot.total_fragments,
            snapshot.integrity_errors, snapshot.integrity_warnings,
            snapshot.benchmark_pass_rate,
            json.dumps(snapshot.metadata),
        ))
        self._conn.commit()
        return cur.lastrowid

    def get_latest(self) -> Optional[QualitySnapshot]:
        """Get the most recent snapshot."""
        row = self._conn.execute(
            "SELECT * FROM quality_snapshots ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        return self._row_to_snapshot(row) if row else None

    def get_history(self, limit: int = 30) -> List[QualitySnapshot]:
        """Get recent snapshots, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM quality_snapshots ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def trend(self, metric: str, limit: int = 30) -> List[Dict[str, Any]]:
        """
        Get the trend of a specific metric over time.

        Returns [{timestamp, value}, ...] in chronological order.
        """
        valid_metrics = {
            "citation_precision", "citation_recall", "citation_f1",
            "resolution_rate", "temporal_accuracy", "benchmark_pass_rate",
            "total_works", "total_expressions", "total_fragments",
            "integrity_errors", "integrity_warnings",
        }
        if metric not in valid_metrics:
            return []

        rows = self._conn.execute(
            f"SELECT timestamp, {metric} as value "
            f"FROM quality_snapshots ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [{"timestamp": r["timestamp"], "value": r["value"]} for r in reversed(rows)]

    def is_improving(self, metric: str = "citation_f1", window: int = 5) -> Optional[bool]:
        """
        Check if a metric is improving over the last N snapshots.

        Returns True if improving, False if declining, None if insufficient data.
        """
        points = self.trend(metric, limit=window)
        if len(points) < 2:
            return None
        values = [p["value"] for p in points]
        return values[-1] > values[0]

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _row_to_snapshot(self, row) -> QualitySnapshot:
        return QualitySnapshot(
            id=row["id"],
            timestamp=row["timestamp"],
            version=row["version"] or "",
            citation_precision=row["citation_precision"] or 0.0,
            citation_recall=row["citation_recall"] or 0.0,
            citation_f1=row["citation_f1"] or 0.0,
            resolution_rate=row["resolution_rate"] or 0.0,
            temporal_accuracy=row["temporal_accuracy"] or 0.0,
            total_works=row["total_works"] or 0,
            total_expressions=row["total_expressions"] or 0,
            total_fragments=row["total_fragments"] or 0,
            integrity_errors=row["integrity_errors"] or 0,
            integrity_warnings=row["integrity_warnings"] or 0,
            benchmark_pass_rate=row["benchmark_pass_rate"] or 0.0,
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
