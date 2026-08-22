"""
Amendment parser diagnostics — characterizes where the parser fails.

Usage:
    python scripts/amendment_diagnostics.py
    python scripts/amendment_diagnostics.py --db data/canonical.db --n 40
    python scripts/amendment_diagnostics.py --json > data/amendment_diagnostics.json

Outputs a per-document breakdown of which parsing stage failed, suitable
for inclusion in the paper's amendment extraction evaluation section.

Failure stages
--------------
OK          Parser extracted at least one AmendmentInstruction.
ZERO_INSTR  Parser ran but extracted 0 instructions.
  └ NO_SECTIONS   _split_into_sections found 0 article sections.
  └ NO_BLOCKS     Sections found but _split_blocks found no labelled blocks.
  └ NO_MATCH      Blocks found but no operation patterns matched (all fallbacks).
NO_TEXT     No fragment text available in the DB for this work.
NO_LINK     Work is not in the amendment_links table.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lexsr.consolidation.parser import AmendmentParser, _split_blocks
from lexsr.consolidation.amendment import OperationType


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------

STAGE_OK          = "OK"           # ≥1 real (non-fallback) instruction extracted
STAGE_ALL_FALLBACK = "ALL_FALLBACK" # instructions exist but all are parse_error fallbacks
STAGE_NO_TEXT     = "NO_TEXT"
STAGE_NO_LINK     = "NO_LINK"
STAGE_NO_SECTIONS = "ZERO_INSTR:NO_SECTIONS"
STAGE_NO_BLOCKS   = "ZERO_INSTR:NO_BLOCKS"
STAGE_NO_MATCH    = "ZERO_INSTR:NO_MATCH"


@dataclass
class DiagnosticRow:
    work_id: str
    title: str
    stage: str
    n_sections: int = 0
    n_blocks: int = 0
    n_instructions: int = 0    # total instructions (including fallbacks)
    n_real_instructions: int = 0  # non-fallback instructions only
    n_fallback: int = 0           # instructions that hit parse_error fallback
    parse_method: str = ""
    base_work_ref: str = ""
    resolved: bool = False
    text_len: int = 0
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "work_id": self.work_id,
            "title": self.title,
            "stage": self.stage,
            "n_sections": self.n_sections,
            "n_blocks": self.n_blocks,
            "n_instructions": self.n_instructions,
            "n_real_instructions": self.n_real_instructions,
            "n_fallback": self.n_fallback,
            "parse_method": self.parse_method,
            "base_work_ref": self.base_work_ref,
            "resolved": self.resolved,
            "text_len": self.text_len,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Text reconstruction from fragments
# ---------------------------------------------------------------------------

def _get_text_and_title(conn: sqlite3.Connection, work_id: str) -> tuple[str, str]:
    """Return (reconstructed_text, title) for a work from its fragments."""
    c = conn.cursor()
    c.execute("SELECT title FROM works WHERE id = ?", (work_id,))
    row = c.fetchone()
    title = row[0] if row else work_id

    c.execute("""
        SELECT f.fragment_type, f.number, f.text
        FROM fragments f
        JOIN expressions e ON f.expression_id = e.id
        WHERE e.work_id = ?
        ORDER BY f.position
    """, (work_id,))
    rows = c.fetchall()

    parts = []
    for ftype, number, text in rows:
        if not text:
            continue
        if ftype == "article":
            parts.append("Artikel %s\n%s" % (number, text))
        else:
            parts.append(text)

    return "\n\n".join(parts), title


# ---------------------------------------------------------------------------
# Diagnostic logic
# ---------------------------------------------------------------------------

def _diagnose_one(
    parser: AmendmentParser,
    conn: sqlite3.Connection,
    work_id: str,
    base_work_ref: str,
    resolved: bool,
) -> DiagnosticRow:
    text, title = _get_text_and_title(conn, work_id)

    row = DiagnosticRow(
        work_id=work_id,
        title=title,
        stage=STAGE_NO_TEXT,
        base_work_ref=base_work_ref,
        resolved=resolved,
    )

    if not text.strip():
        return row

    row.text_len = len(text)

    # Parse without LLM so we can see raw regex results
    result = parser.parse(text, title=title)
    row.n_instructions = len(result.instructions)
    row.parse_method    = result.parse_method

    # Classify instructions: real vs fallback
    fallbacks = [i for i in result.instructions
                 if i.metadata.get("parse_error") is not None]
    real      = [i for i in result.instructions
                 if i.metadata.get("parse_error") is None]
    row.n_fallback          = len(fallbacks)
    row.n_real_instructions = len(real)

    # Also count sections and blocks for all cases
    sections = parser._split_into_sections(text)
    row.n_sections = len(sections)
    total_blocks = sum(len(_split_blocks(sec)) for _, sec in sections)
    row.n_blocks = total_blocks

    if row.n_real_instructions > 0:
        row.stage = STAGE_OK
        return row

    if row.n_instructions > 0:
        # All instructions are fallbacks — parser ran but matched nothing real
        row.stage = STAGE_ALL_FALLBACK
        row.notes = ("%d fallback instructions; operative patterns did not match"
                     % row.n_fallback)
        return row

    # Drill down: which stage failed?
    sections = parser._split_into_sections(text)
    row.n_sections = len(sections)

    if len(sections) == 0 or (len(sections) == 1 and sections[0][0] == "1"
                               and len(sections[0][1]) == len(text.strip())):
        # No Artikel N boundaries found — _split_into_sections returned the
        # whole document as one pseudo-section "1".
        row.stage = STAGE_NO_SECTIONS
        row.notes = "no Artikel N delimiters found in text"
        return row

    # Count blocks across all sections
    total_blocks = 0
    all_fallback = True
    for _, sec_text in sections:
        blocks = _split_blocks(sec_text)
        total_blocks += len(blocks)
        for _, block in blocks:
            if block.strip() and "parse_error" not in block:
                all_fallback = False

    row.n_blocks = total_blocks

    if total_blocks == 0:
        row.stage = STAGE_NO_BLOCKS
        row.notes = "_split_blocks found no blocks in any section"
    else:
        # Blocks exist but nothing matched — all instructions hit the fallback
        non_fallback = [
            inst for inst in result.instructions
            if inst.operation != OperationType.MODIFY
               or inst.metadata.get("parse_error") is None
        ]
        if non_fallback:
            # Some non-fallback instructions exist (shouldn't reach here)
            row.stage = STAGE_OK
        else:
            row.stage = STAGE_NO_MATCH
            row.notes = (
                "%d blocks found but all hit operation-detection fallback; "
                "likely no matching regex patterns for operative text" % total_blocks
            )

    return row


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_diagnostics(
    db_path: str,
    n: int = 33,
    use_llm: bool = False,
) -> List[DiagnosticRow]:
    """
    Sample n amendment works from the DB, run the parser, classify failures.

    Parameters
    ----------
    db_path:  Path to canonical.db.
    n:        How many amendment_links entries to sample (default: all 33).
    use_llm:  If True, enable LLM pass (slower, requires Qwen running).
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Get amendment works from amendment_links
    c.execute("""
        SELECT amendment_work_id, base_work_ref, resolved
        FROM amendment_links
        ORDER BY resolved DESC, amendment_work_id
        LIMIT ?
    """, (n,))
    links = c.fetchall()

    # Build a set of all work_ids in the DB for quick lookup
    c.execute("SELECT id FROM works")
    known_ids = {r[0] for r in c.fetchall()}

    parser = AmendmentParser(use_llm=use_llm)
    rows: List[DiagnosticRow] = []

    for work_id, base_work_ref, resolved in links:
        if work_id not in known_ids:
            rows.append(DiagnosticRow(
                work_id=work_id,
                title=work_id,
                stage=STAGE_NO_LINK,
                base_work_ref=base_work_ref or "",
                resolved=bool(resolved),
                notes="work_id not found in works table",
            ))
            continue

        row = _diagnose_one(
            parser, conn, work_id,
            base_work_ref=base_work_ref or "",
            resolved=bool(resolved),
        )
        rows.append(row)

    conn.close()
    return rows


def print_report(rows: List[DiagnosticRow], output_json: bool = False) -> None:
    if output_json:
        print(json.dumps([r.to_dict() for r in rows], ensure_ascii=False, indent=2))
        return

    # Stage summary
    from collections import Counter
    stage_counts = Counter(r.stage for r in rows)

    print("Amendment parser diagnostics")
    print("=" * 60)
    print("Total sampled: %d" % len(rows))
    print()
    print("Stage breakdown:")
    for stage, count in sorted(stage_counts.items(), key=lambda x: -x[1]):
        pct = count / len(rows) * 100 if rows else 0
        print("  %-30s %3d  (%.0f%%)" % (stage, count, pct))
    print()

    # Per-row details
    hdr = "R  %-16s  %-45s  sec blk real fall  %s"
    print(hdr % ("STAGE", "TITLE", "NOTES"))
    print("-" * 110)
    for r in rows:
        resolved_mark = "R" if r.resolved else " "
        print("%s  %-16s  %-45s  %3d %3d  %3d  %3d  %s" % (
            resolved_mark,
            r.stage[:16],
            r.title[:45],
            r.n_sections,
            r.n_blocks,
            r.n_real_instructions,
            r.n_fallback,
            r.notes[:55],
        ))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/canonical.db",
                    help="Path to canonical.db (default: data/canonical.db)")
    ap.add_argument("--n", type=int, default=33,
                    help="Number of amendment links to sample (default: all)")
    ap.add_argument("--llm", action="store_true",
                    help="Enable LLM pass (requires Qwen running at localhost:8000)")
    ap.add_argument("--json", action="store_true",
                    help="Output JSON instead of ASCII table")
    args = ap.parse_args()

    rows = run_diagnostics(args.db, n=args.n, use_llm=args.llm)
    print_report(rows, output_json=args.json)
