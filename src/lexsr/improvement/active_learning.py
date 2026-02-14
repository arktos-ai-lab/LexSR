"""
Active learning for resolver improvement.

Samples uncertain/failed references for human annotation,
then feeds corrections back into the abbreviation registry and resolver.
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
class LearningExample:
    """A single example for active learning annotation."""
    id: str
    raw_text: str
    ref_type: str
    context: str = ""
    current_uri: Optional[str] = None      # what the resolver produced
    correct_uri: Optional[str] = None      # human-annotated correct URI
    annotated: bool = False
    annotated_at: Optional[str] = None
    annotator: str = ""
    confidence: float = 0.0
    attempts: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LearningStats:
    """Statistics about the active learning pipeline."""
    total_examples: int = 0
    annotated: int = 0
    pending: int = 0
    corrections_applied: int = 0
    new_abbreviations: int = 0

    def summary(self) -> Dict[str, Any]:
        return {
            "total_examples": self.total_examples,
            "annotated": self.annotated,
            "pending": self.pending,
            "corrections_applied": self.corrections_applied,
            "new_abbreviations": self.new_abbreviations,
            "annotation_rate": round(self.annotated / self.total_examples, 4) if self.total_examples > 0 else 0.0,
        }


class ActiveLearner:
    """
    Manages the active learning loop for resolver improvement.

    1. Collects uncertain/failed references from the resolver's unresolved queue
    2. Presents them for human annotation (sorted by frequency)
    3. Applies corrections back to the abbreviation registry
    4. Tracks improvement metrics over time

    Usage:
        learner = ActiveLearner("data/learning.db")
        learner.import_from_resolver(resolver)
        examples = learner.get_next_batch(10)
        # ... human annotates ...
        learner.submit_annotation(example_id, correct_uri="...")
        learner.apply_corrections()
    """

    def __init__(self, db_path: str = "data/learning.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS learning_examples (
                id TEXT PRIMARY KEY,
                raw_text TEXT NOT NULL,
                ref_type TEXT NOT NULL,
                context TEXT,
                current_uri TEXT,
                correct_uri TEXT,
                annotated INTEGER DEFAULT 0,
                annotated_at TEXT,
                annotator TEXT,
                confidence REAL DEFAULT 0.0,
                attempts INTEGER DEFAULT 1,
                metadata TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_learning_annotated
            ON learning_examples(annotated);

            CREATE INDEX IF NOT EXISTS idx_learning_attempts
            ON learning_examples(attempts DESC);

            CREATE TABLE IF NOT EXISTS corrections_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                example_id TEXT NOT NULL,
                abbreviation TEXT,
                bwb_id TEXT,
                applied_at TEXT DEFAULT (datetime('now'))
            );
        """)
        self._conn.commit()

    def import_from_resolver(self, resolver) -> int:
        """
        Import unresolved references from a CitationResolver's queue.

        Returns count of new examples imported.
        """
        if not hasattr(resolver, '_unresolved_db') or not resolver._unresolved_db:
            return 0

        count = 0
        rows = resolver._unresolved_db.execute(
            "SELECT * FROM unresolved_references WHERE status='pending'"
        ).fetchall()

        for row in rows:
            try:
                self._conn.execute("""
                    INSERT OR IGNORE INTO learning_examples
                        (id, raw_text, ref_type, context, confidence, attempts, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    row["id"], row["raw_text"], row["ref_type"],
                    row["context"], row["confidence"], row["attempts"],
                    row["parsed_data"] or "{}",
                ))
                count += 1
            except Exception:
                pass

        self._conn.commit()
        return count

    def get_next_batch(self, size: int = 10) -> List[LearningExample]:
        """Get the next batch of examples to annotate, sorted by frequency."""
        rows = self._conn.execute("""
            SELECT * FROM learning_examples
            WHERE annotated = 0
            ORDER BY attempts DESC, confidence ASC
            LIMIT ?
        """, (size,)).fetchall()

        return [self._row_to_example(r) for r in rows]

    def submit_annotation(
        self,
        example_id: str,
        correct_uri: Optional[str] = None,
        annotator: str = "human",
    ) -> bool:
        """Submit a human annotation for an example."""
        self._conn.execute("""
            UPDATE learning_examples SET
                correct_uri = ?,
                annotated = 1,
                annotated_at = datetime('now'),
                annotator = ?
            WHERE id = ?
        """, (correct_uri, annotator, example_id))
        self._conn.commit()
        return self._conn.total_changes > 0

    def apply_corrections(self) -> int:
        """
        Apply annotated corrections to the abbreviation registry.

        Looks for annotated examples where correct_uri differs from current_uri,
        and extracts new abbreviation mappings.
        """
        rows = self._conn.execute("""
            SELECT * FROM learning_examples
            WHERE annotated = 1 AND correct_uri IS NOT NULL
            AND (current_uri IS NULL OR current_uri != correct_uri)
        """).fetchall()

        applied = 0
        for row in rows:
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
            parsed_law = meta.get("parsed_law")

            if parsed_law and row["correct_uri"]:
                # Extract BWB ID from URI like /id/bwb/BWBR0005291/...
                parts = row["correct_uri"].split("/")
                if len(parts) >= 4 and parts[2] == "bwb":
                    bwb_id = parts[3]
                    # Log the correction
                    self._conn.execute("""
                        INSERT INTO corrections_log (example_id, abbreviation, bwb_id)
                        VALUES (?, ?, ?)
                    """, (row["id"], parsed_law, bwb_id))
                    applied += 1

        self._conn.commit()
        return applied

    def get_corrections(self) -> List[Dict[str, str]]:
        """Get all corrections that should be added to LAW_ABBREVIATIONS."""
        rows = self._conn.execute(
            "SELECT DISTINCT abbreviation, bwb_id FROM corrections_log"
        ).fetchall()
        return [{"abbreviation": r["abbreviation"], "bwb_id": r["bwb_id"]} for r in rows]

    def stats(self) -> LearningStats:
        """Get current learning statistics."""
        total = self._conn.execute("SELECT COUNT(*) FROM learning_examples").fetchone()[0]
        annotated = self._conn.execute(
            "SELECT COUNT(*) FROM learning_examples WHERE annotated = 1"
        ).fetchone()[0]
        corrections = self._conn.execute("SELECT COUNT(*) FROM corrections_log").fetchone()[0]

        return LearningStats(
            total_examples=total,
            annotated=annotated,
            pending=total - annotated,
            corrections_applied=corrections,
        )

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _row_to_example(self, row) -> LearningExample:
        return LearningExample(
            id=row["id"],
            raw_text=row["raw_text"],
            ref_type=row["ref_type"],
            context=row["context"] or "",
            current_uri=row["current_uri"],
            correct_uri=row["correct_uri"],
            annotated=bool(row["annotated"]),
            annotated_at=row["annotated_at"],
            annotator=row["annotator"] or "",
            confidence=row["confidence"] or 0.0,
            attempts=row["attempts"] or 1,
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
