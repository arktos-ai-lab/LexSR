"""
LexSR command-line interface.

Usage:
    python -m lexsr <command> [options]
    lexsr <command> [options]              # after pip install

Commands:
    stats           Show database statistics
    ingest          Scrape and ingest from all live sources (requires network)
    ingest-pdfs     Process PDFs already in data/raw/
    ingest-caselaw  Scrape rechtspraak.sr court decisions
    link-citations  Backfill citation links for all existing fragments
    index           Build / refresh the BM25 search index
    index-vectors   Build / refresh the dense vector index (embeddings)
    generate        Build the static website from the canonical store
    search <query>  Search the knowledge base (BM25)
    benchmark       Run the citation-resolution benchmark suite
    serve           Serve the generated site locally
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Tesseract path helper (Windows only)
# ---------------------------------------------------------------------------

_TESSERACT_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR",
    r"C:\Program Files (x86)\Tesseract-OCR",
]


def _setup_tesseract() -> bool:
    """Add Tesseract to PATH on Windows if it is not already on PATH."""
    if sys.platform != "win32":
        return True
    import shutil
    if shutil.which("tesseract"):
        return True
    for candidate in _TESSERACT_CANDIDATES:
        if Path(candidate, "tesseract.exe").exists():
            os.environ["PATH"] = os.environ.get("PATH", "") + ";" + candidate
            try:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = str(
                    Path(candidate, "tesseract.exe")
                )
            except ImportError:
                pass
            return True
    return False


def _tesseract_lang(preferred: str = "nld+eng", fallback: str = "eng") -> str:
    """
    Pick a Tesseract language string from what's actually installed.

    Requesting a language whose .traineddata isn't installed makes every
    single OCR call fail outright, so check availability first rather than
    hardcoding "nld" (not installed on every machine that has Tesseract).
    """
    try:
        import pytesseract
        available = set(pytesseract.get_languages(config=""))
    except Exception:
        return fallback

    wanted = preferred.split("+")
    usable = [lang for lang in wanted if lang in available]
    if usable:
        return "+".join(usable)

    print(f"WARNING: none of {wanted} installed for Tesseract (have: {sorted(available)}); "
          f"using '{fallback}'. Install missing traineddata files for better Dutch OCR quality.")
    return fallback


# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

DEFAULT_DB = "data/canonical.db"
DEFAULT_SEARCH_DB = "data/search.db"
DEFAULT_VECTOR_DB = "data/vectors.db"
DEFAULT_RAW_DIR = "data/raw"
DEFAULT_SITE_DIR = "site"
DEFAULT_BASE_URL = "https://wetten.suriname.legal"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_stats(args: argparse.Namespace) -> int:
    import sqlite3 as _sqlite3
    from lexsr.core.store import CanonicalStore

    db = args.db
    if not Path(db).exists():
        print(f"Database not found: {db}")
        print("Run 'python -m lexsr ingest-pdfs' to populate it.")
        return 1

    store = CanonicalStore(db)
    stats = store.stats()

    # Amendment resolution breakdown
    conn = _sqlite3.connect(db)
    c = conn.cursor()
    c.execute("SELECT COUNT(*), SUM(resolved) FROM amendment_links")
    al_total, al_resolved = c.fetchone()
    al_resolved = al_resolved or 0

    # Citation resolution stats from unresolved_references (if table exists)
    cit_unresolved = 0
    try:
        c.execute("SELECT COUNT(*) FROM unresolved_references")
        cit_unresolved = c.fetchone()[0]
    except _sqlite3.OperationalError:
        pass

    # Expressions: original vs consolidated
    c.execute("SELECT COUNT(*) FROM expressions WHERE version_date IS NOT NULL "
              "AND version_date > '2020-01-01'")
    consolidated = c.fetchone()[0]
    conn.close()
    store.close()

    print(f"Database: {db}")
    print(f"  Works:              {stats.get('works', 0):>8,}")
    print(f"  Expressions:        {stats.get('expressions', 0):>8,}  "
          f"({consolidated} consolidated)")
    print(f"  Fragments:          {stats.get('fragments', 0):>8,}")
    print(f"  Citations:          {stats.get('citations', 0):>8,}  "
          f"({cit_unresolved} unresolved)")
    print(f"  Amendment links:    {al_total:>8,}  "
          f"({al_resolved} fully applied, {al_total - al_resolved} linked-only)")
    print(f"  Version diffs:      {stats.get('version_diffs', 0):>8,}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    """Scrape all four live sources and ingest into the canonical store."""
    if not _setup_tesseract():
        print("WARNING: Tesseract not found. OCR quality may be reduced.")

    from lexsr.ingestion.batch_processor import BatchProcessor
    from lexsr.ingestion.scrapers import DNAScraper, SRISScraper, BelastingdienstScraper, MASScraper
    from lexsr.ingestion.scrapers.generic import (
        create_ssb_scraper, create_gov_portal_scraper, create_finance_scraper,
        create_labor_scraper, create_natural_resources_scraper, create_chs_scraper,
    )
    from lexsr.ocr.pipeline import PipelineConfig
    from lexsr.ocr.extractor import OCREngine
    from lexsr.core.store import CanonicalStore
    import time

    store = CanonicalStore(args.db)
    initial = store.stats()
    store.close()

    ocr_config = PipelineConfig(ocr_engine=OCREngine.TESSERACT, tesseract_lang=_tesseract_lang())
    processor = BatchProcessor(
        raw_dir=Path(args.raw_dir),
        canonical_db=args.db,
        search_db=args.search_db,
        ocr_config=ocr_config,
    )

    # The other generic-scraper sources (justice, agriculture, nimos, health,
    # education, kos) either 404 on every guessed URL or reliably time out —
    # their legislation_url in scrapers/generic.py needs to be corrected
    # against the real site structure before they're worth including here.
    scrapers = [
        ("DNA (Parliament)",           DNAScraper(rate_limit=2.0)),
        ("SRIS (Legal Database)",       SRISScraper(rate_limit=2.0)),
        ("Belastingdienst (Tax Auth.)", BelastingdienstScraper(rate_limit=2.0)),
        ("MAS (Central Bank)",          MASScraper(rate_limit=2.0)),
        ("SSB (Standards Bureau)",      create_ssb_scraper(rate_limit=3.0)),
        ("Gov Portal",                  create_gov_portal_scraper(rate_limit=2.0)),
        ("Finance Ministry",            create_finance_scraper(rate_limit=2.0)),
        ("Labor Ministry",              create_labor_scraper(rate_limit=2.0)),
        ("Natural Resources Ministry",  create_natural_resources_scraper(rate_limit=2.0)),
        ("CHS (Electoral Bureau)",      create_chs_scraper(rate_limit=2.0)),
    ]

    totals = dict(scraped=0, processed=0, stored=0, failed=0)

    print(f"Ingesting from {len(scrapers)} sources into {args.db}")
    print(f"Initial: {initial.get('works', 0)} works, {initial.get('fragments', 0):,} fragments")
    print()

    for name, scraper in scrapers:
        print(f"-- {name} --")
        t0 = time.time()
        try:
            r = processor.process_scraper(scraper, limit=args.limit, skip_existing=True)
            elapsed = int(time.time() - t0)
            print(
                f"  scraped={r.total_scraped}  downloaded={r.total_downloaded}"
                f"  stored={r.total_stored}  failed={len(r.failed)}  ({elapsed}s)"
            )
            totals["scraped"] += r.total_scraped
            totals["processed"] += r.total_processed
            totals["stored"] += r.total_stored
            totals["failed"] += len(r.failed)
        except Exception as exc:
            print(f"  ERROR: {exc}")

    store = CanonicalStore(args.db)
    final = store.stats()
    store.close()

    print()
    print(
        f"Done — added {final.get('works', 0) - initial.get('works', 0)} works, "
        f"{final.get('fragments', 0) - initial.get('fragments', 0):,} fragments"
    )
    return 0


def cmd_ingest_caselaw(args: argparse.Namespace) -> int:
    """Scrape rechtspraak.sr and ingest court decisions into the canonical store."""
    from lexsr.core.store import CanonicalStore
    from lexsr.ingestion.scrapers.rechtspraak import RechtspraakScraper
    from lexsr.ingestion.caselaw_pipeline import CaseLawPipeline
    from lexsr.ocr.citation_extractor import CitationExtractor

    store = CanonicalStore(args.db)
    initial = store.stats()

    scraper = RechtspraakScraper(rate_limit=args.rate_limit)
    pipeline = CaseLawPipeline()
    citation_extractor = CitationExtractor(store)

    print(f"Discovering decisions from rechtspraak.sr{f' (limit {args.limit})' if args.limit else ''}...")
    urls = scraper.discover_decision_urls()
    if args.limit:
        urls = urls[:args.limit]
    print(f"{len(urls)} decisions to process")

    processed = skipped = failed = 0
    total_fragments = 0
    total_case_citations = 0
    total_legislation_citations = 0

    for i, url in enumerate(urls, 1):
        if i % 25 == 1:
            print(f"  [{i}/{len(urls)}] processing...")

        try:
            doc = scraper.scrape_decision(url)
            if not doc:
                failed += 1
                continue

            result = pipeline.process_document(doc)
            if not result.success:
                failed += 1
                if args.verbose:
                    print(f"    FAIL {url}: {'; '.join(result.errors)}")
                continue

            existing = store.get_work(result.work.id)
            if existing and not args.force:
                skipped += 1
                continue

            store.save_work(result.work)
            store.save_expression(result.expression)
            for fragment in result.fragments:
                store.save_fragment(fragment)
            for citation in result.citations:
                store.save_citation(citation)

            legislation_citations = citation_extractor.extract_from_fragments(
                result.fragments, source_version_date=result.expression.version_date,
            )
            saved = citation_extractor.save_to_store(legislation_citations)

            processed += 1
            total_fragments += len(result.fragments)
            total_case_citations += len(result.citations)
            total_legislation_citations += saved

        except Exception as exc:
            failed += 1
            if args.verbose:
                print(f"    EXCEPTION {url}: {exc}")

    final = store.stats()
    store.close()

    print(f"\nResults: processed={processed}  skipped={skipped}  failed={failed}")
    print(f"  Considerations extracted: {total_fragments:,}")
    print(f"  Case-to-case citations:   {total_case_citations:,}")
    print(f"  Case-to-legislation citations: {total_legislation_citations:,}")
    print(
        f"Database: {initial.get('works', 0)} -> {final.get('works', 0)} works, "
        f"{initial.get('fragments', 0):,} -> {final.get('fragments', 0):,} fragments"
    )
    return 0


def _title_from_pdf_filename(name: str) -> str:
    """Derive a human title from a PDF filename (matches the scheme already
    used for the existing works, so titles stay consistent)."""
    import re as _re
    stem = _re.sub(r'^\d+[._]', '', name)
    stem = stem.replace('_', ' ').replace('-', ' ')
    stem = _re.sub(r'\s+', ' ', stem).strip()
    return (stem or name)[:100]


def _work_id_from_title(title: str) -> str:
    """Slug + hash suffix, matching the scheme used for the existing works."""
    import re as _re
    import hashlib as _hashlib
    slug = _re.sub(r'[^a-z0-9\s-]', '', title.lower())
    slug = _re.sub(r'\s+', '-', slug).strip('-')[:80]
    suffix = _hashlib.md5(title.encode()).hexdigest()[:8]
    return f"{slug}-{suffix}"


def cmd_ingest_pdfs(args: argparse.Namespace) -> int:
    """Process all PDFs in data/raw/ through the OCR pipeline.

    Skips PDFs already ingested, matched by content checksum against
    existing expressions (safe to re-run after adding new PDFs).
    """
    if not _setup_tesseract():
        print("WARNING: Tesseract not found. Skipping OCR.")

    import hashlib
    from datetime import date
    from lexsr.ocr.pipeline import OCRPipeline, PipelineConfig
    from lexsr.ocr.extractor import OCREngine
    from lexsr.core.store import CanonicalStore

    raw_dir = Path(args.raw_dir)
    if not raw_dir.exists():
        print(f"Raw directory not found: {raw_dir}")
        return 1

    pdfs = sorted(raw_dir.rglob("*.pdf"))
    print(f"Found {len(pdfs)} PDFs in {raw_dir}")

    store = CanonicalStore(args.db)
    initial = store.stats()

    ocr_config = PipelineConfig(ocr_engine=OCREngine.TESSERACT, tesseract_lang=_tesseract_lang())
    pipeline = OCRPipeline(ocr_config)

    processed = skipped = failed = 0

    for i, pdf_path in enumerate(pdfs, 1):
        if i % 20 == 1:
            print(f"  [{i}/{len(pdfs)}] processing...")
        try:
            checksum = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            already = store._conn.execute(
                "SELECT 1 FROM expressions WHERE checksum = ? LIMIT 1", (checksum,)
            ).fetchone()
            if already:
                skipped += 1
                continue

            title = _title_from_pdf_filename(pdf_path.stem)
            work_id = _work_id_from_title(title)

            result = pipeline.process_pdf(
                pdf_path=str(pdf_path),
                work_id=work_id,
                title=title,
                version_date=date.today(),
            )

            if not result.success or not result.fragments:
                failed += 1
                if failed <= 5:
                    print(f"    FAIL {pdf_path.name}: {'; '.join(result.errors) or 'no fragments extracted'}")
                continue

            result.expression.checksum = checksum
            store.save_work(result.work)
            store.save_expression(result.expression)
            for fragment in result.fragments:
                store.save_fragment(fragment)
            processed += 1

        except Exception as exc:
            failed += 1
            if failed <= 5:
                print(f"    FAIL {pdf_path.name}: {exc}")

    final = store.stats()
    store.close()

    print(f"\nResults: processed={processed}  skipped={skipped}  failed={failed}")
    print(
        f"Database: {initial.get('works', 0)} -> {final.get('works', 0)} works, "
        f"{initial.get('fragments', 0):,} -> {final.get('fragments', 0):,} fragments"
    )
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    """Build or refresh the BM25 full-text search index from the canonical store."""
    from lexsr.core.store import CanonicalStore
    from lexsr.search.bm25 import BM25Indexer

    if not Path(args.db).exists():
        print(f"Database not found: {args.db}")
        return 1

    print(f"Building BM25 index: {args.db} -> {args.search_db}")
    store = CanonicalStore(args.db)
    indexer = BM25Indexer(args.search_db)

    works = store.list_works(limit=100_000)
    total_indexed = 0

    for work in works:
        expressions = store.get_expressions_for_work(work.id)
        if not expressions:
            continue
        for expr in expressions:
            fragments = store.get_fragments_for_expression(expr.id)
            for frag in fragments:
                if not frag.text:
                    continue
                metadata = {
                    "work_title": work.title,
                    "work_id": work.id,
                    "expression_id": expr.id,
                    "version_date": expr.version_date.isoformat() if expr.version_date else "",
                    "source_type": work.source_type.value if work.source_type else "",
                    "in_force_start": (
                        expr.in_force.start.isoformat() if expr.in_force and expr.in_force.start else ""
                    ),
                    "in_force_end": (
                        expr.in_force.end.isoformat()
                        if expr.in_force and expr.in_force.end
                        else ""
                    ),
                    "is_latest": expr.id == expressions[-1].id,
                }
                indexer.index_fragment(frag, metadata)
                total_indexed += 1

    store.close()
    print(f"Indexed {total_indexed:,} fragments from {len(works)} works.")
    return 0


def cmd_index_vectors(args: argparse.Namespace) -> int:
    """Build or refresh the dense vector index (multilingual-e5-large + Qdrant)."""
    from lexsr.core.store import CanonicalStore
    from lexsr.search.vector import VectorIndexer

    if not Path(args.db).exists():
        print(f"Database not found: {args.db}")
        return 1

    print(f"Loading embedding model {args.model} (first run downloads it)...")
    indexer = VectorIndexer(model_name=args.model, storage_path=args.vector_db)

    store = CanonicalStore(args.db)
    works = store.list_works(limit=100_000)

    batch = []
    total_indexed = 0

    print(f"Building vector index: {args.db} -> {args.vector_db}")

    for i, work in enumerate(works, 1):
        expressions = store.get_expressions_for_work(work.id)
        if not expressions:
            continue
        for expr in expressions:
            fragments = store.get_fragments_for_expression(expr.id)
            for frag in fragments:
                if not frag.text:
                    continue
                metadata = {
                    "work_title": work.title,
                    "version_date": expr.version_date.isoformat() if expr.version_date else "",
                    "in_force_start": (
                        expr.in_force.start.isoformat() if expr.in_force and expr.in_force.start else ""
                    ),
                    "in_force_end": (
                        expr.in_force.end.isoformat()
                        if expr.in_force and expr.in_force.end
                        else ""
                    ),
                }
                batch.append((frag, metadata))

        if len(batch) >= args.batch_size:
            total_indexed += indexer.index_fragments(batch, batch_size=args.batch_size)
            batch = []

        if i % 100 == 0 or i == len(works):
            print(f"  [{i}/{len(works)}]  indexed so far: {total_indexed:,}")

    if batch:
        total_indexed += indexer.index_fragments(batch, batch_size=args.batch_size)

    store.close()
    print(f"Indexed {total_indexed:,} fragments in vector store ({args.vector_db}).")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    """Generate the complete static website."""
    from lexsr.core.store import CanonicalStore
    from lexsr.static_gen.generator import StaticSiteGenerator

    if not Path(args.db).exists():
        print(f"Database not found: {args.db}")
        return 1

    store = CanonicalStore(args.db)
    stats = store.stats()
    print(f"Generating site from {stats.get('works', 0)} works …")

    gen = StaticSiteGenerator(
        store=store,
        output_dir=args.output,
        base_url=args.base_url,
    )
    gen.generate()
    store.close()

    print(f"Site written to: {args.output}/")
    print(f"Serve locally:   python -m lexsr serve --site {args.output}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """Full-text search the knowledge base."""
    search_db = args.search_db
    if not Path(search_db).exists():
        print(f"Search index not found: {search_db}")
        print("Run 'python -m lexsr index' to build it first.")
        return 1

    from lexsr.search.hybrid import HybridSearchEngine

    use_vector = not args.no_hybrid and Path(args.vector_db).exists()
    if not args.no_hybrid and not use_vector:
        print(f"(vector index not found at {args.vector_db} — BM25-only; "
              f"run 'lexsr index-vectors' to enable hybrid search)")

    engine = HybridSearchEngine(
        bm25_db_path=search_db,
        vector_db_path=args.vector_db,
        use_vector=use_vector,
    )
    results = engine.search(args.query, top_k=args.top_k)

    if not results:
        print("No results found.")
        return 0

    for i, r in enumerate(results, 1):
        meta = r.metadata or {}
        title = meta.get("work_title", "")
        print(f"\n[{i}] {title}  —  {r.uri}")
        print(f"    score={r.score:.4f}  rank={r.rank}")
        if r.snippet:
            print(f"    {r.snippet[:200]}")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Run the citation-resolution benchmark suite."""
    from lexsr.core.resolver import CitationResolver
    from lexsr.evaluation.dataset import KnownAnswerDataset
    from lexsr.evaluation.benchmark import BenchmarkSuite
    from datetime import date

    store = None
    if Path(args.db).exists():
        from lexsr.core.store import CanonicalStore
        store = CanonicalStore(args.db)

    resolver = CitationResolver(store=store, default_date=date.today())
    suite = BenchmarkSuite(resolver=resolver)
    ds = KnownAnswerDataset.suriname_legal_seed()

    print(f"Running benchmark: {ds.count} cases …")
    result = suite.run(ds)

    print(f"\nResults for '{result.suite_name}':")
    print(f"  Total:    {result.total_cases}")
    print(f"  Passed:   {result.passed}")
    print(f"  Failed:   {result.failed}")
    print(f"  Pass rate: {result.pass_rate:.1%}")

    if result.quality_report:
        qr = result.quality_report
        if qr.citation_metrics:
            cm = qr.citation_metrics
            print(f"\nCitation metrics:")
            print(f"  Resolution rate: {cm.resolution_rate:.1%}")
            print(f"  Precision:       {cm.precision:.1%}")
            print(f"  Recall:          {cm.recall:.1%}")
            print(f"  F1:              {cm.f1:.1%}")
        if qr.temporal_metrics:
            tm = qr.temporal_metrics
            print(f"\nTemporal accuracy: {tm.accuracy:.1%}  ({tm.correct_version}/{tm.total_queries})")

    if args.verbose and result.failed_cases():
        print("\nFailed cases:")
        for case in result.failed_cases():
            print(f"  [{case.case_id}] expected={case.expected_uris}  actual={case.actual_uris}")

    if store:
        store.close()
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Serve the static site with Python's built-in HTTP server."""
    import http.server
    import socketserver

    site_dir = Path(args.site)
    if not site_dir.exists():
        print(f"Site directory not found: {site_dir}")
        print("Run 'python -m lexsr generate' first.")
        return 1

    os.chdir(site_dir)
    handler = http.server.SimpleHTTPRequestHandler
    handler.extensions_map = {
        "": "application/octet-stream",
        ".html": "text/html; charset=utf-8",
        ".css": "text/css",
        ".js": "application/javascript",
        ".json": "application/json",
    }

    with socketserver.TCPServer(("", args.port), handler) as httpd:
        url = f"http://localhost:{args.port}/"
        print(f"Serving {site_dir}/ at {url}")
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
    return 0


# ---------------------------------------------------------------------------
# Dutch date parser (shared by cmd_consolidate)
# ---------------------------------------------------------------------------

_DUTCH_MONTHS = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "augustus": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12,
}


def _parse_dutch_date(raw: str):
    """Parse '1 januari 1976' -> date(1976, 1, 1). Returns None on failure."""
    if not raw:
        return None
    from datetime import date as _date
    parts = raw.strip().lower().split()
    if len(parts) == 3:
        try:
            day = int(parts[0])
            month = _DUTCH_MONTHS.get(parts[1])
            year = int(parts[2])
            if month and 1 <= day <= 31 and 1600 <= year <= 2100:
                return _date(year, month, day)
        except (ValueError, TypeError):
            pass
    return None


def _clean_law_name(raw: str) -> str:
    """Strip trailing gazette references and punctuation from a law name."""
    import re as _re
    # Stop before "S.B. 2021 no." or "G.B. 1963 no." or "SB 2021 no"
    raw = _re.split(r'\s+(?:S\.?\s*B\.?|G\.?\s*B\.?)\s+\d', raw, flags=_re.I)[0]
    # Stop before " 2021 no." patterns
    raw = _re.split(r'\s+\d{4}\s+[Nn]o', raw)[0]
    return raw.strip().rstrip('.,;(')


def _extract_base_law_from_title(title: str) -> str:
    """
    Extract the base law name from an amendment document title.

    Examples
    --------
    "Arbeidswet 1963 wijziging S B 2023 no 125"   -> "Arbeidswet 1963"
    "S B 2022 no 150 wijziging van de Wet Inkomstenbelasting 1922"
                                                   -> "Wet Inkomstenbelasting 1922"
    "Wijziging Wet Auteursrecht 1913"              -> "Wet Auteursrecht 1913"
    "Wet wijziging Stedebouwkundige wet S B 1982"  -> "Stedebouwkundige wet"
    """
    import re as _re

    # Strip leading gazette ref  "S B 2021 no 125 " or "G B 1954 no 104 "
    clean = _re.sub(
        r'^(?:S\.?\s*B\.?|G\.?\s*B\.?|SB|GB)\s+\d{4}\s+(?:No\.?\s*)?\d+\s+',
        '', title, flags=_re.I
    ).strip()

    # "Wet wijziging X"  /  "Staatsbesluit wijziging X"  — document type prefix
    m = _re.match(r'^(?:wet|besluit|staatsbesluit)\s+(?:nadere\s+)?wijziging\s+(.+)',
                  clean, _re.I)
    if m:
        return _clean_law_name(m.group(1))

    # "houdende [nadere] wijziging van [de/het] X"
    m = _re.search(r'houdende\s+(?:nadere\s+)?wijziging\s+van\s+(?:de\s+|het\s+)?(.+)',
                   clean, _re.I)
    if m:
        return _clean_law_name(m.group(1))

    # "wijziging van [de/het] X"  (without "houdende")
    m = _re.search(r'\bwijziging\s+van\s+(?:de\s+|het\s+)?(.+)', clean, _re.I)
    if m:
        return _clean_law_name(m.group(1))

    # "[nadere] Wijziging X"  — wijziging at start after stripping gazette ref
    m = _re.match(r'^(?:nadere\s+)?[Ww]ijziging\s+(.+)', clean)
    if m:
        return _clean_law_name(m.group(1))

    # "X wijziging" or "X1972wijziging" — law name before wijziging keyword
    m = _re.match(r'^(.+?)\s*[Ww]ijziging\b', clean)
    if m:
        return m.group(1).strip()

    return ""


def cmd_consolidate(args: argparse.Namespace) -> int:
    """
    Run the full amendment consolidation pipeline on the canonical store.

    For each work identified as a wijzigingswet:
      1. Classify (DocumentClassifier, regex-only for speed)
      2. Parse instructions (AmendmentParser)
      3. Apply to the base law (ConsolidationEngine)
      4. Persist amendment links and new versioned expressions

    Safe to re-run: the engine generates stable IDs and uses ON CONFLICT.
    """
    from datetime import date as _date
    from lexsr.core.store import CanonicalStore
    from lexsr.consolidation import (
        DocumentClassifier, DocumentType,
        AmendmentParser, ConsolidationEngine,
    )

    if not Path(args.db).exists():
        print(f"Database not found: {args.db}")
        return 1

    store = CanonicalStore(args.db)
    classifier = DocumentClassifier(
        use_llm=args.use_llm, llm_url=args.llm_url, model=args.llm_model,
    )
    parser = AmendmentParser(
        use_llm=args.use_llm, llm_url=args.llm_url, model=args.llm_model,
    )
    engine = ConsolidationEngine(store)

    works = store.list_works(limit=100_000)
    print(f"Scanning {len(works)} works for amendments …")

    # --- Pass 1: identify amendment candidates by title heuristic ----------
    # (much faster than classifying every document)
    _AMEND_KEYWORDS = ("wijziging", "wijzigingswet", "verbeterblad",
                       "nadere wijziging", "intrekking")
    candidates = [
        w for w in works
        if any(k in w.title.lower() for k in _AMEND_KEYWORDS)
    ]
    print(f"Title heuristic: {len(candidates)} candidates")

    # --- Pass 2: classify each candidate, collect confirmed amendments -----
    confirmed = []   # (work, full_text, ClassificationResult)
    skipped_cls = 0

    for work in candidates:
        exprs = store.get_expressions_for_work(work.id)
        if not exprs:
            skipped_cls += 1
            continue
        frags = store.get_fragments_for_expression(exprs[-1].id)
        full_text = "\n".join(f.text for f in frags if f.text)
        if not full_text.strip():
            skipped_cls += 1
            continue

        cls = classifier.classify(full_text, title=work.title)
        if cls.document_type == DocumentType.AMENDMENT and cls.confidence >= args.min_confidence:
            confirmed.append((work, full_text, cls))
        else:
            skipped_cls += 1

    print(f"Confirmed amendments: {len(confirmed)}  (skipped {skipped_cls})")
    if not confirmed:
        print("Nothing to consolidate.")
        store.close()
        return 0

    # --- Pass 3: parse + apply, sorted by effective date -------------------
    # Parse first so we can sort chronologically before applying
    parsed_items = []   # (work, parsed_amendment, effective_date)
    parse_errors = 0

    # Pre-build amendment_links lookup: work_id -> base_work_ref
    _existing_links = {
        lnk.amendment_work_id: lnk.base_work_ref
        for w in [x[0] for x in confirmed]
        for lnk in store.get_amendment_links_for_amendment(w.id)
        if lnk.base_work_ref
    }

    for work, full_text, cls in confirmed:
        try:
            parsed = parser.parse(
                full_text,
                title=work.title,
                staatsblad_ref=cls.staatsblad_ref,
                effective_date_raw=cls.effective_date_raw,
                base_work_ref=_existing_links.get(work.id, ""),
            )
            eff = (
                _parse_dutch_date(parsed.effective_date_raw)
                or _date(2000, 1, 1)   # fallback when date unknown
            )
            parsed_items.append((work, parsed, eff))
        except Exception as exc:
            parse_errors += 1
            if args.verbose:
                print(f"  PARSE ERROR {work.title[:60]}: {exc}")

    # Sort chronologically so earlier amendments are applied first
    parsed_items.sort(key=lambda t: t[2])

    print(f"Parsed {len(parsed_items)} amendments  ({parse_errors} parse errors)")
    print("Applying …")
    print()

    applied_count = skipped_count = error_count = 0
    new_expressions = 0
    fallback_links = 0

    # Pre-load all works for title-based resolution
    from lexsr.consolidation.engine import _resolve_base_work
    import hashlib as _hashlib
    from lexsr.core.models import AmendmentLink

    for i, (work, parsed, eff_date) in enumerate(parsed_items, 1):
        # --- Title-based base law resolution (used as override / fallback) ---
        base_law_candidate = _extract_base_law_from_title(work.title)
        title_resolved_work = None
        if base_law_candidate:
            candidate = _resolve_base_work(base_law_candidate, store)
            # Don't create self-referential links (amendment resolving to itself)
            if candidate and candidate.id != work.id:
                title_resolved_work = candidate

        # Check if all instructions failed to identify a target law
        real_target_refs = {
            inst.target_work_ref for inst in (parsed.instructions or [])
            if inst.target_work_ref and not inst.target_work_ref.startswith("[section")
        }
        all_unresolved = not real_target_refs and bool(parsed.instructions)

        # Determine base_work_id override
        override_id = title_resolved_work.id if (
            title_resolved_work and (all_unresolved or not parsed.instructions)
        ) else None

        if not parsed.instructions:
            # No instructions parsed at all — try to create a minimal link from title
            if title_resolved_work:
                _save_minimal_link(
                    store, work.id, title_resolved_work.id,
                    eff_date, parsed.staatsblad_ref
                )
                fallback_links += 1
                if args.verbose:
                    print(f"  [{i}] LINK {work.title[:55]} -> {title_resolved_work.title[:30]}")
            else:
                skipped_count += 1
                if args.verbose:
                    print(f"  [{i}] SKIP (no instructions): {work.title[:70]}")
            continue

        try:
            result = engine.consolidate(
                parsed_amendment=parsed,
                amendment_work_id=work.id,
                effective_date=eff_date,
                base_work_id=override_id,
                skip_review=args.skip_review,
            )

            if result.new_expression_id:
                applied_count += 1
                new_expressions += 1
                print(
                    f"  [{i}] OK  {work.title[:55]:<55} "
                    f"+{len(result.applied)} ops  eff={eff_date}"
                )
            elif result.errors:
                # Full consolidation failed — try minimal link from title
                if title_resolved_work:
                    _save_minimal_link(
                        store, work.id, title_resolved_work.id,
                        eff_date, parsed.staatsblad_ref
                    )
                    fallback_links += 1
                    if args.verbose or args.show_errors:
                        err_short = result.errors[0][:50]
                        print(f"  [{i}] LINK {work.title[:50]} -> "
                              f"{title_resolved_work.title[:25]} ({err_short})")
                else:
                    skipped_count += 1
                    if args.verbose or args.show_errors:
                        print(f"  [{i}] ERR {work.title[:60]}: {result.errors[0][:60]}")
            else:
                skipped_count += 1
                if args.verbose:
                    print(f"  [{i}] SKIP {work.title[:60]} (skipped={len(result.skipped)})")

        except Exception as exc:
            error_count += 1
            print(f"  [{i}] EXCEPTION {work.title[:55]}: {exc}")

    store.close()

    print()
    print("Consolidation complete.")
    print(f"  Amendments fully applied:    {applied_count}")
    print(f"  Amendment links created:     {fallback_links}")
    print(f"  Skipped / unresolvable:      {skipped_count}")
    print(f"  Exceptions:                  {error_count}")
    print(f"  New expressions created:     {new_expressions}")
    return 0


def _save_minimal_link(store, amendment_work_id, base_work_id, effective_date, staatsblad_ref):
    """Create an AmendmentLink without applying article-level changes."""
    import hashlib as _hashlib
    from lexsr.core.models import AmendmentLink
    existing = store.get_amendment_links_for_amendment(amendment_work_id)
    for lnk in existing:
        if lnk.base_work_id == base_work_id:
            return  # already linked
    link_id = _hashlib.sha1(
        f"{amendment_work_id}:{base_work_id}".encode()
    ).hexdigest()[:16]
    store.save_amendment_link(AmendmentLink(
        id=link_id,
        amendment_work_id=amendment_work_id,
        base_work_id=base_work_id,
        base_work_ref=base_work_id,
        effective_date=effective_date,
        staatsblad_ref=staatsblad_ref,
        confidence=0.70,
        resolved=False,  # not fully resolved (article changes not applied)
    ))


def cmd_link_citations(args: argparse.Namespace) -> int:
    """
    Backfill citation links for all existing fragments in the canonical store.

    Iterates every work -> latest expression -> fragments, runs the
    CitationExtractor, and persists the results.  Safe to re-run: the
    extractor generates stable SHA-1 citation IDs so duplicates are silently
    ignored by the ON CONFLICT clause in the store.
    """
    from lexsr.core.store import CanonicalStore
    from lexsr.ocr.citation_extractor import CitationExtractor

    if not Path(args.db).exists():
        print(f"Database not found: {args.db}")
        return 1

    store = CanonicalStore(args.db)
    extractor = CitationExtractor(store)

    works = store.list_works(limit=100_000)
    print(f"Linking citations across {len(works)} works …")

    total_citations = 0
    total_expressions = 0
    errors = 0
    report_every = max(1, len(works) // 20)  # ~5% intervals

    for i, work in enumerate(works, 1):
        expressions = store.get_expressions_for_work(work.id)
        if not expressions:
            continue

        # Process every expression so historical versions get citations too.
        for expr in expressions:
            fragments = store.get_fragments_for_expression(expr.id)
            if not fragments:
                continue
            try:
                citations = extractor.extract_from_fragments(
                    fragments,
                    source_version_date=expr.version_date,
                )
                saved = extractor.save_to_store(citations)
                total_citations += saved
                total_expressions += 1
            except Exception as exc:
                errors += 1
                if errors <= 5:
                    print(f"  ERROR {work.id}: {exc}")

        if i % report_every == 0 or i == len(works):
            pct = i / len(works) * 100
            print(f"  [{i}/{len(works)}  {pct:.0f}%]  citations so far: {total_citations:,}")

    store.close()

    print()
    print(f"Done.")
    print(f"  Expressions processed: {total_expressions:,}")
    print(f"  Citations saved:       {total_citations:,}")
    if errors:
        print(f"  Errors:                {errors}")
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lexsr",
        description="LexSR — Suriname Legal Knowledge Fabric",
    )
    parser.add_argument("--db", default=DEFAULT_DB, metavar="PATH",
                        help=f"canonical store path (default: {DEFAULT_DB})")
    parser.add_argument("--search-db", default=DEFAULT_SEARCH_DB, metavar="PATH",
                        help=f"BM25 index path (default: {DEFAULT_SEARCH_DB})")

    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # stats
    sub.add_parser("stats", help="Show database statistics")

    # ingest
    p = sub.add_parser("ingest", help="Scrape all live sources")
    p.add_argument("--raw-dir", default=DEFAULT_RAW_DIR, metavar="DIR")
    p.add_argument("--limit", type=int, default=None, metavar="N",
                   help="Limit per-scraper document count")

    # ingest-pdfs
    p = sub.add_parser("ingest-pdfs", help="Process PDFs already in data/raw/")
    p.add_argument("--raw-dir", default=DEFAULT_RAW_DIR, metavar="DIR")

    # ingest-caselaw
    p = sub.add_parser("ingest-caselaw", help="Scrape rechtspraak.sr court decisions")
    p.add_argument("--limit", type=int, default=None, metavar="N",
                   help="Limit number of decisions to process")
    p.add_argument("--rate-limit", type=float, default=2.0, metavar="SECONDS")
    p.add_argument("--force", action="store_true",
                   help="Re-process decisions already in the store")
    p.add_argument("--verbose", "-v", action="store_true")

    # consolidate
    p = sub.add_parser("consolidate", help="Run amendment consolidation pipeline")
    p.add_argument("--min-confidence", type=float, default=0.55, metavar="F",
                   help="Minimum classifier confidence to treat as amendment (default: 0.55)")
    p.add_argument("--skip-review", action="store_true",
                   help="Apply even low-confidence (<0.70) instructions without review")
    p.add_argument("--show-errors", action="store_true",
                   help="Print error details for unresolvable amendments")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--use-llm", action="store_true",
                   help="Enable the LLM fallback pass for low-confidence classification/parsing")
    p.add_argument("--llm-url", default="http://localhost:8000/v1/completions", metavar="URL",
                   help="Completions endpoint (local vLLM, or an OpenAI-compatible chat endpoint)")
    p.add_argument("--llm-model", default="Qwen/Qwen2.5-Coder-7B-Instruct", metavar="NAME")

    # link-citations
    sub.add_parser("link-citations", help="Backfill citation links for all existing fragments")

    # index
    sub.add_parser("index", help="Build / refresh the BM25 search index")

    # index-vectors
    p = sub.add_parser("index-vectors", help="Build / refresh the dense vector index")
    p.add_argument("--vector-db", default=DEFAULT_VECTOR_DB, metavar="PATH")
    p.add_argument("--model", default="intfloat/multilingual-e5-large", metavar="NAME")
    p.add_argument("--batch-size", type=int, default=64, metavar="N")

    # generate
    p = sub.add_parser("generate", help="Build the static website")
    p.add_argument("--output", default=DEFAULT_SITE_DIR, metavar="DIR")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, metavar="URL")

    # search
    p = sub.add_parser("search", help="Search the knowledge base")
    p.add_argument("query", nargs="+")
    p.add_argument("--top-k", type=int, default=10, metavar="N")
    p.add_argument("--vector-db", default=DEFAULT_VECTOR_DB, metavar="PATH")
    p.add_argument("--no-hybrid", action="store_true",
                   help="Force BM25-only search even if a vector index exists")

    # benchmark
    p = sub.add_parser("benchmark", help="Run the citation benchmark suite")
    p.add_argument("--verbose", "-v", action="store_true")

    # serve
    p = sub.add_parser("serve", help="Serve the static site locally")
    p.add_argument("--site", default=DEFAULT_SITE_DIR, metavar="DIR")
    p.add_argument("--port", type=int, default=8000, metavar="PORT")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Join multi-word search query
    if args.command == "search":
        args.query = " ".join(args.query)

    dispatch = {
        "stats":            cmd_stats,
        "ingest":           cmd_ingest,
        "ingest-pdfs":      cmd_ingest_pdfs,
        "ingest-caselaw":   cmd_ingest_caselaw,
        "consolidate":      cmd_consolidate,
        "link-citations":   cmd_link_citations,
        "index":            cmd_index,
        "index-vectors":    cmd_index_vectors,
        "generate":    cmd_generate,
        "search":      cmd_search,
        "benchmark":   cmd_benchmark,
        "serve":       cmd_serve,
    }

    fn = dispatch[args.command]
    sys.exit(fn(args) or 0)


if __name__ == "__main__":
    main()
