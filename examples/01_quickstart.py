"""
LexSR Quickstart Example

Demonstrates:
1. Creating a legal work and fragments
2. Indexing in BM25 and vector search
3. Hybrid search with RuVector
4. Generating static website
5. Adding case law and annotations
"""

from datetime import date

from lexsr.core.models import (
    Work,
    Expression,
    Fragment,
    FragmentType,
    SourceType,
    DocumentStatus,
    TemporalExtent,
)
from lexsr.core.store import CanonicalStore
from lexsr.core.identifiers import law_fragment_uri


def main():
    print("=" * 60)
    print("LexSR - Suriname Legal Knowledge Fabric")
    print("Quickstart Example")
    print("=" * 60)

    # Step 1: Create canonical store
    print("\n[1] Creating canonical store...")
    store = CanonicalStore("data/quickstart.db")

    # Step 2: Create a sample work (Arbeidswet 1963)
    print("\n[2] Creating sample legislation...")
    work = Work(
        id="arbeidswet-1963",
        uri="/id/law/arbeidswet-1963",
        source_type=SourceType.LEGISLATION,
        official_id="arbeidswet-1963",
        title="Arbeidswet 1963",
        short_title="Arbeidswet",
        document_type="wet",
        jurisdiction="SR",
        language="nl",
        status=DocumentStatus.IN_FORCE,
        date_enacted=date(1963, 1, 15),
        keywords=["arbeid", "employment", "work", "labor"],
    )
    store.save_work(work)
    print(f"   ✓ Created work: {work.title}")

    # Step 3: Create an expression (current version)
    print("\n[3] Creating expression...")
    expression = Expression(
        id="arbeidswet-1963-2024",
        uri="/id/law/arbeidswet-1963/2024-01-15",
        work_id=work.id,
        work_uri=work.uri,
        version_date=date(2024, 1, 15),
        in_force=TemporalExtent(start=date(2024, 1, 15), end=None),
        title=work.title,
        status=DocumentStatus.IN_FORCE,
    )
    store.save_expression(expression)
    print(f"   ✓ Created expression: {expression.version_date}")

    # Step 4: Create fragments (articles)
    print("\n[4] Creating fragments...")
    fragments = [
        Fragment(
            id="arbeidswet-1963-2024-art1",
            uri=law_fragment_uri("arbeidswet-1963", date(2024, 1, 15), "1"),
            expression_id=expression.id,
            expression_uri=expression.uri,
            work_id=work.id,
            fragment_type=FragmentType.ARTICLE,
            number="1",
            title="Definities",
            text=(
                "In deze wet wordt verstaan onder:\n"
                "a. werknemer: de natuurlijke persoon die in dienst staat van een werkgever;\n"
                "b. werkgever: de natuurlijke of rechtspersoon die een of meer werknemers in dienst heeft;\n"
                "c. arbeidsovereenkomst: de overeenkomst waarbij de werknemer zich verbindt "
                "arbeid te verrichten in dienst van de werkgever."
            ),
            heading_path=["Hoofdstuk I: Algemene bepalingen"],
        ),
        Fragment(
            id="arbeidswet-1963-2024-art4",
            uri=law_fragment_uri("arbeidswet-1963", date(2024, 1, 15), "4"),
            expression_id=expression.id,
            expression_uri=expression.uri,
            work_id=work.id,
            fragment_type=FragmentType.ARTICLE,
            number="4",
            title="Minimumloon",
            text=(
                "1. De werkgever is verplicht de werknemer ten minste het bij of krachtens "
                "de wet vastgestelde minimumloon te betalen.\n"
                "2. Voor landbouwarbeiders bedraagt het minimumloon ten minste 150 SRD per dag.\n"
                "3. Het minimumloon wordt jaarlijks herzien op basis van de inflatie."
            ),
            heading_path=["Hoofdstuk II: Arbeidsvoorwaarden", "Afdeling 1: Loon"],
        ),
        Fragment(
            id="arbeidswet-1963-2024-art27",
            uri=law_fragment_uri("arbeidswet-1963", date(2024, 1, 15), "27"),
            expression_id=expression.id,
            expression_uri=expression.uri,
            work_id=work.id,
            fragment_type=FragmentType.ARTICLE,
            number="27",
            title="Jaarlijks verlof",
            text=(
                "1. De werknemer heeft recht op minimaal 15 dagen betaald jaarlijks verlof.\n"
                "2. Na 10 jaar onafgebroken dienstverband wordt dit verhoogd naar 18 dagen.\n"
                "3. Het verlof moet binnen het jaar worden opgenomen, tenzij anderszins overeengekomen."
            ),
            heading_path=["Hoofdstuk II: Arbeidsvoorwaarden", "Afdeling 3: Verlof"],
        ),
    ]

    for fragment in fragments:
        store.save_fragment(fragment)
        print(f"   ✓ Created article {fragment.number}: {fragment.title}")

    # Step 5: Index in BM25 search (requires no external dependencies!)
    print("\n[5] Indexing in BM25 search...")
    try:
        from lexsr.search.bm25 import BM25Indexer

        bm25_indexer = BM25Indexer("data/quickstart_search.db")

        for fragment in fragments:
            metadata = {
                "work_title": work.title,
                "version_date": expression.version_date.isoformat(),
                "in_force_start": expression.in_force.start.isoformat()
                if expression.in_force.start
                else None,
                "in_force_end": expression.in_force.end.isoformat()
                if expression.in_force.end
                else None,
            }
            bm25_indexer.index_fragment(fragment, metadata)

        print(f"   ✓ Indexed {len(fragments)} fragments in BM25")
    except Exception as e:
        print(f"   ⚠ BM25 indexing skipped: {e}")

    # Step 6: Test BM25 search
    print("\n[6] Testing BM25 search...")
    try:
        from lexsr.search.bm25 import BM25Searcher

        searcher = BM25Searcher("data/quickstart_search.db")
        results = searcher.search("minimumloon landbouw")

        print(f"   Query: 'minimumloon landbouw'")
        for i, result in enumerate(results[:3], 1):
            print(f"   {i}. {result.uri} (score: {result.score:.3f})")
            print(f"      {result.snippet[:100]}...")
    except Exception as e:
        print(f"   ⚠ BM25 search skipped: {e}")

    # Step 7: Vector indexing (optional - requires sentence-transformers)
    print("\n[7] Vector indexing (optional)...")
    try:
        from lexsr.search.vector import VectorIndexer

        vector_indexer = VectorIndexer(storage_path="data/quickstart_vectors.db")

        fragment_metadata = [
            (fragment, {
                "work_title": work.title,
                "version_date": expression.version_date.isoformat(),
            })
            for fragment in fragments
        ]

        vector_indexer.index_fragments(fragment_metadata)
        print(f"   ✓ Indexed {len(fragments)} fragments with embeddings")
    except ImportError:
        print("   ⚠ Vector search requires: pip install sentence-transformers qdrant-client")
    except Exception as e:
        print(f"   ⚠ Vector indexing skipped: {e}")

    # Step 8: Hybrid search (RuVector!)
    print("\n[8] Testing RuVector hybrid search...")
    try:
        from lexsr.search.hybrid import HybridSearchEngine

        hybrid = HybridSearchEngine(
            bm25_db_path="data/quickstart_search.db",
            vector_db_path="data/quickstart_vectors.db",
            use_vector=False,  # Set to True if you have embeddings
        )

        results = hybrid.search("wat is het minimumloon voor landbouwarbeiders", top_k=3)

        print(f"   Query: 'wat is het minimumloon voor landbouwarbeiders'")
        for i, result in enumerate(results, 1):
            print(f"\n   {i}. {result.uri}")
            print(f"      Score: {result.score:.4f}")
            print(f"      BM25: {result.score_breakdown.get('bm25_score', 0):.4f}")
            print(f"      Vector: {result.score_breakdown.get('vector_score', 0):.4f}")

    except Exception as e:
        print(f"   ⚠ Hybrid search error: {e}")

    # Step 9: Generate static website
    print("\n[9] Generating static website...")
    try:
        from lexsr.static_gen import StaticSiteGenerator

        generator = StaticSiteGenerator(
            store=store,
            output_dir="site_quickstart",
            base_url="http://localhost:8000",
        )

        # Generate site
        generator.generate(works=[work.id], clean=True)
        print("   ✓ Static site generated at: site_quickstart/")
        print("   Run: cd site_quickstart && python -m http.server")
    except ImportError:
        print("   ⚠ Static site requires: pip install jinja2")
    except Exception as e:
        print(f"   ⚠ Site generation skipped: {e}")

    # Step 10: Citation resolution
    print("\n[10] Testing citation resolution...")
    try:
        from lexsr.core.resolver import CitationResolver

        resolver = CitationResolver(store=store)
        text = (
            "Volgens artikel 4 lid 2 van de Arbeidswet 1963 bedraagt het minimumloon "
            "voor landbouwarbeiders ten minste 150 SRD per dag."
        )

        refs = resolver.resolve_text(text)
        print(f"   Text: '{text[:80]}...'")
        for ref in refs:
            if ref.status.value == "resolved":
                print(f"   ✓ {ref.raw_text} → {ref.uri} (confidence: {ref.confidence:.2f})")
    except Exception as e:
        print(f"   ⚠ Citation resolution error: {e}")

    print("\n" + "=" * 60)
    print("✓ Quickstart complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. View the static site: cd site_quickstart && python -m http.server")
    print("  2. Install vector search: pip install sentence-transformers qdrant-client")
    print("  3. Add more legislation and build the full database")
    print("  4. Explore examples/02_advanced.py for more features")
    print()


if __name__ == "__main__":
    main()
