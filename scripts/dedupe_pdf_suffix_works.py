"""
One-off cleanup: merge duplicate works created by a bug in cmd_ingest_pdfs
that passed the PDF filename (including the .pdf extension) into the title
generator instead of the stem. This produced a second, near-duplicate work
for every PDF whose content already existed under a clean title, since the
existing rows have no checksum recorded (so hash-based dedup never matched).

For each group of works with the same normalized title (case/whitespace/
trailing ".pdf" ignored):
  - keep the member already referenced by amendment_links or citations,
    breaking ties by earliest created_at, then by not ending in ".pdf"
  - delete every other member and all rows that reference it

Safe to run once; does nothing if there are no duplicate groups left.
"""

import re
import sqlite3
import sys
from collections import defaultdict

DB = "data/canonical.db"


def normalize_title(title: str) -> str:
    t = re.sub(r"\.pdf$", "", title, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def reference_count(conn, work_id: str) -> int:
    c = conn.cursor()
    n = 0
    n += c.execute(
        "SELECT COUNT(*) FROM amendment_links WHERE amendment_work_id=? OR base_work_id=?",
        (work_id, work_id),
    ).fetchone()[0]
    n += c.execute(
        "SELECT COUNT(*) FROM citations WHERE source_work_id=? OR target_work_id=?",
        (work_id, work_id),
    ).fetchone()[0]
    n += c.execute(
        "SELECT COUNT(*) FROM amendments WHERE amendment_work_id=? OR base_work_id=?",
        (work_id, work_id),
    ).fetchone()[0]
    return n


def delete_work(conn, work_id: str) -> dict:
    c = conn.cursor()
    expr_ids = [r[0] for r in c.execute(
        "SELECT id FROM expressions WHERE work_id=?", (work_id,)
    ).fetchall()]

    counts = {"fragments": 0, "expressions": len(expr_ids), "citations": 0,
              "amendment_links": 0, "amendments": 0, "version_diffs": 0,
              "manifestations": 0}

    counts["fragments"] = c.execute(
        "DELETE FROM fragments WHERE work_id=?", (work_id,)
    ).rowcount

    for eid in expr_ids:
        counts["manifestations"] += c.execute(
            "DELETE FROM manifestations WHERE expression_id=?", (eid,)
        ).rowcount
        c.execute(
            "DELETE FROM version_diffs WHERE from_expression_id=? OR to_expression_id=?",
            (eid, eid),
        )

    counts["citations"] = c.execute(
        "DELETE FROM citations WHERE source_work_id=? OR target_work_id=?",
        (work_id, work_id),
    ).rowcount
    counts["amendment_links"] = c.execute(
        "DELETE FROM amendment_links WHERE amendment_work_id=? OR base_work_id=?",
        (work_id, work_id),
    ).rowcount
    counts["amendments"] = c.execute(
        "DELETE FROM amendments WHERE amendment_work_id=? OR base_work_id=?",
        (work_id, work_id),
    ).rowcount

    c.execute("DELETE FROM expressions WHERE work_id=?", (work_id,))
    c.execute("DELETE FROM work_metadata WHERE work_id=?", (work_id,))
    c.execute("DELETE FROM works WHERE id=?", (work_id,))

    return counts


def main():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    rows = c.execute("SELECT id, title, created_at FROM works").fetchall()
    print(f"Total works: {len(rows)}")

    groups = defaultdict(list)
    for wid, title, created_at in rows:
        groups[normalize_title(title)].append((wid, title, created_at))

    dupe_groups = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"Duplicate title groups: {len(dupe_groups)}")
    total_dupe_works = sum(len(v) for v in dupe_groups.values())
    print(f"Works involved: {total_dupe_works}")

    if not dupe_groups:
        print("Nothing to do.")
        return

    deleted = 0
    kept = 0
    frag_deleted = 0

    for norm_title, members in dupe_groups.items():
        scored = []
        for wid, title, created_at in members:
            refs = reference_count(conn, wid)
            scored.append((refs, created_at or "", not title.lower().endswith(".pdf"), wid, title))

        # Prefer: most references, then earliest created_at, then non-".pdf" title
        scored.sort(key=lambda x: (-x[0], x[1], not x[2]))
        keep = scored[0]
        kept += 1

        for entry in scored[1:]:
            wid = entry[3]
            counts = delete_work(conn, wid)
            deleted += 1
            frag_deleted += counts["fragments"]

    conn.commit()

    remaining = c.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    remaining_frags = c.execute("SELECT COUNT(*) FROM fragments").fetchone()[0]

    print(f"\nKept:    {kept} canonical works")
    print(f"Deleted: {deleted} duplicate works ({frag_deleted:,} fragments)")
    print(f"Remaining: {remaining} works, {remaining_frags:,} fragments")

    conn.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
