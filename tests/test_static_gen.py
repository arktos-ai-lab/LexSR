"""
Tests for the static site generator.

Covers:
- _get_all_work_ids()  -- was returning [] (fixed)
- _generate_search_data() -- was empty (fixed)
- _get_amendment_metadata() -- was querying non-existent tables (fixed)
- Full generate() smoke test

Run with: python -m pytest tests/test_static_gen.py -v
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from lexsr.core.models import (
    AmendmentLink,
    DocumentStatus,
    Expression,
    Fragment,
    FragmentType,
    SourceType,
    TemporalExtent,
    Work,
)
from lexsr.core.store import CanonicalStore
from lexsr.static_gen.generator import StaticSiteGenerator


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def store(tmp_path):
    s = CanonicalStore(str(tmp_path / "canonical.db"))
    yield s
    s.close()


@pytest.fixture
def populated_store(store):
    """Store with two works (a base law and an amendment), one expression each."""
    base = Work(
        id="w-arbeidswet",
        uri="/id/law/arbeidswet-1963",
        official_id="arbeidswet-1963",
        title="Arbeidswet 1963",
        source_type=SourceType.LEGISLATION,
        document_type="base_law",
    )
    amend = Work(
        id="w-wijziging-aw",
        uri="/id/law/wijziging-aw-1975",
        official_id="wijziging-aw-1975",
        title="Wijzigingswet Arbeidswet 1975",
        source_type=SourceType.LEGISLATION,
        document_type="amendment",
    )
    store.save_work(base)
    store.save_work(amend)

    v0 = date(1963, 1, 1)
    expr = Expression(
        id="e-aw-v0",
        uri="/id/law/arbeidswet-1963/1963-01-01",
        work_id=base.id,
        work_uri=base.uri,
        version_date=v0,
        in_force=TemporalExtent(start=v0),
        title="Arbeidswet 1963",
        language="nl",
        status=DocumentStatus.IN_FORCE,
    )
    store.save_expression(expr)

    for i, (nr, text) in enumerate([
        ("1", "Begripsbepalingen."),
        ("7", "De werkgever betaalt het loon."),
        ("10", "Vakantie."),
    ]):
        store.save_fragment(Fragment(
            id=f"f-aw-{nr}",
            uri=f"/id/law/arbeidswet-1963/1963-01-01/article/{nr}",
            expression_id=expr.id,
            expression_uri=expr.uri,
            work_id=base.id,
            fragment_type=FragmentType.ARTICLE,
            number=nr,
            title=f"Artikel {nr}",
            position=i,
            depth=0,
            text=text,
        ))

    # Amendment link: wijziging → base
    store.save_amendment_link(AmendmentLink(
        id="al-1",
        amendment_work_id=amend.id,
        base_work_id=base.id,
        base_work_ref="Arbeidswet 1963",
        effective_date=date(1976, 1, 1),
        staatsblad_ref="S.B. 1975 no. 100",
        confidence=1.0,
        resolved=True,
    ))

    return store


@pytest.fixture
def generator(populated_store, tmp_path):
    output = str(tmp_path / "site")
    return StaticSiteGenerator(
        store=populated_store,
        output_dir=output,
        base_url="https://wetten.test",
    )


# ===================================================================
# _get_all_work_ids
# ===================================================================

class TestGetAllWorkIds:
    def test_returns_all_works(self, populated_store, tmp_path):
        gen = StaticSiteGenerator(
            store=populated_store,
            output_dir=str(tmp_path / "site"),
            base_url="https://wetten.test",
        )
        ids = gen._get_all_work_ids()
        assert "w-arbeidswet" in ids
        assert "w-wijziging-aw" in ids
        assert len(ids) == 2

    def test_returns_empty_for_empty_store(self, store, tmp_path):
        gen = StaticSiteGenerator(
            store=store,
            output_dir=str(tmp_path / "site"),
            base_url="https://wetten.test",
        )
        assert gen._get_all_work_ids() == []


# ===================================================================
# _generate_search_data
# ===================================================================

class TestGenerateSearchData:
    def test_search_index_has_documents(self, generator, tmp_path):
        # Must create directories first
        generator._create_directories()
        generator._generate_search_data()

        index_path = Path(str(tmp_path / "site")) / "data" / "search-index.json"
        assert index_path.exists()

        data = json.loads(index_path.read_text(encoding="utf-8"))
        assert "documents" in data
        assert "generated" in data
        assert len(data["documents"]) == 3  # 3 fragments in populated_store

    def test_search_index_document_shape(self, generator, tmp_path):
        generator._create_directories()
        generator._generate_search_data()

        index_path = Path(str(tmp_path / "site")) / "data" / "search-index.json"
        data = json.loads(index_path.read_text(encoding="utf-8"))
        doc = data["documents"][0]

        assert "id" in doc
        assert "work_id" in doc
        assert "work_title" in doc
        assert "article" in doc
        assert "text" in doc
        assert "url" in doc

    def test_repealed_fragments_excluded(self, store, tmp_path):
        """Fragments with text '[Vervallen]' should not appear in the search index."""
        work = Work(
            id="w-test",
            uri="/id/law/test",
            official_id="test",
            title="Test Wet",
            source_type=SourceType.LEGISLATION,
        )
        store.save_work(work)
        v0 = date(2020, 1, 1)
        expr = Expression(
            id="e-test",
            uri="/id/law/test/2020-01-01",
            work_id=work.id,
            work_uri=work.uri,
            version_date=v0,
            in_force=TemporalExtent(start=v0),
            title="Test Wet",
            language="nl",
            status=DocumentStatus.IN_FORCE,
        )
        store.save_expression(expr)
        store.save_fragment(Fragment(
            id="f-test-1",
            uri="/id/law/test/2020-01-01/article/1",
            expression_id=expr.id,
            expression_uri=expr.uri,
            work_id=work.id,
            fragment_type=FragmentType.ARTICLE,
            number="1",
            position=0,
            depth=0,
            text="[Vervallen]",
        ))
        store.save_fragment(Fragment(
            id="f-test-2",
            uri="/id/law/test/2020-01-01/article/2",
            expression_id=expr.id,
            expression_uri=expr.uri,
            work_id=work.id,
            fragment_type=FragmentType.ARTICLE,
            number="2",
            position=1,
            depth=0,
            text="Dit artikel heeft inhoud.",
        ))

        gen = StaticSiteGenerator(store=store, output_dir=str(tmp_path / "site2"), base_url="https://t")
        gen._create_directories()
        gen._generate_search_data()

        index_path = Path(str(tmp_path / "site2")) / "data" / "search-index.json"
        data = json.loads(index_path.read_text(encoding="utf-8"))
        texts = [d["text"] for d in data["documents"]]
        assert "[Vervallen]" not in texts
        assert any("inhoud" in t for t in texts)

    def test_search_index_text_capped_at_500_chars(self, store, tmp_path):
        work = Work(
            id="w-long",
            uri="/id/law/long",
            official_id="long",
            title="Lange Wet",
            source_type=SourceType.LEGISLATION,
        )
        store.save_work(work)
        v0 = date(2020, 1, 1)
        expr = Expression(
            id="e-long",
            uri="/id/law/long/2020-01-01",
            work_id=work.id,
            work_uri=work.uri,
            version_date=v0,
            in_force=TemporalExtent(start=v0),
            title="Lange Wet",
            language="nl",
            status=DocumentStatus.IN_FORCE,
        )
        store.save_expression(expr)
        store.save_fragment(Fragment(
            id="f-long-1",
            uri="/id/law/long/2020-01-01/article/1",
            expression_id=expr.id,
            expression_uri=expr.uri,
            work_id=work.id,
            fragment_type=FragmentType.ARTICLE,
            number="1",
            position=0,
            depth=0,
            text="x" * 1000,
        ))

        gen = StaticSiteGenerator(store=store, output_dir=str(tmp_path / "site3"), base_url="https://t")
        gen._create_directories()
        gen._generate_search_data()

        index_path = Path(str(tmp_path / "site3")) / "data" / "search-index.json"
        data = json.loads(index_path.read_text(encoding="utf-8"))
        assert len(data["documents"][0]["text"]) <= 500


# ===================================================================
# _get_amendment_metadata
# ===================================================================

class TestGetAmendmentMetadata:
    def test_base_law_has_amendments_to_this(self, generator):
        meta = generator._get_amendment_metadata("w-arbeidswet")
        assert len(meta["amendments_to_this"]) == 1
        assert meta["amendments_to_this"][0]["id"] == "w-wijziging-aw"

    def test_amendment_has_this_amends(self, generator):
        meta = generator._get_amendment_metadata("w-wijziging-aw")
        assert len(meta["this_amends"]) == 1
        assert meta["this_amends"][0]["id"] == "w-arbeidswet"

    def test_document_type_populated(self, generator):
        meta = generator._get_amendment_metadata("w-arbeidswet")
        assert meta["document_type"] == "base_law"

    def test_no_links_returns_empty_lists(self, store, tmp_path):
        isolated = Work(
            id="w-isolated",
            uri="/id/law/isolated",
            official_id="isolated",
            title="Isolated Wet",
            source_type=SourceType.LEGISLATION,
        )
        store.save_work(isolated)
        gen = StaticSiteGenerator(store=store, output_dir=str(tmp_path / "site4"), base_url="https://t")
        meta = gen._get_amendment_metadata("w-isolated")
        assert meta["amendments_to_this"] == []
        assert meta["this_amends"] == []


# ===================================================================
# Full generate() smoke test
# ===================================================================

class TestFullGenerate:
    def test_generate_creates_index_html(self, generator, tmp_path):
        generator.generate()
        assert (Path(str(tmp_path / "site")) / "index.html").exists()

    def test_generate_creates_works_index(self, generator, tmp_path):
        generator.generate()
        assert (Path(str(tmp_path / "site")) / "works" / "index.html").exists()

    def test_generate_creates_work_pages(self, generator, tmp_path):
        generator.generate()
        work_page = Path(str(tmp_path / "site")) / "works" / "w-arbeidswet" / "index.html"
        assert work_page.exists()

    def test_generate_creates_search_page(self, generator, tmp_path):
        generator.generate()
        assert (Path(str(tmp_path / "site")) / "search" / "index.html").exists()

    def test_generate_creates_search_index(self, generator, tmp_path):
        generator.generate()
        index_path = Path(str(tmp_path / "site")) / "data" / "search-index.json"
        assert index_path.exists()
        data = json.loads(index_path.read_text(encoding="utf-8"))
        assert len(data["documents"]) > 0

    def test_generate_creates_assets(self, generator, tmp_path):
        generator.generate()
        site = Path(str(tmp_path / "site"))
        assert (site / "assets" / "css" / "style.css").exists()
        assert (site / "assets" / "js" / "search.js").exists()

    def test_generate_subset_of_works(self, generator, tmp_path):
        """Passing a specific work list generates only those pages."""
        generator.generate(works=["w-arbeidswet"])
        work_page = Path(str(tmp_path / "site")) / "works" / "w-arbeidswet" / "index.html"
        assert work_page.exists()
        # The amendment work page should not have been generated
        amend_page = Path(str(tmp_path / "site")) / "works" / "w-wijziging-aw" / "index.html"
        assert not amend_page.exists()
