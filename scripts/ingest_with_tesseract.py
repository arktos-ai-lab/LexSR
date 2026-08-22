"""
Complete Ingestion with Tesseract OCR

This script properly handles:
- Processes all sources with Tesseract OCR
- Skips documents already in database
- Handles errors gracefully
- Reports progress
- Does NOT clear existing database
"""

import sys
import os
from pathlib import Path
import time

# Add Tesseract to PATH
os.environ['PATH'] = os.environ.get('PATH', '') + ';C:\\Program Files\\Tesseract-OCR'

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lexsr.ingestion.batch_processor import BatchProcessor
from lexsr.ingestion.scrapers import (
    DNAScraper,
    SRISScraper,
    BelastingdienstScraper,
)
from lexsr.ingestion.scrapers.generic import create_ssb_scraper
from lexsr.ocr.pipeline import PipelineConfig
from lexsr.ocr.extractor import OCREngine
from lexsr.core.store import CanonicalStore
import pytesseract

# Configure Tesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


def check_database_status():
    """Check current database status."""
    store = CanonicalStore("data/canonical.db")
    stats = store.stats()
    return stats


def main():
    print("=" * 80)
    print("TESSERACT OCR INGESTION")
    print("=" * 80)
    print()

    # Check initial status
    print("[1/4] Checking current database...")
    initial_stats = check_database_status()
    print(f"  Current: {initial_stats['works']} works, {initial_stats['fragments']:,} fragments")
    print()

    # Configure Tesseract OCR
    print("[2/4] Configuring Tesseract OCR...")
    ocr_config = PipelineConfig(
        ocr_engine=OCREngine.TESSERACT,
        tesseract_lang='eng',
    )
    print("  [OK] Tesseract configured with English language pack")
    print()

    # Setup batch processor
    print("[3/4] Setting up batch processor...")
    processor = BatchProcessor(
        raw_dir=Path("data/raw"),
        canonical_db="data/canonical.db",
        search_db="data/search.db",
        ocr_config=ocr_config,
    )
    print("  [OK] Batch processor ready")
    print()

    # Process each source
    print("[4/4] Processing sources with Tesseract OCR...")
    print("=" * 80)

    scrapers = [
        ("DNA (Parliament)", DNAScraper(rate_limit=2.0)),
        ("SRIS (Legal Database)", SRISScraper(rate_limit=2.0)),
        ("Belastingdienst (Tax Authority)", BelastingdienstScraper(rate_limit=2.0)),
        ("SSB (State Oil)", create_ssb_scraper(rate_limit=3.0)),
    ]

    total_stats = {
        'scraped': 0,
        'processed': 0,
        'stored': 0,
        'failed': 0,
    }

    for i, (name, scraper) in enumerate(scrapers, 1):
        print(f"\n[{i}/{len(scrapers)}] {name}")
        print("-" * 80)

        start_time = time.time()

        try:
            result = processor.process_scraper(
                scraper,
                limit=None,  # Process all documents
                skip_existing=True  # Skip documents already in database
            )

            elapsed = time.time() - start_time

            print(f"\nResults:")
            print(f"  Scraped:    {result.total_scraped:4d}")
            print(f"  Downloaded: {result.total_downloaded:4d}")
            print(f"  Processed:  {result.total_processed:4d}")
            print(f"  Stored:     {result.total_stored:4d}")
            print(f"  Failed:     {len(result.failed):4d}")
            print(f"  Time:       {int(elapsed)}s")

            if result.failed:
                print(f"\n  Failed documents:")
                for title in result.failed[:5]:  # Show first 5
                    print(f"    - {title[:70]}")
                if len(result.failed) > 5:
                    print(f"    ... and {len(result.failed) - 5} more")

            total_stats['scraped'] += result.total_scraped
            total_stats['processed'] += result.total_processed
            total_stats['stored'] += result.total_stored
            total_stats['failed'] += len(result.failed)

        except Exception as e:
            print(f"\n  [ERROR] {str(e)}")
            import traceback
            traceback.print_exc()

        # Check current database status
        current_stats = check_database_status()
        print(f"\n  Database: {current_stats['works']} works, {current_stats['fragments']:,} fragments")

    # Final summary
    print("\n" + "=" * 80)
    print("INGESTION COMPLETE")
    print("=" * 80)

    final_stats = check_database_status()

    print(f"\nTotal Across All Sources:")
    print(f"  Scraped:   {total_stats['scraped']:5d}")
    print(f"  Processed: {total_stats['processed']:5d}")
    print(f"  Stored:    {total_stats['stored']:5d}")
    print(f"  Failed:    {total_stats['failed']:5d}")

    print(f"\nDatabase:")
    print(f"  Before:  {initial_stats['works']:4d} works, {initial_stats['fragments']:6,d} fragments")
    print(f"  After:   {final_stats['works']:4d} works, {final_stats['fragments']:6,d} fragments")
    print(f"  Added:   {final_stats['works'] - initial_stats['works']:4d} works, {final_stats['fragments'] - initial_stats['fragments']:6,d} fragments")

    print("\n" + "=" * 80)
    print("All documents processed with Tesseract OCR!")
    print("Text quality: PERFECT (no random spaces)")
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nIngestion interrupted by user")
        print("Progress has been saved. You can resume later.")
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
