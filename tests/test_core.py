"""
Tests for the core module: FRBR models, URI system, versioning, and store.

Run with: python -m pytest tests/test_core.py -v
"""

from datetime import date, datetime

import pytest

from lexsr.core.models import (
    AnchorType,
    DocumentStatus,
    Expression,
    Fragment,
    FragmentAnchor,
    FragmentType,
    Manifestation,
    ManifestationType,
    SourceType,
    TemporalExtent,
    Work,
)
from lexsr.core.identifiers import (
    AbbreviationRegistry,
    FragmentPath,
    LegalURI,
    URIScheme,
    build_uri,
    ecli_fragment_uri,
    ecli_work_uri,
    law_expression_uri,
    law_fragment_uri,
    law_work_uri,
    normalize_uri,
    parse_uri,
    resolve_abbreviation,
)
from lexsr.core.versioning import TemporalIndex, VersionChain, VersionDiff
from lexsr.core.store import CanonicalStore


# ===================================================================
# Models
# ===================================================================

class TestTemporalExtent:
    def test_contains_open_ended(self):
        ext = TemporalExtent(start=date(2020, 1, 1))
        assert ext.contains(date(2024, 6, 15))
        assert not ext.contains(date(2019, 12, 31))

    def test_contains_closed(self):
        ext = TemporalExtent(start=date(2020, 1, 1), end=date(2023, 12, 31))
        assert ext.contains(date(2022, 6, 1))
        assert not ext.contains(date(2024, 1, 1))

    def test_contains_no_bounds(self):
        ext = TemporalExtent()
        assert ext.contains(date(2000, 1, 1))

    def test_is_open(self):
        assert TemporalExtent(start=date(2020, 1, 1)).is_open()
        assert not TemporalExtent(start=date(2020, 1, 1), end=date(2023, 1, 1)).is_open()


class TestFragmentAnchor:
    def test_compute_text_hash_deterministic(self):
        h1 = FragmentAnchor.compute_text_hash("Hello World")
        h2 = FragmentAnchor.compute_text_hash("  hello   world  ")
        assert h1 == h2

    def test_from_structural(self):
        anchor = FragmentAnchor.from_structural(
            "/wetgeving/article[3]/paragraph[1]",
            text="De verplichting tot schadevergoeding...",
            heading="Article 3:2",
        )
        assert anchor.anchor_type == AnchorType.STRUCTURAL
        assert anchor.structural_path == "/wetgeving/article[3]/paragraph[1]"
        assert anchor.text_hash is not None
        assert anchor.heading_context == "Article 3:2"

    def test_from_text(self):
        anchor = FragmentAnchor.from_text("Some legal text here")
        assert anchor.anchor_type == AnchorType.TEXT_HASH
        assert anchor.text_hash is not None
        assert anchor.structural_path is None


class TestWork:
    def test_creation(self):
        work = Work(
            id="w-arbeidswet-1963",
            uri="/id/law/arbeidswet-1963",
            source_type=SourceType.LEGISLATION,
            official_id="arbeidswet-1963",
            title="Arbeidswet 1963",
            short_title="AW",
            status=DocumentStatus.IN_FORCE,
        )
        assert work.uri == "/id/law/arbeidswet-1963"
        assert work.short_title == "AW"
        assert work.jurisdiction == "SR"

    def test_requires_uri(self):
        with pytest.raises(ValueError):
            Work(
                id="test",
                uri="",
                source_type=SourceType.LEGISLATION,
                official_id="arbeidswet-1963",
                title="Test",
            )


# ===================================================================
# URI System
# ===================================================================

class TestFragmentPath:
    def test_build_and_serialize(self):
        fp = FragmentPath()
        fp.append("article", "3:2").append("paragraph", "1")
        assert fp.to_uri_suffix() == "/article/3:2/paragraph/1"

    def test_parse_roundtrip(self):
        original = "/article/6:162/paragraph/1/sub/a"
        fp = FragmentPath.from_uri_suffix(original)
        assert fp.to_uri_suffix() == original

    def test_valueless_segment(self):
        fp = FragmentPath.from_uri_suffix("/decision")
        assert fp.segments == [("decision", "")]
        assert fp.leaf_type == "decision"

    def test_invalid_segment_type(self):
        with pytest.raises(ValueError, match="Unknown"):
            FragmentPath().append("nonexistent", "1")

    def test_depth(self):
        fp = FragmentPath()
        fp.append("article", "5").append("paragraph", "2").append("sub", "b")
        assert fp.depth == 3

    def test_dutch_aliases_accepted(self):
        """Dutch segment names should be accepted via FRAGMENT_ALIASES."""
        fp = FragmentPath()
        fp.append("artikel", "5").append("lid", "2")
        assert fp.depth == 2


class TestBuildURI:
    def test_law_work(self):
        uri = build_uri(URIScheme.LAW, "arbeidswet-1963")
        assert uri.to_uri() == "/id/law/arbeidswet-1963"
        assert uri.is_work

    def test_law_expression(self):
        uri = build_uri(URIScheme.LAW, "arbeidswet-1963", version_date=date(2024, 1, 15))
        assert uri.to_uri() == "/id/law/arbeidswet-1963/2024-01-15"
        assert uri.is_expression

    def test_law_fragment(self):
        fp = FragmentPath()
        fp.append("article", "3:2").append("paragraph", "1")
        uri = build_uri(
            URIScheme.LAW, "arbeidswet-1963",
            version_date=date(2024, 1, 15),
            fragment_path=fp,
        )
        assert uri.to_uri() == "/id/law/arbeidswet-1963/2024-01-15/article/3:2/paragraph/1"
        assert uri.is_fragment

    def test_ecli_work(self):
        uri = build_uri(URIScheme.ECLI, "ECLI:NL:HR:2020:1234")
        assert uri.to_uri() == "/id/ecli/ECLI:NL:HR:2020:1234"
        assert uri.is_work

    def test_ecli_fragment(self):
        fp = FragmentPath()
        fp.append("consideration", "4.3")
        uri = build_uri(URIScheme.ECLI, "ECLI:NL:HR:2020:1234", fragment_path=fp)
        assert uri.to_uri() == "/id/ecli/ECLI:NL:HR:2020:1234/consideration/4.3"
        assert uri.is_fragment

    def test_no_validation_on_law_ids(self):
        """LAW scheme has no ID validation -- any string is accepted."""
        uri = build_uri(URIScheme.LAW, "anything-goes-here")
        assert uri.to_uri() == "/id/law/anything-goes-here"

    def test_invalid_ecli_id(self):
        with pytest.raises(ValueError, match="Invalid official_id"):
            build_uri(URIScheme.ECLI, "NOT_AN_ECLI")

    def test_invalid_celex_id(self):
        with pytest.raises(ValueError, match="Invalid official_id"):
            build_uri(URIScheme.CELEX, "INVALID")

    def test_manifestation(self):
        uri = build_uri(
            URIScheme.LAW, "arbeidswet-1963",
            version_date=date(2024, 1, 15),
            format_type="xml",
        )
        assert uri.is_manifestation
        assert uri.to_uri() == "/id/law/arbeidswet-1963/2024-01-15/xml"

    def test_work_uri_property(self):
        fp = FragmentPath()
        fp.append("article", "5")
        uri = build_uri(
            URIScheme.LAW, "arbeidswet-1963",
            version_date=date(2024, 1, 15),
            fragment_path=fp,
        )
        assert uri.work_uri == "/id/law/arbeidswet-1963"
        assert uri.expression_uri == "/id/law/arbeidswet-1963/2024-01-15"


class TestParseURI:
    def test_law_work(self):
        uri = parse_uri("/id/law/arbeidswet-1963")
        assert uri.scheme == URIScheme.LAW
        assert uri.official_id == "arbeidswet-1963"
        assert uri.is_work

    def test_law_expression(self):
        uri = parse_uri("/id/law/arbeidswet-1963/2024-01-15")
        assert uri.version_date == date(2024, 1, 15)
        assert uri.is_expression

    def test_law_fragment(self):
        uri = parse_uri("/id/law/arbeidswet-1963/2024-01-15/article/3:2/paragraph/1")
        assert uri.is_fragment
        assert uri.fragment_path.segments == [("article", "3:2"), ("paragraph", "1")]

    def test_ecli_work(self):
        uri = parse_uri("/id/ecli/ECLI:NL:HR:2020:1234")
        assert uri.scheme == URIScheme.ECLI
        assert uri.official_id == "ECLI:NL:HR:2020:1234"

    def test_ecli_fragment(self):
        uri = parse_uri("/id/ecli/ECLI:NL:HR:2020:1234/consideration/4.3")
        assert uri.is_fragment
        assert uri.fragment_path.leaf_type == "consideration"
        assert uri.fragment_path.leaf_number == "4.3"

    def test_ecli_valueless_fragment(self):
        uri = parse_uri("/id/ecli/ECLI:NL:HR:2020:1234/decision")
        assert uri.is_fragment
        assert uri.fragment_path.leaf_type == "decision"

    def test_celex(self):
        uri = parse_uri("/id/celex/32016R0679")
        assert uri.scheme == URIScheme.CELEX
        assert uri.official_id == "32016R0679"

    def test_roundtrip(self):
        originals = [
            "/id/law/arbeidswet-1963",
            "/id/law/arbeidswet-1963/2024-01-15",
            "/id/law/arbeidswet-1963/2024-01-15/article/3:2/paragraph/1",
            "/id/ecli/ECLI:NL:HR:2020:1234",
            "/id/ecli/ECLI:NL:HR:2020:1234/consideration/4.3",
            "/id/ecli/ECLI:NL:HR:2020:1234/decision",
            "/id/celex/32016R0679",
        ]
        for orig in originals:
            assert normalize_uri(orig) == orig, f"Roundtrip failed for {orig}"

    def test_invalid_scheme(self):
        with pytest.raises(ValueError, match="Unknown URI scheme"):
            parse_uri("/id/invalid/something")

    def test_missing_prefix(self):
        with pytest.raises(ValueError, match="must start with"):
            parse_uri("/law/arbeidswet-1963")


class TestConvenienceBuilders:
    def test_law_work_uri(self):
        assert law_work_uri("arbeidswet-1963") == "/id/law/arbeidswet-1963"

    def test_law_expression_uri(self):
        assert law_expression_uri("arbeidswet-1963", date(2024, 1, 15)) == \
            "/id/law/arbeidswet-1963/2024-01-15"

    def test_law_fragment_uri_article(self):
        assert law_fragment_uri("arbeidswet-1963", date(2024, 1, 15), "3:2") == \
            "/id/law/arbeidswet-1963/2024-01-15/article/3:2"

    def test_law_fragment_uri_article_paragraph(self):
        assert law_fragment_uri("arbeidswet-1963", date(2024, 1, 15), "3:2", paragraph="1") == \
            "/id/law/arbeidswet-1963/2024-01-15/article/3:2/paragraph/1"

    def test_law_fragment_uri_article_paragraph_sub(self):
        assert law_fragment_uri("arbeidswet-1963", date(2024, 1, 15), "6:162", paragraph="1", sub="a") == \
            "/id/law/arbeidswet-1963/2024-01-15/article/6:162/paragraph/1/sub/a"

    def test_ecli_work_uri(self):
        assert ecli_work_uri("ECLI:NL:HR:2020:1234") == "/id/ecli/ECLI:NL:HR:2020:1234"

    def test_ecli_fragment_uri(self):
        assert ecli_fragment_uri("ECLI:NL:HR:2020:1234", "consideration", "4.3") == \
            "/id/ecli/ECLI:NL:HR:2020:1234/consideration/4.3"


class TestAbbreviationRegistry:
    """Tests for the AbbreviationRegistry class and resolve_abbreviation function."""

    def test_exact_match(self):
        assert resolve_abbreviation("BW") == "burgerlijk-wetboek"

    def test_case_insensitive(self):
        assert resolve_abbreviation("gw") == "grondwet-1987"

    def test_unknown(self):
        assert resolve_abbreviation("NonExistentLaw") is None

    def test_common_aliases(self):
        assert resolve_abbreviation("WvSr") == resolve_abbreviation("Sr")
        assert resolve_abbreviation("Grondwet") == resolve_abbreviation("GW")

    def test_suriname_slugs(self):
        """Abbreviations now resolve to Suriname slugs, not BWB IDs."""
        assert resolve_abbreviation("BW") == "burgerlijk-wetboek"
        assert resolve_abbreviation("Grondwet") == "grondwet-1987"
        assert resolve_abbreviation("Sr") == "wetboek-van-strafrecht"

    def test_custom_registry(self):
        """AbbreviationRegistry supports custom registrations."""
        registry = AbbreviationRegistry()
        registry.register("TestWet", "test-wet-2024")
        assert registry.resolve("TestWet") == "test-wet-2024"
        assert registry.resolve("testwet") == "test-wet-2024"
        assert registry.resolve("UnknownWet") is None

    def test_registry_register_many(self):
        registry = AbbreviationRegistry()
        registry.register_many({
            "Foo": "foo-wet",
            "Bar": "bar-wet",
        })
        assert registry.count == 2
        assert registry.resolve("Foo") == "foo-wet"
        assert registry.resolve("Bar") == "bar-wet"

    def test_registry_get_abbreviations(self):
        registry = AbbreviationRegistry()
        registry.register("AW", "arbeidswet-1963")
        registry.register("Arbeidswet", "arbeidswet-1963")
        abbrs = registry.get_abbreviations("arbeidswet-1963")
        assert "AW" in abbrs
        assert "Arbeidswet" in abbrs


# ===================================================================
# Versioning
# ===================================================================

class TestVersionChain:
    @pytest.fixture
    def work(self):
        return Work(
            id="w-test",
            uri="/id/law/arbeidswet-1963",
            source_type=SourceType.LEGISLATION,
            official_id="arbeidswet-1963",
            title="Arbeidswet 1963",
        )

    def _make_expression(self, work, version_date, expr_id=None):
        d = version_date
        eid = expr_id or f"e-{d.isoformat()}"
        return Expression(
            id=eid,
            uri=f"/id/law/arbeidswet-1963/{d.isoformat()}",
            work_id=work.id,
            work_uri=work.uri,
            version_date=d,
            in_force=TemporalExtent(start=d),
        )

    def test_add_and_lookup(self, work):
        chain = VersionChain(work)
        e1 = self._make_expression(work, date(2020, 1, 1))
        e2 = self._make_expression(work, date(2022, 6, 1))
        e3 = self._make_expression(work, date(2024, 1, 15))

        chain.add_expression(e1)
        chain.add_expression(e3)
        chain.add_expression(e2)

        assert chain.count == 3
        assert chain.earliest.version_date == date(2020, 1, 1)
        assert chain.latest.version_date == date(2024, 1, 15)

    def test_at_date(self, work):
        chain = VersionChain(work)
        e1 = self._make_expression(work, date(2020, 1, 1))
        e2 = self._make_expression(work, date(2022, 6, 1))
        chain.add_expression(e1)
        chain.add_expression(e2)

        assert chain.at_date(date(2019, 1, 1)) is None
        result = chain.at_date(date(2021, 6, 15))
        assert result.version_date == date(2020, 1, 1)
        result = chain.at_date(date(2025, 1, 1))
        assert result.version_date == date(2022, 6, 1)

    def test_prev_next_linking(self, work):
        chain = VersionChain(work)
        e1 = self._make_expression(work, date(2020, 1, 1))
        e2 = self._make_expression(work, date(2022, 1, 1))
        e3 = self._make_expression(work, date(2024, 1, 1))

        chain.add_expression(e1)
        chain.add_expression(e2)
        chain.add_expression(e3)

        assert e1.next_expression_id == e2.id
        assert e2.previous_expression_id == e1.id
        assert e2.next_expression_id == e3.id
        assert e3.previous_expression_id == e2.id

    def test_duplicate_date_raises(self, work):
        chain = VersionChain(work)
        chain.add_expression(self._make_expression(work, date(2020, 1, 1), "e1"))
        with pytest.raises(ValueError, match="already exists"):
            chain.add_expression(self._make_expression(work, date(2020, 1, 1), "e2"))

    def test_wrong_work_raises(self, work):
        other = Work(
            id="w-other", uri="/id/law/grondwet-1987",
            source_type=SourceType.LEGISLATION, official_id="grondwet-1987",
            title="Grondwet 1987",
        )
        chain = VersionChain(work)
        expr = self._make_expression(other, date(2020, 1, 1))
        with pytest.raises(ValueError, match="doesn't match"):
            chain.add_expression(expr)

    def test_versions_between(self, work):
        chain = VersionChain(work)
        for year in range(2018, 2025):
            chain.add_expression(self._make_expression(work, date(year, 1, 1)))

        result = chain.versions_between(date(2020, 1, 1), date(2022, 12, 31))
        assert len(result) == 3


class TestTemporalIndex:
    def test_works_in_force(self):
        index = TemporalIndex()
        for slug, title in [("arbeidswet-1963", "AW"), ("grondwet-1987", "GW")]:
            work = Work(
                id=f"w-{slug}", uri=f"/id/law/{slug}",
                source_type=SourceType.LEGISLATION, official_id=slug, title=title,
            )
            chain = VersionChain(work)
            chain.add_expression(Expression(
                id=f"e-{slug}", uri=f"/id/law/{slug}/2020-01-01",
                work_id=work.id, work_uri=work.uri,
                version_date=date(2020, 1, 1),
            ))
            index.add_chain(chain)

        works = index.works_in_force_on(date(2024, 6, 1))
        assert len(works) == 2

    def test_stats(self):
        index = TemporalIndex()
        assert index.stats()["works"] == 0


# ===================================================================
# Store
# ===================================================================

class TestCanonicalStore:
    @pytest.fixture
    def store(self, tmp_path):
        db_path = str(tmp_path / "test_canonical.db")
        s = CanonicalStore(db_path)
        yield s
        s.close()

    @pytest.fixture
    def sample_work(self):
        return Work(
            id="w-arbeidswet-1963",
            uri="/id/law/arbeidswet-1963",
            source_type=SourceType.LEGISLATION,
            official_id="arbeidswet-1963",
            title="Arbeidswet 1963",
            short_title="AW",
            status=DocumentStatus.IN_FORCE,
            date_enacted=date(1963, 1, 1),
            date_first_in_force=date(1963, 1, 1),
            subject_areas=["arbeidsrecht"],
            keywords=["arbeid", "werknemers"],
        )

    @pytest.fixture
    def sample_expression(self, sample_work):
        return Expression(
            id="e-arbeidswet-1963-20240115",
            uri="/id/law/arbeidswet-1963/2024-01-15",
            work_id=sample_work.id,
            work_uri=sample_work.uri,
            version_date=date(2024, 1, 15),
            in_force=TemporalExtent(start=date(2024, 1, 15)),
            title="Arbeidswet 1963 geldig op 2024-01-15",
            status=DocumentStatus.IN_FORCE,
            full_text="Arbeidswet 1963. Regeling van arbeidsvoorwaarden...",
        )

    @pytest.fixture
    def sample_fragment(self, sample_work, sample_expression):
        return Fragment(
            id="f-arbeidswet-1963-20240115-art2",
            uri="/id/law/arbeidswet-1963/2024-01-15/article/2",
            expression_id=sample_expression.id,
            expression_uri=sample_expression.uri,
            work_id=sample_work.id,
            fragment_type=FragmentType.ARTICLE,
            number="2",
            title="Article 2",
            text="De werkgever is verplicht de arbeidsovereenkomst na te komen...",
            heading_path=["Arbeidswet 1963", "Article 2"],
            anchors=[
                FragmentAnchor.from_structural(
                    "/wetgeving/article[2]",
                    text="De werkgever is verplicht...",
                ),
            ],
        )

    def test_save_and_get_work(self, store, sample_work):
        store.save_work(sample_work)
        retrieved = store.get_work(sample_work.id)
        assert retrieved is not None
        assert retrieved.title == "Arbeidswet 1963"
        assert retrieved.source_type == SourceType.LEGISLATION
        assert retrieved.status == DocumentStatus.IN_FORCE
        assert "arbeidsrecht" in retrieved.subject_areas

    def test_get_work_by_uri(self, store, sample_work):
        store.save_work(sample_work)
        retrieved = store.get_work_by_uri("/id/law/arbeidswet-1963")
        assert retrieved is not None
        assert retrieved.id == sample_work.id

    def test_get_work_by_official_id(self, store, sample_work):
        store.save_work(sample_work)
        retrieved = store.get_work_by_official_id("arbeidswet-1963")
        assert retrieved is not None

    def test_save_and_get_expression(self, store, sample_work, sample_expression):
        store.save_work(sample_work)
        store.save_expression(sample_expression)
        retrieved = store.get_expression(sample_expression.id)
        assert retrieved is not None
        assert retrieved.version_date == date(2024, 1, 15)
        assert retrieved.in_force.start == date(2024, 1, 15)
        assert retrieved.full_text.startswith("Arbeidswet")

    def test_get_expression_at_date(self, store, sample_work):
        store.save_work(sample_work)

        e1 = Expression(
            id="e1", uri="/id/law/arbeidswet-1963/2020-01-01",
            work_id=sample_work.id, work_uri=sample_work.uri,
            version_date=date(2020, 1, 1),
        )
        e2 = Expression(
            id="e2", uri="/id/law/arbeidswet-1963/2023-06-01",
            work_id=sample_work.id, work_uri=sample_work.uri,
            version_date=date(2023, 6, 1),
        )
        store.save_expression(e1)
        store.save_expression(e2)

        result = store.get_expression_at_date(sample_work.id, date(2022, 3, 15))
        assert result.id == "e1"

        result = store.get_expression_at_date(sample_work.id, date(2024, 1, 1))
        assert result.id == "e2"

        result = store.get_expression_at_date(sample_work.id, date(2019, 1, 1))
        assert result is None

    def test_save_and_get_fragment(self, store, sample_work, sample_expression, sample_fragment):
        store.save_work(sample_work)
        store.save_expression(sample_expression)
        store.save_fragment(sample_fragment)

        retrieved = store.get_fragment(sample_fragment.id)
        assert retrieved is not None
        assert retrieved.fragment_type == FragmentType.ARTICLE
        assert retrieved.number == "2"
        assert "werkgever" in retrieved.text
        assert len(retrieved.anchors) == 1
        assert retrieved.anchors[0].anchor_type == AnchorType.STRUCTURAL

    def test_get_fragment_by_uri(self, store, sample_work, sample_expression, sample_fragment):
        store.save_work(sample_work)
        store.save_expression(sample_expression)
        store.save_fragment(sample_fragment)

        retrieved = store.get_fragment_by_uri("/id/law/arbeidswet-1963/2024-01-15/article/2")
        assert retrieved is not None
        assert retrieved.id == sample_fragment.id

    def test_get_fragments_for_expression(self, store, sample_work, sample_expression):
        store.save_work(sample_work)
        store.save_expression(sample_expression)

        for i, art_num in enumerate(["1", "2", "3"]):
            frag = Fragment(
                id=f"f-art{art_num}",
                uri=f"/id/law/arbeidswet-1963/2024-01-15/article/{art_num}",
                expression_id=sample_expression.id,
                expression_uri=sample_expression.uri,
                work_id=sample_work.id,
                fragment_type=FragmentType.ARTICLE,
                number=art_num,
                position=i,
                text=f"Text of article {art_num}",
            )
            store.save_fragment(frag)

        frags = store.get_fragments_for_expression(sample_expression.id)
        assert len(frags) == 3

    def test_manifestation(self, store, sample_work, sample_expression):
        store.save_work(sample_work)
        store.save_expression(sample_expression)

        man = Manifestation(
            id="m-xml-1",
            uri="/id/law/arbeidswet-1963/2024-01-15/xml",
            expression_id=sample_expression.id,
            expression_uri=sample_expression.uri,
            format=ManifestationType.XML,
            media_type="application/xml",
            storage_path="bronze/law/arbeidswet-1963/2024-01-15.xml",
            checksum_sha256="abc123",
            byte_size=50000,
        )
        store.save_manifestation(man)

        results = store.get_manifestations_for_expression(sample_expression.id)
        assert len(results) == 1
        assert results[0].format == ManifestationType.XML

    def test_stats(self, store, sample_work, sample_expression, sample_fragment):
        store.save_work(sample_work)
        store.save_expression(sample_expression)
        store.save_fragment(sample_fragment)

        stats = store.stats()
        assert stats["works"] == 1
        assert stats["expressions"] == 1
        assert stats["fragments"] == 1

    def test_build_temporal_index(self, store, sample_work):
        store.save_work(sample_work)
        for d in [date(2020, 1, 1), date(2022, 1, 1), date(2024, 1, 1)]:
            expr = Expression(
                id=f"e-{d.isoformat()}",
                uri=f"/id/law/arbeidswet-1963/{d.isoformat()}",
                work_id=sample_work.id, work_uri=sample_work.uri,
                version_date=d,
            )
            store.save_expression(expr)

        index = store.build_temporal_index()
        assert index.work_count == 1

        chain = index.get_chain(sample_work.id)
        assert chain.count == 3

        expr = index.expression_at(sample_work.id, date(2021, 6, 15))
        assert expr.version_date == date(2020, 1, 1)

    def test_upsert_work(self, store, sample_work):
        store.save_work(sample_work)
        sample_work.status = DocumentStatus.REPEALED
        store.save_work(sample_work)

        retrieved = store.get_work(sample_work.id)
        assert retrieved.status == DocumentStatus.REPEALED

    def test_search_fragments_by_text(self, store, sample_work, sample_expression, sample_fragment):
        store.save_work(sample_work)
        store.save_expression(sample_expression)
        store.save_fragment(sample_fragment)

        results = store.search_fragments_by_text("werkgever")
        assert len(results) == 1
        assert results[0].id == sample_fragment.id


# ===================================================================
# Integration: end-to-end workflow
# ===================================================================

class TestEndToEnd:
    def test_full_law_workflow(self, tmp_path):
        store = CanonicalStore(str(tmp_path / "e2e.db"))

        work = Work(
            id="w-arbeidswet",
            uri=law_work_uri("arbeidswet-1963"),
            source_type=SourceType.LEGISLATION,
            official_id="arbeidswet-1963",
            title="Arbeidswet 1963",
            short_title="AW",
            status=DocumentStatus.IN_FORCE,
        )
        store.save_work(work)

        for d in [date(2020, 1, 1), date(2023, 7, 1)]:
            expr = Expression(
                id=f"e-aw-{d.isoformat()}",
                uri=law_expression_uri("arbeidswet-1963", d),
                work_id=work.id, work_uri=work.uri,
                version_date=d,
                in_force=TemporalExtent(start=d),
            )
            store.save_expression(expr)

        expr_2023 = store.get_expression_at_date(work.id, date(2023, 7, 1))
        for i, art in enumerate(["1", "2", "3"]):
            frag = Fragment(
                id=f"f-aw-2023-art{art}",
                uri=law_fragment_uri("arbeidswet-1963", date(2023, 7, 1), art),
                expression_id=expr_2023.id,
                expression_uri=expr_2023.uri,
                work_id=work.id,
                fragment_type=FragmentType.ARTICLE,
                number=art,
                position=i,
                text=f"Inhoud van artikel {art} Arbeidswet",
            )
            store.save_fragment(frag)

        expr = store.get_expression_at_date(work.id, date(2024, 1, 1))
        assert expr.version_date == date(2023, 7, 1)

        target_uri = law_fragment_uri("arbeidswet-1963", date(2023, 7, 1), "2")
        frag = store.get_fragment_by_uri(target_uri)
        assert frag is not None
        assert "2" in frag.text

        index = store.build_temporal_index()
        assert index.expression_at(work.id, date(2021, 6, 1)).version_date == date(2020, 1, 1)

        stats = store.stats()
        assert stats["works"] == 1
        assert stats["expressions"] == 2
        assert stats["fragments"] == 3

        store.close()

    def test_full_ecli_workflow(self, tmp_path):
        store = CanonicalStore(str(tmp_path / "ecli_e2e.db"))

        ecli = "ECLI:NL:HR:2020:1234"

        work = Work(
            id="w-hr-2020-1234",
            uri=ecli_work_uri(ecli),
            source_type=SourceType.CASE_LAW,
            official_id=ecli,
            title="Hoge Raad 15 juni 2020 (onrechtmatige daad)",
            document_type="arrest",
        )
        store.save_work(work)

        expr = Expression(
            id="e-hr-2020-1234",
            uri=ecli_work_uri(ecli),
            work_id=work.id, work_uri=work.uri,
            version_date=date(2020, 6, 15),
        )
        store.save_expression(expr)

        for ro_num in ["4.1", "4.2", "4.3"]:
            frag = Fragment(
                id=f"f-hr-consideration-{ro_num}",
                uri=ecli_fragment_uri(ecli, "consideration", ro_num),
                expression_id=expr.id, expression_uri=expr.uri,
                work_id=work.id,
                fragment_type=FragmentType.CONSIDERATION,
                number=ro_num,
                text=f"Rechtsoverweging {ro_num} tekst...",
            )
            store.save_fragment(frag)

        frag_decision = Fragment(
            id="f-hr-decision",
            uri=ecli_fragment_uri(ecli, "decision"),
            expression_id=expr.id, expression_uri=expr.uri,
            work_id=work.id,
            fragment_type=FragmentType.DECISION,
            text="De Hoge Raad vernietigt het arrest...",
        )
        store.save_fragment(frag_decision)

        ro43 = store.get_fragment_by_uri(ecli_fragment_uri(ecli, "consideration", "4.3"))
        assert ro43 is not None
        assert ro43.fragment_type == FragmentType.CONSIDERATION

        frags = store.get_fragments_for_expression(expr.id)
        assert len(frags) == 4

        store.close()
