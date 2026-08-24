"""
One-off migration: fix stale "sr/..." URIs (missing the "/id" prefix
identifiers.py's URI_PREFIX has always used) left over from the original
pre-session ingestion run. Newer rows (this session's ingest-pdfs/ingest
runs) already use the correct "/id/..." form; only the works and
expressions created before ~2026-08-22 were affected.

This alone doesn't fix citation resolution — see to_citation()'s fuzzy
title-match fallback in ocr/citation_extractor.py for the deeper issue
(the citation resolver's abbreviation registry produces idealized
canonical slugs like "grondwet-1987" that don't match real filename-
derived work IDs regardless of URI prefix). Re-run `lexsr link-citations`
after this migration to actually pick up the fix.

Safe to re-run: WHERE uri LIKE 'sr/%' matches nothing once migrated.
"""

import sqlite3
import sys

DB = "data/canonical.db"


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    n_works = cur.execute(
        "UPDATE works SET uri = '/id/' || substr(uri, 4) WHERE uri LIKE 'sr/%'"
    ).rowcount
    n_expr_uri = cur.execute(
        "UPDATE expressions SET uri = '/id/' || substr(uri, 4) WHERE uri LIKE 'sr/%'"
    ).rowcount
    n_expr_work_uri = cur.execute(
        "UPDATE expressions SET work_uri = '/id/' || substr(work_uri, 4) WHERE work_uri LIKE 'sr/%'"
    ).rowcount

    conn.commit()

    print(f"works.uri migrated:          {n_works}")
    print(f"expressions.uri migrated:    {n_expr_uri}")
    print(f"expressions.work_uri fixed:  {n_expr_work_uri}")

    remaining = cur.execute(
        "SELECT COUNT(*) FROM works WHERE uri LIKE 'sr/%'"
    ).fetchone()[0]
    print(f"Remaining stale works.uri rows: {remaining}")

    conn.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
