"""
Process Existing PDFs with Tesseract

Processes all PDFs in data/raw/ with Tesseract OCR
Skips PDFs already in database (by content hash)
"""

import sys
import os
from pathlib import Path
import hashlib
from datetime import date

# Add Tesseract to PATH
os.environ['PATH'] = os.environ.get('PATH', '') + ';C:\\Program Files\\Tesseract-OCR'

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lexsr.core.store import CanonicalStore
from lexsr.core.models import Work, Expression
from lexsr.ocr.pipeline import OCRPipeline, PipelineConfig
from lexsr.ocr.extractor import OCREngine
import pytesseract
import sqlite3
import re

# Configure Tesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


def pdf_hash(pdf_path):
    """Calculate SHA-256 hash of PDF content."""
    hasher = hashlib.sha256()
    with open(pdf_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def is_already_processed(pdf_path):
    """Check if PDF is already in database by content hash."""
    file_hash = pdf_hash(pdf_path)

    conn = sqlite3.connect("data/canonical.db")
    cursor = conn.execute(
        "SELECT COUNT(*) FROM expressions WHERE checksum = ?",
        (file_hash,)
    )
    count = cursor.fetchone()[0]
    conn.close()

    return count > 0


def clean_title_from_filename(filename):
    """Extract clean title from PDF filename."""
    name = Path(filename).stem

    # Remove common patterns
    name = re.sub(r'^\d+[\._]', '', name)  # Remove leading numbers
    name = name.replace('_', ' ')
    name = name.replace('-', ' ')
    name = re.sub(r'\s+', ' ', name).strip()

    # Limit length
    if len(name) > 100:
        name = name[:100].strip()

    return name if name else filename


def generate_work_id(title):
    """Generate unique work ID from title."""
    # Clean for ID
    work_id = title.lower()
    work_id = re.sub(r'[^a-z0-9\s-]', '', work_id)
    work_id = re.sub(r'\s+', '-', work_id)
    work_id = work_id[:80]  # Limit length

    # Add hash suffix for uniqueness
    suffix = hashlib.md5(title.encode()).hexdigest()[:8]

    return f"{work_id}-{suffix}"


def process_pdf(pdf_path, ocr_pipeline, store):
    """Process a single PDF with Tesseract."""
    try:
        # Generate title and IDs
        title = clean_title_from_filename(pdf_path.name)
        work_id = generate_work_id(title)

        # Process PDF with Tesseract
        result = ocr_pipeline.process_pdf(
            str(pdf_path),
            work_id=work_id,
            title=title,
            version_date=date.today()
        )

        if not result.fragments:
            return False, "No content extracted"

        # Create work
        work = Work(
            id=work_id,
            title=title,
            document_type="legislation",
            jurisdiction="SR",
            language="nl",
            status="in_force",
        )

        # Create expression
        expr_id = f"{work_id}-v1"
        file_hash = pdf_hash(pdf_path)

        expression = Expression(
            id=expr_id,
            work_id=work_id,
            title=title,
            language="nl",
            status="in_force",
            checksum=file_hash,
        )

        # Store everything
        store.save_work(work)
        store.save_expression(expression)

        for frag in result.fragments:
            frag.expression_id = expr_id
            store.save_fragment(frag)

        return True, f"OK - {len(result.fragments)} fragments"

    except Exception as e:
        return False, str(e)[:100]


def main():
    print("=" * 80)
    print("PROCESS EXISTING PDFs WITH TESSERACT")
    print("=" * 80)
    print()

    # Setup
    raw_dir = Path("data/raw")
    store = CanonicalStore("data/canonical.db")

    # Configure Tesseract
    ocr_config = PipelineConfig(
        ocr_engine=OCREngine.TESSERACT,
        tesseract_lang='eng',
    )
    ocr_pipeline = OCRPipeline(ocr_config)

    # Find all PDFs
    all_pdfs = sorted(raw_dir.rglob("*.pdf"))
    print(f"Found: {len(all_pdfs)} PDFs in {raw_dir}/")
    print()

    # Check initial database
    conn = sqlite3.connect("data/canonical.db")
    initial_works = conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    initial_frags = conn.execute("SELECT COUNT(*) FROM fragments").fetchone()[0]
    conn.close()

    print(f"Initial database: {initial_works} works, {initial_frags:,} fragments")
    print()
    print("=" * 80)
    print("PROCESSING...")
    print("=" * 80)

    # Process each PDF
    processed = 0
    skipped = 0
    failed = 0
    errors = []

    for i, pdf_path in enumerate(all_pdfs, 1):
        # Progress indicator
        if i % 10 == 1:
            print(f"\n[{i}/{len(all_pdfs)}] Processing...")

        # Skip if already in database
        if is_already_processed(pdf_path):
            skipped += 1
            if i <= 10:  # Show details for first 10
                print(f"  [-] Skip: {pdf_path.name[:60]} (exists)")
            continue

        # Process with Tesseract
        success, message = process_pdf(pdf_path, ocr_pipeline, store)

        if success:
            processed += 1
            if processed <= 10:  # Show details for first 10 new
                print(f"  [+] New:  {pdf_path.name[:60]}")
                print(f"      {message}")
        else:
            failed += 1
            error_msg = f"{pdf_path.name}: {message}"
            errors.append(error_msg)
            if failed <= 5:  # Show first 5 errors
                print(f"  [X] Fail: {pdf_path.name[:60]}")
                print(f"      {message[:70]}")

        # Progress update every 50
        if i % 50 == 0:
            conn = sqlite3.connect("data/canonical.db")
            current_works = conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]
            current_frags = conn.execute("SELECT COUNT(*) FROM fragments").fetchone()[0]
            conn.close()

            added = current_works - initial_works
            print(f"\n  >> Progress: {current_works} works (+{added}), {current_frags:,} fragments")
            print(f"  >> Processed: {processed}, Skipped: {skipped}, Failed: {failed}\n")

    # Final stats
    conn = sqlite3.connect("data/canonical.db")
    final_works = conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    final_frags = conn.execute("SELECT COUNT(*) FROM fragments").fetchone()[0]
    conn.close()

    print("\n" + "=" * 80)
    print("FINAL RESULTS")
    print("=" * 80)
    print(f"PDFs found:      {len(all_pdfs):4d}")
    print(f"New processed:   {processed:4d}")
    print(f"Already existed: {skipped:4d}")
    print(f"Failed:          {failed:4d}")
    print()
    print(f"Database:")
    print(f"  Initial: {initial_works:4d} works, {initial_frags:6,d} fragments")
    print(f"  Final:   {final_works:4d} works, {final_frags:6,d} fragments")
    print(f"  Added:   {final_works - initial_works:4d} works, {final_frags - initial_frags:6,d} fragments")
    print()

    if errors:
        print(f"Errors ({len(errors)} total, showing first 10):")
        for error in errors[:10]:
            print(f"  - {error[:75]}")

    print("=" * 80)
    print("COMPLETE!")
    print("All PDFs processed with Tesseract OCR")
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        print("Progress has been saved.")
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
