"""
Bronze layer: immutable raw storage.

Stores exact bytes retrieved from scrapers and APIs with full provenance.
Every derived product (Silver, Gold) traces back to a Bronze record.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BronzeRecord:
    """A single raw payload stored in the Bronze layer."""
    id: str                            # SHA-256 of content, or explicit ID
    source_type: str                   # bwb, rechtspraak, cvdr, eurlex, etc.
    source_url: str                    # URL or API endpoint
    content_type: str                  # application/xml, text/html, application/pdf
    content: bytes                     # raw bytes
    checksum_sha256: str = ""          # SHA-256 of content
    byte_size: int = 0
    retrieved_at: str = ""             # ISO-8601
    http_status: int = 200
    http_headers: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.checksum_sha256 and self.content:
            self.checksum_sha256 = hashlib.sha256(self.content).hexdigest()
        if not self.byte_size and self.content:
            self.byte_size = len(self.content)
        if not self.retrieved_at:
            self.retrieved_at = datetime.now().isoformat()


class BronzeStore:
    """
    SQLite-backed Bronze layer for raw document storage.

    Stores raw bytes immutably with deduplication by content hash.
    """

    def __init__(self, db_path: str = "data/bronze.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS bronze_records (
                id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                source_url TEXT NOT NULL,
                content_type TEXT NOT NULL,
                content BLOB NOT NULL,
                checksum_sha256 TEXT NOT NULL,
                byte_size INTEGER NOT NULL,
                retrieved_at TEXT NOT NULL,
                http_status INTEGER DEFAULT 200,
                http_headers TEXT DEFAULT '{}',
                metadata TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_bronze_source_type
            ON bronze_records(source_type);

            CREATE INDEX IF NOT EXISTS idx_bronze_checksum
            ON bronze_records(checksum_sha256);

            CREATE INDEX IF NOT EXISTS idx_bronze_source_url
            ON bronze_records(source_url);
        """)
        self._conn.commit()

    def store(self, record: BronzeRecord) -> bool:
        """
        Store a Bronze record. Returns True if new, False if duplicate.

        Deduplicates by content hash — same bytes won't be stored twice.
        """
        # Check for duplicate
        existing = self._conn.execute(
            "SELECT id FROM bronze_records WHERE checksum_sha256 = ?",
            (record.checksum_sha256,),
        ).fetchone()
        if existing:
            logger.debug("Duplicate content hash %s, skipping", record.checksum_sha256[:12])
            return False

        self._conn.execute("""
            INSERT OR IGNORE INTO bronze_records
                (id, source_type, source_url, content_type, content,
                 checksum_sha256, byte_size, retrieved_at,
                 http_status, http_headers, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.id, record.source_type, record.source_url,
            record.content_type, record.content,
            record.checksum_sha256, record.byte_size, record.retrieved_at,
            record.http_status,
            json.dumps(record.http_headers),
            json.dumps(record.metadata),
        ))
        self._conn.commit()
        return True

    def get(self, record_id: str) -> Optional[BronzeRecord]:
        """Retrieve a Bronze record by ID."""
        row = self._conn.execute(
            "SELECT * FROM bronze_records WHERE id = ?", (record_id,)
        ).fetchone()
        if not row:
            return None
        return BronzeRecord(
            id=row["id"],
            source_type=row["source_type"],
            source_url=row["source_url"],
            content_type=row["content_type"],
            content=row["content"],
            checksum_sha256=row["checksum_sha256"],
            byte_size=row["byte_size"],
            retrieved_at=row["retrieved_at"],
            http_status=row["http_status"],
            http_headers=json.loads(row["http_headers"]) if row["http_headers"] else {},
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def get_by_url(self, source_url: str) -> List[BronzeRecord]:
        """Retrieve all Bronze records for a source URL (may have multiple versions)."""
        rows = self._conn.execute(
            "SELECT * FROM bronze_records WHERE source_url = ? ORDER BY retrieved_at DESC",
            (source_url,),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def list_by_source(self, source_type: str, limit: int = 100) -> List[BronzeRecord]:
        """List Bronze records by source type (without content for efficiency)."""
        rows = self._conn.execute(
            "SELECT id, source_type, source_url, content_type, '' as content, "
            "checksum_sha256, byte_size, retrieved_at, http_status, http_headers, metadata "
            "FROM bronze_records WHERE source_type = ? ORDER BY retrieved_at DESC LIMIT ?",
            (source_type, limit),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def stats(self) -> Dict[str, Any]:
        """Return statistics about the Bronze store."""
        total = self._conn.execute("SELECT COUNT(*) FROM bronze_records").fetchone()[0]
        by_type = {}
        for row in self._conn.execute(
            "SELECT source_type, COUNT(*), SUM(byte_size) "
            "FROM bronze_records GROUP BY source_type"
        ).fetchall():
            by_type[row[0]] = {"count": row[1], "total_bytes": row[2]}
        return {"total_records": total, "by_source_type": by_type}

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _row_to_record(self, row) -> BronzeRecord:
        return BronzeRecord(
            id=row["id"],
            source_type=row["source_type"],
            source_url=row["source_url"],
            content_type=row["content_type"],
            content=row["content"] if row["content"] else b"",
            checksum_sha256=row["checksum_sha256"],
            byte_size=row["byte_size"],
            retrieved_at=row["retrieved_at"],
            http_status=row["http_status"],
            http_headers=json.loads(row["http_headers"]) if row["http_headers"] else {},
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
