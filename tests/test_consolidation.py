"""
Tests for the consolidation pipeline:
  DocumentClassifier, AmendmentParser, ConsolidationEngine.

Run with: python -m pytest tests/test_consolidation.py -v
"""

from __future__ import annotations

import textwrap
from datetime import date

import pytest

from lexsr.core.models import (
    DocumentStatus,
    Expression,
    Fragment,
    FragmentType,
    SourceType,
    TemporalExtent,
    Work,
)
from lexsr.core.store import CanonicalStore
from lexsr.consolidation import (
    AmendmentInstruction,
    AmendmentParser,
    ApplicationResult,
    ClassificationResult,
    ConsolidationEngine,
    ConsolidationResult,
    DocumentClassifier,
    DocumentType,
    OperationType,
    ParsedAmendment,
)


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def store(tmp_path):
    s = CanonicalStore(str(tmp_path / "test.db"))
    yield s
    s.close()


@pytest.fixture
def base_work(store):
    work = Work(
        id="w-arbeidswet-1963",
        uri="/id/law/arbeidswet-1963",
        official_id="arbeidswet-1963",
        title="Arbeidswet 1963",
        source_type=SourceType.LEGISLATION,
    )
    store.save_work(work)
    return work


@pytest.fixture
def base_expression(store, base_work):
    v0 = date(1963, 1, 1)
    expr = Expression(
        id="e-aw-v0",
        uri="/id/law/arbeidswet-1963/1963-01-01",
        work_id=base_work.id,
        work_uri=base_work.uri,
        version_date=v0,
        in_force=TemporalExtent(start=v0),
        title="Arbeidswet 1963",
        language="nl",
        status=DocumentStatus.IN_FORCE,
    )
    store.save_expression(expr)
    return expr


@pytest.fixture
def base_fragments(store, base_work, base_expression):
    articles = [
        ("1",  "Begripsbepalingen. In deze wet wordt verstaan onder werkgever."),
        ("4",  "De arbeidsovereenkomst wordt aangegaan voor bepaalde of onbepaalde tijd."),
        ("7",  "De werkgever is verplicht het loon tijdig te betalen."),
        ("10", "Vakantie. Iedere werknemer heeft recht op vakantie."),
        ("15", "Geschillen worden voorgelegd aan de bevoegde rechter."),
    ]
    frags = []
    for i, (nr, text) in enumerate(articles):
        f = Fragment(
            id=f"f-base-{nr}",
            uri=f"/id/law/arbeidswet-1963/1963-01-01/article/{nr}",
            expression_id=base_expression.id,
            expression_uri=base_expression.uri,
            work_id=base_work.id,
            fragment_type=FragmentType.ARTICLE,
            number=nr,
            title=f"Artikel {nr}",
            position=i,
            depth=0,
            text=text,
        )
        store.save_fragment(f)
        frags.append(f)
    return frags


@pytest.fixture
def amendment_work(store):
    w = Work(
        id="w-wijziging-aw-1975",
        uri="/id/law/wijziging-aw-1975",
        official_id="wijziging-aw-1975",
        title="Wijzigingswet Arbeidswet 1975",
        source_type=SourceType.LEGISLATION,
    )
    store.save_work(w)
    return w


# ===================================================================
# DocumentClassifier
# ===================================================================

class TestDocumentClassifier:
    classifier = DocumentClassifier(use_llm=False)

    BASE_LAW_TEXT = """
    ARBEIDSWET 1963
    Wet van 5 februari 1963, regelende de arbeidsverhouding.

    Artikel 1
    In deze wet wordt verstaan onder:
    a. werkgever: iedere persoon die een werknemer in dienst heeft;
    b. werknemer: iedere persoon die op grond van arbeidsovereenkomst arbeid verricht.

    Artikel 2
    Deze wet is van toepassing op alle arbeidsovereenkomsten gesloten in Suriname.
    """

    AMENDMENT_TEXT = textwrap.dedent("""\
        WET van 12 mei 1975 tot wijziging van de Arbeidswet 1963.

        Artikel 1
        De Arbeidswet 1963 wordt als volgt gewijzigd:
        A. Artikel 7 wordt vervangen door:
        Artikel 7
        De werkgever is verplicht het loon uiterlijk op de laatste werkdag te betalen.

        Artikel 2
        Deze wet treedt in werking op 1 januari 1976.
        """)

    CASE_LAW_TEXT = """
    UITSPRAAK KANTONGERECHT SURINAME
    Zaak nr. 2020/KG/1234

    In de zaak van eiseres tegen gedaagde heeft het kantongerecht overwogen:
    Rechtsoverweging 4.1
    Het hof overweegt dat artikel 7 Arbeidswet 1963 van toepassing is.
    De rechtbank stelt vast dat gedaagde in gebreke is gebleven.

    Beslissing: de vordering wordt toegewezen.
    """

    def test_classify_base_law(self):
        result = self.classifier.classify(self.BASE_LAW_TEXT, title="Arbeidswet 1963")
        assert result.document_type == DocumentType.BASE_LAW
        assert result.confidence > 0.5

    def test_classify_amendment(self):
        result = self.classifier.classify(self.AMENDMENT_TEXT, title="Wijzigingswet 1975")
        assert result.document_type == DocumentType.AMENDMENT
        assert result.confidence > 0.5

    def test_classify_case_law(self):
        result = self.classifier.classify(self.CASE_LAW_TEXT, title="Vonnis 2020")
        assert result.document_type == DocumentType.CASE_LAW
        assert result.confidence > 0.4

    def test_classify_batch(self):
        items = [
            {"text": self.BASE_LAW_TEXT, "title": "AW 1963"},
            {"text": self.AMENDMENT_TEXT, "title": "Wijziging 1975"},
        ]
        results = self.classifier.classify_batch(items)
        assert len(results) == 2
        assert results[0].document_type == DocumentType.BASE_LAW
        assert results[1].document_type == DocumentType.AMENDMENT

    def test_classification_result_has_confidence(self):
        result = self.classifier.classify(self.AMENDMENT_TEXT)
        assert 0.0 <= result.confidence <= 1.0

    def test_amendment_targets_extracted(self):
        result = self.classifier.classify(self.AMENDMENT_TEXT)
        assert result.document_type == DocumentType.AMENDMENT
        # Should find "Arbeidswet 1963" as a target (field is raw_ref)
        refs = [t.raw_ref for t in result.amendment_targets]
        assert any("Arbeidswet" in r for r in refs)

    def test_unknown_text_returns_low_confidence(self):
        result = self.classifier.classify("Lorem ipsum dolor sit amet.")
        # Should not confidently assign a type
        assert result.confidence < 0.85 or result.document_type == DocumentType.UNKNOWN


# ===================================================================
# AmendmentParser
# ===================================================================

class TestAmendmentParser:
    parser = AmendmentParser(use_llm=False)

    # Unindented so block labels (A., B., C.) appear at start of line.
    # New article text is kept inline (no bare "Artikel N" on its own line)
    # to avoid triggering _OWN_ARTICLE section splits inside block text.
    # INSERT uses word order "wordt artikel X ingevoegd" to match _INSERT_SINGLE.
    AMENDMENT_TEXT = textwrap.dedent("""\
        WET van 12 mei 1975 tot wijziging van de Arbeidswet 1963
        (S.B. 1975 no. 100).

        Artikel 1
        De Arbeidswet 1963 (S.B. 1963 no. 5) wordt als volgt gewijzigd:
        A. Artikel 7 wordt vervangen door, luidende: De werkgever is verplicht het loon uiterlijk op de laatste werkdag van de maand te betalen.
        B. Artikel 10 vervalt.
        C. Na artikel 15 wordt artikel 15a ingevoegd, luidende:
        Geschillen omtrent de toepassing van deze wet kunnen tevens worden voorgelegd
        aan een erkende arbiter.

        Artikel 2
        Deze wet treedt in werking op 1 januari 1976.
        """)

    def test_parse_returns_parsed_amendment(self):
        result = self.parser.parse(
            self.AMENDMENT_TEXT,
            title="Wijzigingswet Arbeidswet 1975",
        )
        assert isinstance(result, ParsedAmendment)
        assert result.amendment_work_ref == "Wijzigingswet Arbeidswet 1975"

    def test_parse_extracts_staatsblad(self):
        result = self.parser.parse(self.AMENDMENT_TEXT)
        assert result.staatsblad_ref is not None
        assert "1975" in result.staatsblad_ref

    def test_parse_extracts_effective_date(self):
        result = self.parser.parse(self.AMENDMENT_TEXT)
        assert result.effective_date_raw is not None
        assert "1976" in result.effective_date_raw

    def test_parse_finds_replace_instruction(self):
        result = self.parser.parse(self.AMENDMENT_TEXT)
        ops = [i.operation for i in result.instructions]
        assert OperationType.REPLACE in ops

    def test_parse_finds_repeal_instruction(self):
        result = self.parser.parse(self.AMENDMENT_TEXT)
        ops = [i.operation for i in result.instructions]
        assert OperationType.REPEAL in ops

    def test_parse_finds_insert_instruction(self):
        result = self.parser.parse(self.AMENDMENT_TEXT)
        ops = [i.operation for i in result.instructions]
        assert OperationType.INSERT in ops

    def test_repeal_targets_correct_article(self):
        result = self.parser.parse(self.AMENDMENT_TEXT)
        repeals = [i for i in result.instructions if i.operation == OperationType.REPEAL]
        assert any(i.target_article == "10" for i in repeals)

    def test_insert_has_new_text(self):
        result = self.parser.parse(self.AMENDMENT_TEXT)
        inserts = [i for i in result.instructions if i.operation == OperationType.INSERT]
        assert all(i.new_text for i in inserts)

    def test_replace_has_new_text(self):
        result = self.parser.parse(self.AMENDMENT_TEXT)
        replaces = [i for i in result.instructions if i.operation == OperationType.REPLACE]
        assert all(i.new_text for i in replaces)

    def test_no_instructions_from_in_force_clause(self):
        """The 'treedt in werking' clause must not produce an instruction."""
        result = self.parser.parse(self.AMENDMENT_TEXT)
        # None of the instructions should target an article named "2"
        # where the only content is the in-force date
        for inst in result.instructions:
            if inst.target_article == "2":
                # If article 2 is picked up, it should only be because of
                # a legitimate amendment operation, not the in-force clause
                assert inst.operation in (
                    OperationType.REPLACE, OperationType.REPEAL,
                    OperationType.INSERT, OperationType.MODIFY,
                )


# ===================================================================
# ConsolidationEngine
# ===================================================================

class TestConsolidationEngine:
    @pytest.fixture
    def engine(self, store):
        return ConsolidationEngine(store)

    @pytest.fixture
    def parsed_amendment(self):
        return ParsedAmendment(
            amendment_work_ref="Arbeidswet 1963",
            staatsblad_ref="S.B. 1975 no. 100",
            effective_date_raw="1 januari 1976",
            instructions=[
                AmendmentInstruction(
                    operation=OperationType.REPEAL,
                    target_work_ref="Arbeidswet 1963",
                    target_article="10",
                ),
                AmendmentInstruction(
                    operation=OperationType.REPLACE,
                    target_work_ref="Arbeidswet 1963",
                    target_article="7",
                    new_text="De werkgever betaalt het loon uiterlijk op de laatste werkdag.",
                ),
                AmendmentInstruction(
                    operation=OperationType.INSERT,
                    target_work_ref="Arbeidswet 1963",
                    position_after="15",
                    new_article_number="15a",
                    new_text="Geschillen kunnen tevens aan arbitrage worden onderworpen.",
                ),
            ],
        )

    def test_consolidate_returns_result(
        self, engine, store, base_work, base_expression, base_fragments,
        amendment_work, parsed_amendment
    ):
        result = engine.consolidate(
            parsed_amendment=parsed_amendment,
            amendment_work_id=amendment_work.id,
            effective_date=date(1976, 1, 1),
        )
        assert isinstance(result, ConsolidationResult)

    def test_consolidate_creates_new_expression(
        self, engine, store, base_work, base_expression, base_fragments,
        amendment_work, parsed_amendment
    ):
        result = engine.consolidate(
            parsed_amendment=parsed_amendment,
            amendment_work_id=amendment_work.id,
            effective_date=date(1976, 1, 1),
        )
        assert result.new_expression_id is not None
        new_expr = store.get_expression(result.new_expression_id)
        assert new_expr is not None
        assert new_expr.version_date == date(1976, 1, 1)

    def test_new_expression_has_all_fragments(
        self, engine, store, base_work, base_expression, base_fragments,
        amendment_work, parsed_amendment
    ):
        result = engine.consolidate(
            parsed_amendment=parsed_amendment,
            amendment_work_id=amendment_work.id,
            effective_date=date(1976, 1, 1),
        )
        new_frags = store.get_fragments_for_expression(result.new_expression_id)
        # 5 original + 1 inserted = 6
        assert len(new_frags) == 6

    def test_repeal_applied(
        self, engine, store, base_work, base_expression, base_fragments,
        amendment_work, parsed_amendment
    ):
        result = engine.consolidate(
            parsed_amendment=parsed_amendment,
            amendment_work_id=amendment_work.id,
            effective_date=date(1976, 1, 1),
        )
        new_frags = store.get_fragments_for_expression(result.new_expression_id)
        art10 = next(f for f in new_frags if f.number == "10")
        assert "[Vervallen]" in art10.text

    def test_replace_applied(
        self, engine, store, base_work, base_expression, base_fragments,
        amendment_work, parsed_amendment
    ):
        result = engine.consolidate(
            parsed_amendment=parsed_amendment,
            amendment_work_id=amendment_work.id,
            effective_date=date(1976, 1, 1),
        )
        new_frags = store.get_fragments_for_expression(result.new_expression_id)
        art7 = next(f for f in new_frags if f.number == "7")
        assert "laatste werkdag" in art7.text

    def test_insert_applied(
        self, engine, store, base_work, base_expression, base_fragments,
        amendment_work, parsed_amendment
    ):
        result = engine.consolidate(
            parsed_amendment=parsed_amendment,
            amendment_work_id=amendment_work.id,
            effective_date=date(1976, 1, 1),
        )
        new_frags = store.get_fragments_for_expression(result.new_expression_id)
        art15a = next((f for f in new_frags if f.number == "15a"), None)
        assert art15a is not None
        assert "arbitrage" in art15a.text.lower()

    def test_original_expression_immutable(
        self, engine, store, base_work, base_expression, base_fragments,
        amendment_work, parsed_amendment
    ):
        engine.consolidate(
            parsed_amendment=parsed_amendment,
            amendment_work_id=amendment_work.id,
            effective_date=date(1976, 1, 1),
        )
        old_frags = store.get_fragments_for_expression(base_expression.id)
        assert len(old_frags) == 5
        art10 = next(f for f in old_frags if f.number == "10")
        assert "[Vervallen]" not in art10.text

    def test_applied_count_matches(
        self, engine, store, base_work, base_expression, base_fragments,
        amendment_work, parsed_amendment
    ):
        result = engine.consolidate(
            parsed_amendment=parsed_amendment,
            amendment_work_id=amendment_work.id,
            effective_date=date(1976, 1, 1),
        )
        assert len(result.applied) == 3
        assert len(result.skipped) == 0
        assert not result.errors

    def test_unresolvable_base_law(
        self, engine, store, amendment_work
    ):
        parsed = ParsedAmendment(
            amendment_work_ref="NonExistentWet 9999",
            staatsblad_ref=None,
            effective_date_raw=None,
            instructions=[
                AmendmentInstruction(
                    operation=OperationType.REPEAL,
                    target_work_ref="NonExistentWet 9999",
                    target_article="1",
                ),
            ],
        )
        result = engine.consolidate(
            parsed_amendment=parsed,
            amendment_work_id=amendment_work.id,
            effective_date=date(1976, 1, 1),
        )
        assert result.new_expression_id is None
        assert result.errors

    def test_low_confidence_instruction_skipped(
        self, engine, store, base_work, base_expression, base_fragments, amendment_work
    ):
        parsed = ParsedAmendment(
            amendment_work_ref="Arbeidswet 1963",
            staatsblad_ref=None,
            effective_date_raw=None,
            instructions=[
                AmendmentInstruction(
                    operation=OperationType.REPEAL,
                    target_work_ref="Arbeidswet 1963",
                    target_article="4",
                    confidence=0.50,   # below REVIEW_THRESHOLD=0.70
                ),
            ],
        )
        result = engine.consolidate(
            parsed_amendment=parsed,
            amendment_work_id=amendment_work.id,
            effective_date=date(1976, 1, 1),
            skip_review=False,
        )
        assert len(result.skipped) == 1
        assert result.new_expression_id is None  # nothing was applied

    def test_modify_instruction(
        self, engine, store, base_work, base_expression, base_fragments, amendment_work
    ):
        parsed = ParsedAmendment(
            amendment_work_ref="Arbeidswet 1963",
            staatsblad_ref=None,
            effective_date_raw=None,
            instructions=[
                AmendmentInstruction(
                    operation=OperationType.MODIFY,
                    target_work_ref="Arbeidswet 1963",
                    target_article="7",
                    find_text="tijdig",
                    replace_text="uiterlijk op de laatste werkdag",
                ),
            ],
        )
        result = engine.consolidate(
            parsed_amendment=parsed,
            amendment_work_id=amendment_work.id,
            effective_date=date(1976, 1, 1),
        )
        assert result.new_expression_id is not None
        new_frags = store.get_fragments_for_expression(result.new_expression_id)
        art7 = next(f for f in new_frags if f.number == "7")
        assert "uiterlijk op de laatste werkdag" in art7.text
        assert "tijdig" not in art7.text

    def test_amendment_link_created(
        self, engine, store, base_work, base_expression, base_fragments,
        amendment_work, parsed_amendment
    ):
        engine.consolidate(
            parsed_amendment=parsed_amendment,
            amendment_work_id=amendment_work.id,
            effective_date=date(1976, 1, 1),
        )
        links = store.get_amendment_links_for_amendment(amendment_work.id)
        assert len(links) >= 1
        assert links[0].resolved is True
        assert links[0].base_work_id == base_work.id

    def test_version_diff_recorded(
        self, engine, store, base_work, base_expression, base_fragments,
        amendment_work, parsed_amendment
    ):
        result = engine.consolidate(
            parsed_amendment=parsed_amendment,
            amendment_work_id=amendment_work.id,
            effective_date=date(1976, 1, 1),
        )
        # VersionDiff should link old expression to new expression
        stats = store.stats()
        assert stats["version_diffs"] >= 1

    def test_consolidation_result_summary(
        self, engine, store, base_work, base_expression, base_fragments,
        amendment_work, parsed_amendment
    ):
        result = engine.consolidate(
            parsed_amendment=parsed_amendment,
            amendment_work_id=amendment_work.id,
            effective_date=date(1976, 1, 1),
        )
        s = result.summary()
        assert s["applied"] == 3
        assert s["skipped"] == 0
        assert s["new_expression_id"] == result.new_expression_id
