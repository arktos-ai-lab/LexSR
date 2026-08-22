"""
SQLite-backed canonical store for the FRBR data model.

Persists Works, Expressions, Manifestations, and Fragments with full CRUD,
URI-based lookups, and temporal queries.

Design:
  - Single SQLite file (easy to ship, backup, and version)
  - Write-ahead log for concurrent read/write safety
  - All datetimes stored as ISO-8601 text
  - JSON for metadata/lists (schema-on-read flexibility)
  - Indexes on URIs, official IDs, and version dates
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from .identifiers import LegalURI, URIScheme, parse_uri
from .models import (
    AmendmentLink,
    Citation,
    CitationType,
    DocumentStatus,
    Expression,
    Fragment,
    FragmentAnchor,
    FragmentType,
    Manifestation,
    ManifestationType,
    SourceType,
    TemporalExtent,
    Work,
    resolve_fragment_type,
)
from .versioning import TemporalIndex, VersionChain, VersionDiff

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

_NUM_RE = re.compile(r'^(\d+)')


def _fragment_sort_key(frag: "Fragment") -> tuple:
    """
    Return a sort key that places fragments in natural document order:
    1. Articles numerically (1, 2 … 10 rather than 1, 10, 2).
    2. Paragraph fragments immediately after their parent article.
    3. Paragraphs with no matching parent (memos, annexes) at the end.

    Key tuple: (is_orphan_para, article_num_int, article_num_str,
                is_paragraph, para_num_int, para_num_str)
    """
    from .models import FragmentType  # avoid circular import at module level

    num_str = (frag.number or "").strip()
    m = _NUM_RE.match(num_str)
    num_int = int(m.group(1)) if m else 9999

    if frag.fragment_type == FragmentType.ARTICLE:
        return (0, num_int, num_str, 0, 0, "")
    else:
        # Paragraph: sort after its parent article.
        # Parent article number is embedded in parent_fragment_id as the
        # numeric portion of the last slug segment, e.g. "…-art-7a-…".
        # Fall back to sorting all orphan paragraphs at the very end.
        pid = frag.parent_fragment_id or ""
        pm = re.search(r'-art-?(\d+)', pid)
        if pm:
            part_int = int(pm.group(1))
        else:
            # Try to extract leading digits from parent id for ordering
            pm2 = _NUM_RE.search(pid)
            part_int = int(pm2.group(1)) if pm2 else 9999

        return (1 if not pid else 0, part_int, pid, 1, num_int, num_str)


def _order_fragments(frags: "List[Fragment]") -> "List[Fragment]":
    """Return fragments sorted in natural document order."""
    return sorted(frags, key=_fragment_sort_key)


class CanonicalStore:
    """
    SQLite-backed persistent store for the FRBR legal data model.

    Usage:
        store = CanonicalStore("data/canonical.db")
        store.save_work(work)
        store.save_expression(expression)
        store.save_fragment(fragment)

        # Lookups
        work = store.get_work_by_uri("/id/bwb/BWBR0005291")
        expr = store.get_expression_at_date("work-id", date(2024, 1, 15))
        frags = store.get_fragments_for_expression("expr-id")
    """

    def __init__(self, db_path: str = "data/canonical.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path),
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @contextmanager
    def _transaction(self) -> Generator:
        """Context manager for atomic transactions."""
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _create_schema(self):
        cur = self._conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            )
        """)

        cur.execute("""
            INSERT OR IGNORE INTO schema_version (version) VALUES (?)
        """, (SCHEMA_VERSION,))

        # --- Works ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS works (
                id TEXT PRIMARY KEY,
                uri TEXT UNIQUE NOT NULL,
                source_type TEXT NOT NULL,
                official_id TEXT NOT NULL,
                title TEXT NOT NULL,
                short_title TEXT,
                document_type TEXT,
                jurisdiction TEXT DEFAULT 'SR',
                language TEXT DEFAULT 'nl',
                status TEXT DEFAULT 'unknown',
                date_enacted TEXT,
                date_first_in_force TEXT,
                source_url TEXT,
                source_api TEXT,
                retrieved_at TEXT,
                subject_areas TEXT DEFAULT '[]',
                keywords TEXT DEFAULT '[]',
                replaces TEXT DEFAULT '[]',
                replaced_by TEXT DEFAULT '[]',
                implements TEXT DEFAULT '[]',
                implemented_by TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_works_official_id
            ON works(official_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_works_source_type
            ON works(source_type)
        """)

        # --- Expressions ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS expressions (
                id TEXT PRIMARY KEY,
                uri TEXT UNIQUE NOT NULL,
                work_id TEXT NOT NULL REFERENCES works(id),
                work_uri TEXT NOT NULL,
                version_date TEXT NOT NULL,
                in_force_start TEXT,
                in_force_end TEXT,
                title TEXT,
                language TEXT DEFAULT 'nl',
                status TEXT DEFAULT 'unknown',
                source_url TEXT,
                retrieved_at TEXT,
                checksum TEXT,
                full_text TEXT,
                previous_expression_id TEXT,
                next_expression_id TEXT,
                metadata TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_expressions_work_id
            ON expressions(work_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_expressions_version_date
            ON expressions(work_id, version_date)
        """)

        # --- Manifestations ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS manifestations (
                id TEXT PRIMARY KEY,
                uri TEXT UNIQUE NOT NULL,
                expression_id TEXT NOT NULL REFERENCES expressions(id),
                expression_uri TEXT NOT NULL,
                format TEXT NOT NULL,
                media_type TEXT,
                storage_path TEXT,
                checksum_sha256 TEXT,
                byte_size INTEGER,
                source_url TEXT,
                retrieved_at TEXT,
                http_headers TEXT DEFAULT '{}',
                metadata TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_manifestations_expression_id
            ON manifestations(expression_id)
        """)

        # --- Fragments ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fragments (
                id TEXT PRIMARY KEY,
                uri TEXT UNIQUE NOT NULL,
                expression_id TEXT NOT NULL REFERENCES expressions(id),
                expression_uri TEXT NOT NULL,
                work_id TEXT NOT NULL REFERENCES works(id),
                fragment_type TEXT NOT NULL,
                number TEXT,
                title TEXT,
                parent_fragment_id TEXT,
                position INTEGER DEFAULT 0,
                depth INTEGER DEFAULT 0,
                text TEXT,
                heading_path TEXT DEFAULT '[]',
                anchors TEXT DEFAULT '[]',
                extraction_method TEXT DEFAULT 'structural',
                confidence REAL DEFAULT 1.0,
                extracted_at TEXT,
                metadata TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_fragments_expression_id
            ON fragments(expression_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_fragments_work_id
            ON fragments(work_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_fragments_parent
            ON fragments(parent_fragment_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_fragments_type
            ON fragments(fragment_type)
        """)

        # --- Version Diffs ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS version_diffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_expression_id TEXT NOT NULL,
                to_expression_id TEXT NOT NULL REFERENCES expressions(id),
                effective_date TEXT NOT NULL,
                change_type TEXT,
                change_law_id TEXT,
                change_law_title TEXT,
                affected_fragments TEXT DEFAULT '[]',
                summary TEXT,
                staatsblad_ref TEXT,
                metadata TEXT DEFAULT '{}'
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_diffs_to_expression
            ON version_diffs(to_expression_id)
        """)

        # --- Citations ---
        # Directed edges in the citation graph: fragment/work → fragment/work.
        # source is always resolved; target may be unresolved (target_work_id NULL).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS citations (
                id TEXT PRIMARY KEY,
                citation_type TEXT NOT NULL,
                source_work_id TEXT NOT NULL REFERENCES works(id),
                source_fragment_id TEXT,
                source_version_date TEXT,
                target_work_id TEXT,
                target_fragment_id TEXT,
                target_version_date TEXT,
                raw_text TEXT NOT NULL DEFAULT '',
                confidence REAL DEFAULT 1.0,
                valid_from TEXT,
                valid_to TEXT,
                metadata TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_citations_source_work
            ON citations(source_work_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_citations_target_work
            ON citations(target_work_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_citations_source_fragment
            ON citations(source_fragment_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_citations_target_fragment
            ON citations(target_fragment_id)
        """)

        # --- Amendment links ---
        # Structural links: wijzigingswet → base law.
        # Separate from citations because they drive the consolidation engine.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS amendment_links (
                id TEXT PRIMARY KEY,
                amendment_work_id TEXT NOT NULL REFERENCES works(id),
                base_work_id TEXT,
                base_work_ref TEXT NOT NULL,
                effective_date TEXT,
                staatsblad_ref TEXT,
                confidence REAL DEFAULT 1.0,
                resolved INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_amendment_links_amendment
            ON amendment_links(amendment_work_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_amendment_links_base
            ON amendment_links(base_work_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_amendment_links_unresolved
            ON amendment_links(resolved) WHERE resolved = 0
        """)

        self._conn.commit()

    # ------------------------------------------------------------------
    # Works
    # ------------------------------------------------------------------

    def save_work(self, work: Work) -> None:
        """Insert or update a Work."""
        with self._transaction():
            self._conn.execute("""
                INSERT INTO works (
                    id, uri, source_type, official_id, title, short_title,
                    document_type, jurisdiction, language, status,
                    date_enacted, date_first_in_force,
                    source_url, source_api, retrieved_at,
                    subject_areas, keywords,
                    replaces, replaced_by, implements, implemented_by,
                    metadata, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    uri=excluded.uri, title=excluded.title,
                    short_title=excluded.short_title,
                    status=excluded.status,
                    date_enacted=excluded.date_enacted,
                    date_first_in_force=excluded.date_first_in_force,
                    source_url=excluded.source_url,
                    retrieved_at=excluded.retrieved_at,
                    subject_areas=excluded.subject_areas,
                    keywords=excluded.keywords,
                    replaces=excluded.replaces,
                    replaced_by=excluded.replaced_by,
                    implements=excluded.implements,
                    implemented_by=excluded.implemented_by,
                    metadata=excluded.metadata,
                    updated_at=datetime('now')
            """, (
                work.id, work.uri, work.source_type.value, work.official_id,
                work.title, work.short_title, work.document_type,
                work.jurisdiction, work.language, work.status.value,
                work.date_enacted.isoformat() if work.date_enacted else None,
                work.date_first_in_force.isoformat() if work.date_first_in_force else None,
                work.source_url, work.source_api,
                work.retrieved_at.isoformat() if work.retrieved_at else None,
                json.dumps(work.subject_areas),
                json.dumps(work.keywords),
                json.dumps(work.replaces),
                json.dumps(work.replaced_by),
                json.dumps(work.implements),
                json.dumps(work.implemented_by),
                json.dumps(work.metadata),
            ))

    def get_work(self, work_id: str) -> Optional[Work]:
        """Fetch a Work by ID."""
        row = self._conn.execute(
            "SELECT * FROM works WHERE id = ?", (work_id,)
        ).fetchone()
        return self._row_to_work(row) if row else None

    def get_work_by_uri(self, uri: str) -> Optional[Work]:
        """Fetch a Work by its canonical URI."""
        row = self._conn.execute(
            "SELECT * FROM works WHERE uri = ?", (uri,)
        ).fetchone()
        return self._row_to_work(row) if row else None

    def get_work_by_official_id(self, official_id: str) -> Optional[Work]:
        """Fetch a Work by its official identifier (BWBR, ECLI, etc.)."""
        row = self._conn.execute(
            "SELECT * FROM works WHERE official_id = ?", (official_id,)
        ).fetchone()
        return self._row_to_work(row) if row else None

    def list_works(
        self, source_type: Optional[SourceType] = None, limit: int = 100
    ) -> List[Work]:
        """List Works, optionally filtered by source type."""
        if source_type:
            rows = self._conn.execute(
                "SELECT * FROM works WHERE source_type = ? ORDER BY title LIMIT ?",
                (source_type.value, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM works ORDER BY title LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_work(r) for r in rows]

    # ------------------------------------------------------------------
    # Expressions
    # ------------------------------------------------------------------

    def save_expression(self, expression: Expression) -> None:
        """Insert or update an Expression."""
        with self._transaction():
            self._conn.execute("""
                INSERT INTO expressions (
                    id, uri, work_id, work_uri, version_date,
                    in_force_start, in_force_end,
                    title, language, status,
                    source_url, retrieved_at, checksum, full_text,
                    previous_expression_id, next_expression_id,
                    metadata, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    uri=excluded.uri,
                    in_force_start=excluded.in_force_start,
                    in_force_end=excluded.in_force_end,
                    title=excluded.title, status=excluded.status,
                    source_url=excluded.source_url,
                    checksum=excluded.checksum,
                    full_text=excluded.full_text,
                    previous_expression_id=excluded.previous_expression_id,
                    next_expression_id=excluded.next_expression_id,
                    metadata=excluded.metadata,
                    updated_at=datetime('now')
            """, (
                expression.id, expression.uri,
                expression.work_id, expression.work_uri,
                expression.version_date.isoformat(),
                expression.in_force.start.isoformat() if expression.in_force.start else None,
                expression.in_force.end.isoformat() if expression.in_force.end else None,
                expression.title, expression.language,
                expression.status.value if expression.status else "unknown",
                expression.source_url,
                expression.retrieved_at.isoformat() if expression.retrieved_at else None,
                expression.checksum, expression.full_text,
                expression.previous_expression_id,
                expression.next_expression_id,
                json.dumps(expression.metadata),
            ))

    def get_expression(self, expression_id: str) -> Optional[Expression]:
        """Fetch an Expression by ID."""
        row = self._conn.execute(
            "SELECT * FROM expressions WHERE id = ?", (expression_id,)
        ).fetchone()
        return self._row_to_expression(row) if row else None

    def get_expression_by_uri(self, uri: str) -> Optional[Expression]:
        """Fetch an Expression by its canonical URI."""
        row = self._conn.execute(
            "SELECT * FROM expressions WHERE uri = ?", (uri,)
        ).fetchone()
        return self._row_to_expression(row) if row else None

    def get_expression_at_date(
        self, work_id: str, query_date: date
    ) -> Optional[Expression]:
        """
        Find the Expression of a Work valid on query_date.

        Returns the latest Expression whose version_date <= query_date.
        """
        row = self._conn.execute("""
            SELECT * FROM expressions
            WHERE work_id = ? AND version_date <= ?
            ORDER BY version_date DESC LIMIT 1
        """, (work_id, query_date.isoformat())).fetchone()
        return self._row_to_expression(row) if row else None

    def get_expressions_for_work(self, work_id: str) -> List[Expression]:
        """Fetch all Expressions for a Work, chronologically."""
        rows = self._conn.execute(
            "SELECT * FROM expressions WHERE work_id = ? ORDER BY version_date",
            (work_id,),
        ).fetchall()
        return [self._row_to_expression(r) for r in rows]

    # ------------------------------------------------------------------
    # Manifestations
    # ------------------------------------------------------------------

    def save_manifestation(self, manifestation: Manifestation) -> None:
        """Insert or update a Manifestation."""
        with self._transaction():
            self._conn.execute("""
                INSERT INTO manifestations (
                    id, uri, expression_id, expression_uri,
                    format, media_type, storage_path,
                    checksum_sha256, byte_size,
                    source_url, retrieved_at,
                    http_headers, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    storage_path=excluded.storage_path,
                    checksum_sha256=excluded.checksum_sha256,
                    byte_size=excluded.byte_size,
                    metadata=excluded.metadata
            """, (
                manifestation.id, manifestation.uri,
                manifestation.expression_id, manifestation.expression_uri,
                manifestation.format.value, manifestation.media_type,
                manifestation.storage_path, manifestation.checksum_sha256,
                manifestation.byte_size, manifestation.source_url,
                manifestation.retrieved_at.isoformat() if manifestation.retrieved_at else None,
                json.dumps(manifestation.http_headers),
                json.dumps(manifestation.metadata),
            ))

    def get_manifestations_for_expression(
        self, expression_id: str
    ) -> List[Manifestation]:
        """Fetch all Manifestations for an Expression."""
        rows = self._conn.execute(
            "SELECT * FROM manifestations WHERE expression_id = ?",
            (expression_id,),
        ).fetchall()
        return [self._row_to_manifestation(r) for r in rows]

    # ------------------------------------------------------------------
    # Fragments
    # ------------------------------------------------------------------

    def save_fragment(self, fragment: Fragment) -> None:
        """Insert or update a Fragment."""
        anchors_json = json.dumps([
            {
                "anchor_type": a.anchor_type.value,
                "structural_path": a.structural_path,
                "text_hash": a.text_hash,
                "text_preview": a.text_preview,
                "char_offset_start": a.char_offset_start,
                "char_offset_end": a.char_offset_end,
                "heading_context": a.heading_context,
            }
            for a in fragment.anchors
        ])

        with self._transaction():
            self._conn.execute("""
                INSERT INTO fragments (
                    id, uri, expression_id, expression_uri, work_id,
                    fragment_type, number, title,
                    parent_fragment_id, position, depth,
                    text, heading_path, anchors,
                    extraction_method, confidence, extracted_at,
                    metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    text=excluded.text,
                    anchors=excluded.anchors,
                    heading_path=excluded.heading_path,
                    confidence=excluded.confidence,
                    metadata=excluded.metadata
            """, (
                fragment.id, fragment.uri,
                fragment.expression_id, fragment.expression_uri,
                fragment.work_id,
                fragment.fragment_type.value, fragment.number, fragment.title,
                fragment.parent_fragment_id, fragment.position, fragment.depth,
                fragment.text, json.dumps(fragment.heading_path),
                anchors_json,
                fragment.extraction_method, fragment.confidence,
                fragment.extracted_at.isoformat() if fragment.extracted_at else None,
                json.dumps(fragment.metadata),
            ))

    def get_fragment(self, fragment_id: str) -> Optional[Fragment]:
        """Fetch a Fragment by ID."""
        row = self._conn.execute(
            "SELECT * FROM fragments WHERE id = ?", (fragment_id,)
        ).fetchone()
        return self._row_to_fragment(row) if row else None

    def get_fragment_by_uri(self, uri: str) -> Optional[Fragment]:
        """Fetch a Fragment by its canonical URI."""
        row = self._conn.execute(
            "SELECT * FROM fragments WHERE uri = ?", (uri,)
        ).fetchone()
        return self._row_to_fragment(row) if row else None

    def get_fragments_for_expression(
        self, expression_id: str, fragment_type: Optional[FragmentType] = None
    ) -> List[Fragment]:
        """Fetch all Fragments for an Expression, optionally filtered by type.

        Fragments are returned in document order:
        - Articles ordered numerically (1, 2 … 10, 11 — not lexicographic).
        - Paragraph fragments are grouped immediately after their parent article.
        - Memos / annexes (paragraphs with no matching parent article) come last.

        This matters because almost all fragments have position=0 in the current
        dataset; relying on depth+position alone gives arbitrary ordering.
        """
        if fragment_type:
            rows = self._conn.execute(
                "SELECT * FROM fragments WHERE expression_id = ? AND fragment_type = ? "
                "ORDER BY position",
                (expression_id, fragment_type.value),
            ).fetchall()
            return [self._row_to_fragment(r) for r in rows]

        rows = self._conn.execute(
            "SELECT * FROM fragments WHERE expression_id = ?",
            (expression_id,),
        ).fetchall()
        frags = [self._row_to_fragment(r) for r in rows]
        return _order_fragments(frags)

    def get_child_fragments(self, parent_fragment_id: str) -> List[Fragment]:
        """Fetch child fragments of a parent, ordered by position."""
        rows = self._conn.execute(
            "SELECT * FROM fragments WHERE parent_fragment_id = ? ORDER BY position",
            (parent_fragment_id,),
        ).fetchall()
        return [self._row_to_fragment(r) for r in rows]

    def search_fragments_by_text(
        self, query: str, limit: int = 50
    ) -> List[Fragment]:
        """Simple text search across fragment content."""
        rows = self._conn.execute(
            "SELECT * FROM fragments WHERE text LIKE ? LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [self._row_to_fragment(r) for r in rows]

    # ------------------------------------------------------------------
    # Version Diffs
    # ------------------------------------------------------------------

    def save_version_diff(self, diff: VersionDiff) -> None:
        """Insert a VersionDiff."""
        with self._transaction():
            self._conn.execute("""
                INSERT INTO version_diffs (
                    from_expression_id, to_expression_id, effective_date,
                    change_type, change_law_id, change_law_title,
                    affected_fragments, summary, staatsblad_ref, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                diff.from_expression_id, diff.to_expression_id,
                diff.effective_date.isoformat(),
                diff.change_type, diff.change_law_id, diff.change_law_title,
                json.dumps(diff.affected_fragments),
                diff.summary, diff.staatsblad_ref,
                json.dumps(diff.metadata),
            ))

    # ------------------------------------------------------------------
    # Bulk + Stats
    # ------------------------------------------------------------------

    def save_works_bulk(self, works: List[Work]) -> int:
        """Save multiple Works in a single transaction. Returns count saved."""
        count = 0
        with self._transaction():
            for work in works:
                try:
                    self.save_work(work)
                    count += 1
                except Exception as e:
                    logger.warning("Failed to save work %s: %s", work.id, e)
        return count

    def save_fragments_bulk(self, fragments: List[Fragment]) -> int:
        """Save multiple Fragments in a single transaction."""
        count = 0
        with self._transaction():
            for frag in fragments:
                try:
                    self.save_fragment(frag)
                    count += 1
                except Exception as e:
                    logger.warning("Failed to save fragment %s: %s", frag.id, e)
        return count

    def build_temporal_index(self) -> TemporalIndex:
        """
        Build a TemporalIndex from all Works and Expressions in the store.

        Useful for loading the full index into memory for fast queries.
        """
        index = TemporalIndex()
        works = self.list_works(limit=1_000_000)
        for work in works:
            chain = VersionChain(work)
            expressions = self.get_expressions_for_work(work.id)
            for expr in expressions:
                chain.add_expression(expr)
            if chain.count > 0:
                index.add_chain(chain)
        return index

    def stats(self) -> Dict[str, Any]:
        """Return counts of all stored objects."""
        counts = {}
        for table in (
            "works", "expressions", "manifestations", "fragments",
            "version_diffs", "citations", "amendment_links",
        ):
            row = self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            counts[table] = row[0]
        return counts

    # ------------------------------------------------------------------
    # Citations
    # ------------------------------------------------------------------

    def save_citation(self, citation: Citation) -> None:
        """Insert or update a Citation."""
        with self._transaction():
            self._conn.execute("""
                INSERT INTO citations (
                    id, citation_type,
                    source_work_id, source_fragment_id, source_version_date,
                    target_work_id, target_fragment_id, target_version_date,
                    raw_text, confidence, valid_from, valid_to, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    target_work_id=excluded.target_work_id,
                    target_fragment_id=excluded.target_fragment_id,
                    target_version_date=excluded.target_version_date,
                    confidence=excluded.confidence,
                    valid_to=excluded.valid_to,
                    metadata=excluded.metadata
            """, (
                citation.id, citation.citation_type.value,
                citation.source_work_id, citation.source_fragment_id,
                citation.source_version_date.isoformat() if citation.source_version_date else None,
                citation.target_work_id, citation.target_fragment_id,
                citation.target_version_date.isoformat() if citation.target_version_date else None,
                citation.raw_text, citation.confidence,
                citation.valid_from.isoformat() if citation.valid_from else None,
                citation.valid_to.isoformat() if citation.valid_to else None,
                json.dumps(citation.metadata),
            ))

    def get_citations_from(
        self, work_id: str, fragment_id: Optional[str] = None
    ) -> List[Citation]:
        """Outgoing citations from a work (or specific fragment)."""
        if fragment_id:
            rows = self._conn.execute(
                "SELECT * FROM citations WHERE source_fragment_id = ? ORDER BY valid_from",
                (fragment_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM citations WHERE source_work_id = ? ORDER BY valid_from",
                (work_id,),
            ).fetchall()
        return [self._row_to_citation(r) for r in rows]

    def get_citations_to(
        self, work_id: str, fragment_id: Optional[str] = None
    ) -> List[Citation]:
        """Incoming citations to a work (or specific fragment) — 'cited by'."""
        if fragment_id:
            rows = self._conn.execute(
                "SELECT * FROM citations WHERE target_fragment_id = ?",
                (fragment_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM citations WHERE target_work_id = ?",
                (work_id,),
            ).fetchall()
        return [self._row_to_citation(r) for r in rows]

    def get_unresolved_citations(self) -> List[Citation]:
        """Citations where the target work has not yet been resolved."""
        rows = self._conn.execute(
            "SELECT * FROM citations WHERE target_work_id IS NULL"
        ).fetchall()
        return [self._row_to_citation(r) for r in rows]

    # ------------------------------------------------------------------
    # Amendment links
    # ------------------------------------------------------------------

    def save_amendment_link(self, link: AmendmentLink) -> None:
        """Insert or update an AmendmentLink."""
        with self._transaction():
            self._conn.execute("""
                INSERT INTO amendment_links (
                    id, amendment_work_id, base_work_id, base_work_ref,
                    effective_date, staatsblad_ref, confidence, resolved, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    base_work_id=excluded.base_work_id,
                    effective_date=excluded.effective_date,
                    confidence=excluded.confidence,
                    resolved=excluded.resolved,
                    metadata=excluded.metadata
            """, (
                link.id, link.amendment_work_id, link.base_work_id,
                link.base_work_ref,
                link.effective_date.isoformat() if link.effective_date else None,
                link.staatsblad_ref, link.confidence,
                1 if link.resolved else 0,
                json.dumps(link.metadata),
            ))

    def get_amendment_links_for_base(self, base_work_id: str) -> List[AmendmentLink]:
        """All amendments that target a given base law, ordered by effective date."""
        rows = self._conn.execute(
            "SELECT * FROM amendment_links WHERE base_work_id = ? ORDER BY effective_date",
            (base_work_id,),
        ).fetchall()
        return [self._row_to_amendment_link(r) for r in rows]

    def get_amendment_links_for_amendment(
        self, amendment_work_id: str
    ) -> List[AmendmentLink]:
        """Which base laws does this wijzigingswet target?"""
        rows = self._conn.execute(
            "SELECT * FROM amendment_links WHERE amendment_work_id = ?",
            (amendment_work_id,),
        ).fetchall()
        return [self._row_to_amendment_link(r) for r in rows]

    def get_unresolved_amendment_links(self) -> List[AmendmentLink]:
        """Amendment links where the base law has not yet been matched to a Work."""
        rows = self._conn.execute(
            "SELECT * FROM amendment_links WHERE resolved = 0"
        ).fetchall()
        return [self._row_to_amendment_link(r) for r in rows]

    # ------------------------------------------------------------------
    # Row deserializers
    # ------------------------------------------------------------------

    def _row_to_work(self, row: sqlite3.Row) -> Work:
        return Work(
            id=row["id"],
            uri=row["uri"],
            source_type=SourceType(row["source_type"]),
            official_id=row["official_id"],
            title=row["title"],
            short_title=row["short_title"],
            document_type=row["document_type"] or "",
            jurisdiction=row["jurisdiction"] or "SR",
            language=row["language"] or "nl",
            status=DocumentStatus(row["status"]) if row["status"] else DocumentStatus.UNKNOWN,
            date_enacted=date.fromisoformat(row["date_enacted"]) if row["date_enacted"] else None,
            date_first_in_force=date.fromisoformat(row["date_first_in_force"]) if row["date_first_in_force"] else None,
            source_url=row["source_url"],
            source_api=row["source_api"],
            retrieved_at=datetime.fromisoformat(row["retrieved_at"]) if row["retrieved_at"] else None,
            subject_areas=json.loads(row["subject_areas"]) if row["subject_areas"] else [],
            keywords=json.loads(row["keywords"]) if row["keywords"] else [],
            replaces=json.loads(row["replaces"]) if row["replaces"] else [],
            replaced_by=json.loads(row["replaced_by"]) if row["replaced_by"] else [],
            implements=json.loads(row["implements"]) if row["implements"] else [],
            implemented_by=json.loads(row["implemented_by"]) if row["implemented_by"] else [],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def _row_to_expression(self, row: sqlite3.Row) -> Expression:
        return Expression(
            id=row["id"],
            uri=row["uri"],
            work_id=row["work_id"],
            work_uri=row["work_uri"],
            version_date=date.fromisoformat(row["version_date"]),
            in_force=TemporalExtent(
                start=date.fromisoformat(row["in_force_start"]) if row["in_force_start"] else None,
                end=date.fromisoformat(row["in_force_end"]) if row["in_force_end"] else None,
            ),
            title=row["title"],
            language=row["language"] or "nl",
            status=DocumentStatus(row["status"]) if row["status"] else DocumentStatus.UNKNOWN,
            source_url=row["source_url"],
            retrieved_at=datetime.fromisoformat(row["retrieved_at"]) if row["retrieved_at"] else None,
            checksum=row["checksum"],
            full_text=row["full_text"],
            previous_expression_id=row["previous_expression_id"],
            next_expression_id=row["next_expression_id"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def _row_to_manifestation(self, row: sqlite3.Row) -> Manifestation:
        return Manifestation(
            id=row["id"],
            uri=row["uri"],
            expression_id=row["expression_id"],
            expression_uri=row["expression_uri"],
            format=ManifestationType(row["format"]),
            media_type=row["media_type"] or "",
            storage_path=row["storage_path"],
            checksum_sha256=row["checksum_sha256"],
            byte_size=row["byte_size"],
            source_url=row["source_url"],
            retrieved_at=datetime.fromisoformat(row["retrieved_at"]) if row["retrieved_at"] else None,
            http_headers=json.loads(row["http_headers"]) if row["http_headers"] else {},
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def _row_to_fragment(self, row: sqlite3.Row) -> Fragment:
        anchors_raw = json.loads(row["anchors"]) if row["anchors"] else []
        anchors = []
        for a in anchors_raw:
            from .models import AnchorType
            anchors.append(FragmentAnchor(
                anchor_type=AnchorType(a["anchor_type"]),
                structural_path=a.get("structural_path"),
                text_hash=a.get("text_hash"),
                text_preview=a.get("text_preview"),
                char_offset_start=a.get("char_offset_start"),
                char_offset_end=a.get("char_offset_end"),
                heading_context=a.get("heading_context"),
            ))

        return Fragment(
            id=row["id"],
            uri=row["uri"],
            expression_id=row["expression_id"],
            expression_uri=row["expression_uri"],
            work_id=row["work_id"],
            fragment_type=resolve_fragment_type(row["fragment_type"]),
            number=row["number"] or "",
            title=row["title"],
            parent_fragment_id=row["parent_fragment_id"],
            position=row["position"] or 0,
            depth=row["depth"] or 0,
            text=row["text"] or "",
            heading_path=json.loads(row["heading_path"]) if row["heading_path"] else [],
            anchors=anchors,
            extraction_method=row["extraction_method"] or "structural",
            confidence=row["confidence"] if row["confidence"] is not None else 1.0,
            extracted_at=datetime.fromisoformat(row["extracted_at"]) if row["extracted_at"] else None,
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def _row_to_citation(self, row: sqlite3.Row) -> Citation:
        return Citation(
            id=row["id"],
            citation_type=CitationType(row["citation_type"]),
            source_work_id=row["source_work_id"],
            source_fragment_id=row["source_fragment_id"],
            source_version_date=date.fromisoformat(row["source_version_date"]) if row["source_version_date"] else None,
            target_work_id=row["target_work_id"],
            target_fragment_id=row["target_fragment_id"],
            target_version_date=date.fromisoformat(row["target_version_date"]) if row["target_version_date"] else None,
            raw_text=row["raw_text"] or "",
            confidence=row["confidence"] if row["confidence"] is not None else 1.0,
            valid_from=date.fromisoformat(row["valid_from"]) if row["valid_from"] else None,
            valid_to=date.fromisoformat(row["valid_to"]) if row["valid_to"] else None,
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def _row_to_amendment_link(self, row: sqlite3.Row) -> AmendmentLink:
        return AmendmentLink(
            id=row["id"],
            amendment_work_id=row["amendment_work_id"],
            base_work_id=row["base_work_id"],
            base_work_ref=row["base_work_ref"],
            effective_date=date.fromisoformat(row["effective_date"]) if row["effective_date"] else None,
            staatsblad_ref=row["staatsblad_ref"],
            confidence=row["confidence"] if row["confidence"] is not None else 1.0,
            resolved=bool(row["resolved"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
