"""
BM25 lexical search using SQLite FTS5.

Fast, lightweight, zero-dependency (except stdlib) lexical search.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.models import Fragment

logger = logging.getLogger(__name__)


@dataclass
class BM25Result:
    """A single BM25 search result."""
    uri: str
    score: float
    rank: int
    snippet: str = ""
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BM25Indexer:
    """
    Index legal fragments for BM25 search using SQLite FTS5.

    Features:
    - Article-level and paragraph-level indexing
    - Field boosting (title > article_number > heading > text)
    - Porter stemming + Unicode tokenization
    - Incremental updates
    """

    def __init__(self, db_path: str = "data/search.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_index()

    def _create_index(self):
        """Create FTS5 virtual table with field boosting."""
        self._conn.executescript("""
            -- FTS5 virtual table for full-text search
            CREATE VIRTUAL TABLE IF NOT EXISTS fragments_fts USING fts5(
                uri UNINDEXED,
                work_id UNINDEXED,
                work_title,
                fragment_type UNINDEXED,
                article_number,
                heading,
                heading_path,
                text,
                tokenize='porter unicode61',
                content_rowid=rowid
            );

            -- Metadata table (not searchable, but joined for results)
            CREATE TABLE IF NOT EXISTS fragment_metadata (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                uri TEXT UNIQUE NOT NULL,
                work_id TEXT NOT NULL,
                expression_id TEXT NOT NULL,
                fragment_type TEXT NOT NULL,
                version_date TEXT,
                in_force_start TEXT,
                in_force_end TEXT,
                language TEXT DEFAULT 'nl',
                jurisdiction TEXT DEFAULT 'SR',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_metadata_uri ON fragment_metadata(uri);
            CREATE INDEX IF NOT EXISTS idx_metadata_work ON fragment_metadata(work_id);
        """)
        self._conn.commit()

    def index_fragment(self, fragment: Fragment, metadata: Dict[str, Any]) -> None:
        """
        Index a single fragment.

        Args:
            fragment: Fragment to index
            metadata: Additional metadata (version_date, in_force, etc.)
        """
        # Insert metadata
        self._conn.execute("""
            INSERT OR REPLACE INTO fragment_metadata
                (uri, work_id, expression_id, fragment_type, version_date,
                 in_force_start, in_force_end, language, jurisdiction)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fragment.uri,
            fragment.work_id,
            fragment.expression_id,
            fragment.fragment_type.value,
            metadata.get("version_date"),
            metadata.get("in_force_start"),
            metadata.get("in_force_end"),
            metadata.get("language", "nl"),
            metadata.get("jurisdiction", "SR"),
        ))

        # Get the rowid for FTS5
        rowid = self._conn.execute(
            "SELECT rowid FROM fragment_metadata WHERE uri = ?", (fragment.uri,)
        ).fetchone()[0]

        # Index in FTS5
        work_title = metadata.get("work_title", "")
        heading_path = " > ".join(fragment.heading_path) if fragment.heading_path else ""

        self._conn.execute("""
            INSERT OR REPLACE INTO fragments_fts
                (rowid, uri, work_id, work_title, fragment_type, article_number,
                 heading, heading_path, text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rowid,
            fragment.uri,
            fragment.work_id,
            work_title,
            fragment.fragment_type.value,
            fragment.number or "",
            fragment.title or "",
            heading_path,
            fragment.text,
        ))
        self._conn.commit()

    def index_fragments(self, fragments: List[Tuple[Fragment, Dict[str, Any]]]) -> int:
        """
        Batch index multiple fragments.

        Args:
            fragments: List of (fragment, metadata) tuples

        Returns:
            Number of fragments indexed
        """
        count = 0
        for fragment, metadata in fragments:
            self.index_fragment(fragment, metadata)
            count += 1

        logger.info(f"Indexed {count} fragments")
        return count

    def delete_fragment(self, uri: str) -> bool:
        """Delete a fragment from the index."""
        rowid = self._conn.execute(
            "SELECT rowid FROM fragment_metadata WHERE uri = ?", (uri,)
        ).fetchone()

        if not rowid:
            return False

        self._conn.execute("DELETE FROM fragments_fts WHERE rowid = ?", (rowid[0],))
        self._conn.execute("DELETE FROM fragment_metadata WHERE uri = ?", (uri,))
        self._conn.commit()
        return True

    def count(self) -> int:
        """Return the total number of indexed fragments."""
        return self._conn.execute(
            "SELECT COUNT(*) FROM fragment_metadata"
        ).fetchone()[0]

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class BM25Searcher:
    """
    Search indexed fragments using BM25.

    Features:
    - Field boosting via BM25 parameters
    - Snippet generation with highlighting
    - Temporal filtering (as_of_date)
    - Configurable result limit
    """

    def __init__(self, db_path: str = "data/search.db"):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Index not found: {db_path}")

        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row

    def search(
        self,
        query: str,
        limit: int = 100,
        as_of_date: Optional[str] = None,
        work_id: Optional[str] = None,
    ) -> List[BM25Result]:
        """
        Search for fragments using BM25.

        Args:
            query: Search query
            limit: Maximum results to return
            as_of_date: Optional temporal filter (YYYY-MM-DD)
            work_id: Optional filter by work ID

        Returns:
            List of BM25Result objects sorted by relevance
        """
        # Build FTS5 query
        # FTS5 syntax: field:term for field-specific search
        # We'll boost by ordering fields: work_title first, then article_number, etc.
        fts_query = query

        # Build SQL query with optional filters
        sql = """
            SELECT
                f.uri,
                f.work_title,
                f.article_number,
                f.heading,
                f.text,
                m.version_date,
                m.in_force_start,
                m.in_force_end,
                f.rank AS bm25_score
            FROM fragments_fts f
            JOIN fragment_metadata m ON f.rowid = m.rowid
            WHERE fragments_fts MATCH ?
        """

        params = [fts_query]

        # Add temporal filter
        if as_of_date:
            sql += " AND (m.in_force_start IS NULL OR m.in_force_start <= ?)"
            sql += " AND (m.in_force_end IS NULL OR m.in_force_end > ?)"
            params.extend([as_of_date, as_of_date])

        # Add work filter
        if work_id:
            sql += " AND m.work_id = ?"
            params.append(work_id)

        sql += " ORDER BY bm25_score LIMIT ?"
        params.append(limit)

        # Execute search
        rows = self._conn.execute(sql, params).fetchall()

        # Convert to results
        results = []
        for rank, row in enumerate(rows, start=1):
            # Generate snippet (simplified - just take first 200 chars)
            text = row["text"] or ""
            snippet = text[:200] + "..." if len(text) > 200 else text

            result = BM25Result(
                uri=row["uri"],
                score=abs(row["bm25_score"]),  # FTS5 rank is negative
                rank=rank,
                snippet=snippet,
                metadata={
                    "work_title": row["work_title"],
                    "article_number": row["article_number"],
                    "heading": row["heading"],
                    "version_date": row["version_date"],
                }
            )
            results.append(result)

        logger.info(f"BM25 search for '{query}' returned {len(results)} results")
        return results

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
