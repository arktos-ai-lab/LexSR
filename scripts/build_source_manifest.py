"""
Write manifest/raw_sources.csv: one row per downloaded source file, with its
SHA-256, so anyone who re-runs the scrapers can check they obtained the same
documents the paper's corpus was built from (government sites change).

Usage:
    python scripts/build_source_manifest.py
    python scripts/build_source_manifest.py --check   # verify data/raw against the manifest

Columns: source, file, bytes, sha256, url. The url column is filled for case
law (rechtspraak.sr); the legislation scrapers did not record per-file URLs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifest" / "raw_sources.csv"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def caselaw_urls(db: Path) -> dict:
    if not db.exists():
        return {}
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = conn.execute("SELECT source_url FROM works WHERE source_type='case_law'").fetchall()
    return {u.rstrip("/").rsplit("/", 1)[-1] + ".html": u for (u,) in rows if u}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw-dir", default=str(ROOT / "data" / "raw"))
    ap.add_argument("--db", default=str(ROOT / "data" / "canonical.db"))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    raw = Path(args.raw_dir)

    if args.check:
        with open(MANIFEST, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        missing = changed = 0
        for r in rows:
            p = raw / r["source"] / r["file"]
            if not p.exists():
                missing += 1
            elif sha256(p) != r["sha256"]:
                changed += 1
        print(f"{len(rows)} files in manifest: {len(rows) - missing - changed} identical, "
              f"{changed} different, {missing} missing")
        return 0 if not (missing or changed) else 1

    urls = caselaw_urls(Path(args.db))
    rows = []
    for p in sorted(raw.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(raw)
        source, file = rel.parts[0], "/".join(rel.parts[1:])
        rows.append({
            "source": source,
            "file": file,
            "bytes": p.stat().st_size,
            "sha256": sha256(p),
            "url": urls.get(file, "") if source == "rechtspraak" else "",
        })
    MANIFEST.parent.mkdir(exist_ok=True)
    with open(MANIFEST, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["source", "file", "bytes", "sha256", "url"])
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
