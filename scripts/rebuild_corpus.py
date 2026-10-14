"""
Rebuild the LexSR corpus from the public sources, in the order used for the
JURIX 2026 paper.

    python scripts/rebuild_corpus.py              # full run
    python scripts/rebuild_corpus.py --from consolidate   # resume at a step

Steps (each is an ordinary `python -m lexsr` command and can be run alone):

  1. ingest          scrape the ten live government sources into data/raw/
                     and the canonical store (OCR via Tesseract where needed)
  2. ingest-pdfs     process any PDFs already in data/raw/ (locally held archives)
  3. ingest-caselaw  the first 300 decisions from the rechtspraak.sr sitemap
  4. consolidate     parse amendment acts and apply them
  5. link-citations  extract and link citations across all fragments
  6. build-graph     write data/knowledge_graph.graphml and its statistics
  7. stats           print corpus statistics
  8. manifest        write manifest/raw_sources.csv (SHA-256 per source file)

Ingestion skips documents already stored, so an interrupted run can simply be
started again. Government sites change: a rebuild today will not return
exactly the paper's documents. Compare with `python scripts/build_source_manifest.py
--check`, which checks data/raw/ against the committed manifest.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STEPS = [
    ("ingest", ["-m", "lexsr", "ingest"]),
    ("ingest-pdfs", ["-m", "lexsr", "ingest-pdfs"]),
    ("ingest-caselaw", ["-m", "lexsr", "ingest-caselaw", "--limit", "300"]),
    ("consolidate", ["-m", "lexsr", "consolidate"]),
    ("link-citations", ["-m", "lexsr", "link-citations"]),
    ("build-graph", ["-m", "lexsr", "build-graph"]),
    ("stats", ["-m", "lexsr", "stats"]),
    ("manifest", ["scripts/build_source_manifest.py"]),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="start", choices=[s for s, _ in STEPS], default="ingest")
    args = ap.parse_args()

    names = [s for s, _ in STEPS]
    for name, cmd in STEPS[names.index(args.start):]:
        print(f"\n=== {name} ===", flush=True)
        rc = subprocess.call([sys.executable, *cmd], cwd=ROOT)
        if rc != 0:
            print(f"Step '{name}' failed (exit {rc}). Fix and resume with --from {name}")
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
