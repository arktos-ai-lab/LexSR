"""One-off: smoke-test every registered scraper's .scrape() with a hard
per-source timeout, so one slow/broken source doesn't block visibility
into the rest. Metadata discovery only -- no downloads, no OCR."""

import sys
import time
import multiprocessing as mp

from lexsr.ingestion.scrapers import get_all_scrapers


def _run_one(source_name, rate_limit, q):
    from lexsr.ingestion.scrapers import get_all_scrapers
    scraper = next(s for s in get_all_scrapers(rate_limit=rate_limit) if s.source_name == source_name)
    try:
        result = scraper.scrape()
        q.put(("ok", len(result.documents), len(result.errors)))
    except Exception as exc:
        q.put(("exception", str(exc), None))


def main():
    names = [s.source_name for s in get_all_scrapers()]
    print(f"{len(names)} scrapers total: {names}")

    for name in names:
        q = mp.Queue()
        p = mp.Process(target=_run_one, args=(name, 1.0, q))
        t0 = time.time()
        p.start()
        p.join(timeout=90)
        elapsed = time.time() - t0

        if p.is_alive():
            p.terminate()
            p.join()
            print(f"{name:20s} TIMED OUT after {elapsed:.0f}s")
            continue

        if not q.empty():
            status, a, b = q.get()
            if status == "ok":
                print(f"{name:20s} docs={a:4d}  errors={b}  ({elapsed:.1f}s)")
            else:
                print(f"{name:20s} EXCEPTION: {a}  ({elapsed:.1f}s)")
        else:
            print(f"{name:20s} died with no result ({elapsed:.1f}s)")


if __name__ == "__main__":
    sys.exit(main() or 0)
