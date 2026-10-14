"""
Export human-verification tasks for the claims made in the JURIX 2026 paper.

Each task is a JSONL file in annotation/tasks/, one item per line, with a
stable item id so labels survive re-export. Samples are seeded, so the
same database always yields the same items.

Usage:
    python annotation/export_tasks.py --db data/canonical_backup_20260913_submitted.db

Tasks
-----
gold           every case of the 61-case citation benchmark: is the expected
               answer the right one for the input?
instructions   every instruction the regex parser extracts from the amendment
               documents: is it correct?
parse_failures every amendment document with no classified instruction: does
               the stored text contain an operative instruction?
links          random sample of citations the pipeline linked to a work: is
               the link correct? (precision estimate)
gazette        random sample of unlinked gazette references whose year and
               number match a work title: is that the cited act?
segmentation   random sample of court decisions: are the considerations
               split correctly?
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from lexsr.consolidation.parser import AmendmentParser  # noqa: E402
from lexsr.evaluation.dataset import KnownAnswerDataset  # noqa: E402
import amendment_diagnostics as ad  # noqa: E402

TASK_DIR = Path(__file__).resolve().parent / "tasks"
SEED = 20261014

GAZ_REF = re.compile(
    r"(?:S\.?\s*B\.?|G\.?\s*B\.?|Staatsblad|Gouvernementsblad)\D{0,6}(\d{4})\D{1,8}(\d{1,4})", re.I)
GAZ_TITLE = re.compile(r"(?:S\.?\s*B\.?|G\.?\s*B\.?)\D{0,6}(\d{4})\D{1,8}(\d{1,4})", re.I)


def context(text: str, needle: str, width: int = 400) -> str:
    """Return text around the first occurrence of needle, marked with [[ ]]."""
    text = text or ""
    i = text.find(needle) if needle else -1
    if i < 0:
        return text[: 2 * width]
    return (text[max(0, i - width):i] + "[[" + needle + "]]"
            + text[i + len(needle):i + len(needle) + width])


def preceding(text: str, block: str, width: int = 600) -> str:
    """Return the text just before block in the document (heading context)."""
    i = text.find((block or "")[:80])
    return text[max(0, i - width):i] if i > 0 else ""


def export_gold(conn):
    ds = KnownAnswerDataset.suriname_legal_seed()
    for c in ds.cases():
        yield {
            "id": c.id,
            "title": f"{c.category} / {c.difficulty}",
            "fields": {
                "Input text": c.input_text,
                "Expected answer": "\n".join(c.expected_uris) or "(none: should NOT resolve)",
                "Query date": str(c.query_date or ""),
                "Tags": ", ".join(c.tags),
            },
            "question": "Is the expected answer correct for this input?",
        }


def export_instructions(conn):
    parser = AmendmentParser(use_llm=False)
    ids = sorted({r[0] for r in conn.execute("SELECT amendment_work_id FROM amendment_links")})
    for wid in ids:
        text, title = ad._get_text_and_title(conn, wid)
        if not text.strip():
            continue
        real = [i for i in parser.parse(text, title=title).instructions
                if i.metadata.get("parse_error") is None]
        for n, ins in enumerate(real):
            extracted = {k: v for k, v in {
                "operation": ins.operation.value,
                "target law": ins.target_work_ref,
                "article": ins.target_article,
                "paragraph (lid)": ins.target_paragraph,
                "sub": ins.target_sub,
                "insert after": ins.position_after,
                "new article nr": ins.new_article_number,
                "find": ins.find_text,
                "replace with": ins.replace_text,
                "new text": ins.new_text,
                "confidence": ins.confidence,
            }.items() if v not in (None, "")}
            yield {
                "id": f"{wid}#{n}",
                "title": title,
                "fields": {
                    "Preceding text": preceding(text, ins.source_text),
                    "Source block": ins.source_text,
                    "Extracted instruction": json.dumps(extracted, ensure_ascii=False, indent=1),
                },
                "question": "Does the extracted instruction say exactly what the source block says?",
            }


def export_parse_failures(conn, db_path):
    rows = ad.run_diagnostics(db_path, n=10_000)
    seen = set()
    for r in rows:
        if r.stage == "OK" or r.work_id in seen:
            continue
        seen.add(r.work_id)
        text, title = ad._get_text_and_title(conn, r.work_id)
        yield {
            "id": r.work_id,
            "title": title,
            "fields": {"Stored text (everything the parser saw)": text},
            "question": "Does this text contain an operative amendment instruction "
                        "(e.g. 'Artikel 3 vervalt', 'wordt vervangen door')? "
                        "Correct = NO instruction present (paper's claim holds).",
        }


def export_links(conn, n):
    rows = conn.execute("""
        SELECT c.id, c.raw_text, c.citation_type, f.text, w.title, s.title
        FROM citations c
        JOIN works w ON w.id = c.target_work_id
        LEFT JOIN fragments f ON f.id = c.source_fragment_id
        LEFT JOIN works s ON s.id = c.source_work_id
        WHERE c.target_work_id IS NOT NULL
        ORDER BY c.id""").fetchall()
    for cid, raw, ctype, ftext, target, source in random.Random(SEED).sample(rows, min(n, len(rows))):
        yield {
            "id": cid,
            "title": f"{ctype}: {raw}",
            "fields": {
                "Citing document": source or "",
                "Context ([[citation]])": context(ftext, raw),
                "Linked to work": target,
            },
            "question": "Is the citation linked to the act it actually refers to?",
        }


def export_gazette(conn, n):
    titles = conn.execute("SELECT id, title FROM works").fetchall()
    by_num = {}
    for wid, t in titles:
        m = GAZ_TITLE.search(t or "")
        if m:
            by_num.setdefault((m.group(1), int(m.group(2))), []).append(t)
    rows = conn.execute("""
        SELECT c.id, c.raw_text, f.text FROM citations c
        LEFT JOIN fragments f ON f.id = c.source_fragment_id
        WHERE c.target_work_id IS NULL ORDER BY c.id""").fetchall()
    cands = []
    for cid, raw, ftext in rows:
        m = GAZ_REF.search(raw or "")
        if m and (m.group(1), int(m.group(2))) in by_num:
            cands.append((cid, raw, ftext, by_num[(m.group(1), int(m.group(2)))]))
    for cid, raw, ftext, ts in random.Random(SEED).sample(cands, min(n, len(cands))):
        yield {
            "id": cid,
            "title": raw,
            "fields": {
                "Context ([[citation]])": context(ftext, raw),
                "Candidate act(s) in corpus": "\n".join(ts),
            },
            "question": "Is the candidate the act this gazette reference cites? "
                        "(Mind S.B. vs G.B.: different gazettes.)",
        }


def export_segmentation(conn, n):
    works = conn.execute(
        "SELECT id, title, source_url FROM works WHERE source_type='case_law' ORDER BY id").fetchall()
    for wid, title, url in random.Random(SEED).sample(works, min(n, len(works))):
        frs = conn.execute("""SELECT number, text FROM fragments WHERE work_id=?
                              ORDER BY position""", (wid,)).fetchall()
        shown = "\n\n".join(f"── {num or '(unnumbered)'} ──\n{(t or '')[:600]}" for num, t in frs)
        yield {
            "id": wid,
            "title": f"{title} ({len(frs)} considerations)",
            "fields": {"Source page": url or "", "Considerations as segmented": shown},
            "question": "Compare with the source page: are the considerations split at the "
                        "right numbers, with nothing missing?",
        }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/canonical_backup_20260913_submitted.db")
    ap.add_argument("--links", type=int, default=200, help="sample size for link precision")
    ap.add_argument("--gazette", type=int, default=100)
    ap.add_argument("--segmentation", type=int, default=20)
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    TASK_DIR.mkdir(exist_ok=True)
    jobs = {
        "gold": export_gold(conn),
        "instructions": export_instructions(conn),
        "parse_failures": export_parse_failures(conn, args.db),
        "links": export_links(conn, args.links),
        "gazette": export_gazette(conn, args.gazette),
        "segmentation": export_segmentation(conn, args.segmentation),
    }
    meta = {"db": args.db, "seed": SEED, "tasks": {}}
    for name, items in jobs.items():
        items = list(items)
        with open(TASK_DIR / f"{name}.jsonl", "w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        meta["tasks"][name] = len(items)
        print(f"{name:15s} {len(items):5d} items")
    (TASK_DIR / "manifest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
