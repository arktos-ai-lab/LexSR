"""
One-off: re-run classify+parse with the LLM fallback enabled (OpenRouter)
against just the amendments that remain unresolved (linked-only) after the
regex-only consolidation pass, instead of re-scanning every candidate.

Safe to re-run: ConsolidationEngine generates stable IDs and uses ON CONFLICT.
"""

import sys
from datetime import date

from lexsr.core.store import CanonicalStore
from lexsr.consolidation import DocumentClassifier, DocumentType, AmendmentParser, ConsolidationEngine
from lexsr.__main__ import _parse_dutch_date, _extract_base_law_from_title, _save_minimal_link
from lexsr.consolidation.engine import _resolve_base_work

DB = "data/canonical.db"
LLM_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "stealth/ox-alpha"


def main():
    store = CanonicalStore(DB)
    classifier = DocumentClassifier(use_llm=True, llm_url=LLM_URL, model=MODEL)
    parser = AmendmentParser(use_llm=True, llm_url=LLM_URL, model=MODEL)
    engine = ConsolidationEngine(store)

    rows = store._conn.execute(
        "SELECT DISTINCT amendment_work_id FROM amendment_links WHERE resolved = 0"
    ).fetchall()
    work_ids = [r[0] for r in rows]
    print(f"{len(work_ids)} unresolved amendments to retry with LLM assistance")

    applied = skipped = errors = 0

    for i, work_id in enumerate(work_ids, 1):
        work = store.get_work(work_id)
        if not work:
            continue
        exprs = store.get_expressions_for_work(work_id)
        if not exprs:
            continue
        frags = store.get_fragments_for_expression(exprs[-1].id)
        full_text = "\n".join(f.text for f in frags if f.text)
        if not full_text.strip():
            skipped += 1
            continue

        print(f"[{i}/{len(work_ids)}] {work.title[:70]}")

        try:
            cls = classifier.classify(full_text, title=work.title)
            if cls.document_type != DocumentType.AMENDMENT:
                print(f"    reclassified as {cls.document_type.value}, skipping")
                skipped += 1
                continue

            existing_links = store.get_amendment_links_for_amendment(work_id)
            base_work_ref = existing_links[0].base_work_ref if existing_links else ""

            parsed = parser.parse(
                full_text,
                title=work.title,
                staatsblad_ref=cls.staatsblad_ref,
                effective_date_raw=cls.effective_date_raw,
                base_work_ref=base_work_ref,
            )

            if not parsed.instructions:
                print("    LLM found no instructions either, leaving as-is")
                skipped += 1
                continue

            eff = _parse_dutch_date(parsed.effective_date_raw) or date(2000, 1, 1)

            base_law_candidate = _extract_base_law_from_title(work.title)
            title_resolved = _resolve_base_work(base_law_candidate, store) if base_law_candidate else None
            override_id = title_resolved.id if (title_resolved and title_resolved.id != work_id) else None

            result = engine.consolidate(
                parsed_amendment=parsed,
                amendment_work_id=work_id,
                effective_date=eff,
                base_work_id=override_id,
            )

            if result.new_expression_id:
                applied += 1
                print(f"    OK +{len(result.applied)} ops")
            else:
                skipped += 1
                if result.errors:
                    print(f"    still unresolved: {result.errors[0][:80]}")

        except Exception as exc:
            errors += 1
            print(f"    EXCEPTION: {exc}")

    store.close()
    print(f"\nDone. applied={applied} skipped={skipped} errors={errors}")


if __name__ == "__main__":
    sys.exit(main() or 0)
