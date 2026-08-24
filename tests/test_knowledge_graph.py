"""
Tests for the knowledge graph builder.

Run with: python -m pytest tests/test_knowledge_graph.py -v
"""

from __future__ import annotations

from datetime import date

import pytest

from lexsr.core.models import (
    AmendmentLink,
    Citation,
    CitationType,
    DocumentStatus,
    Expression,
    SourceType,
    TemporalExtent,
    Work,
)
from lexsr.core.store import CanonicalStore
from lexsr.graph import build_graph, graph_stats


@pytest.fixture
def populated_store(tmp_path):
    """A small store: two laws (one amends the other), one case citing
    both a law and another (unindexed) case."""
    store = CanonicalStore(str(tmp_path / "graph_test.db"))

    base_law = Work(
        id="arbeidswet-1963", uri="/id/law/arbeidswet-1963",
        source_type=SourceType.LEGISLATION, official_id="arbeidswet-1963",
        title="Arbeidswet 1963", jurisdiction="SR",
    )
    amendment = Work(
        id="wijziging-arbeidswet-2020", uri="/id/law/wijziging-arbeidswet-2020",
        source_type=SourceType.LEGISLATION, official_id="wijziging-arbeidswet-2020",
        title="Wijziging Arbeidswet 2020", jurisdiction="SR",
    )
    case = Work(
        id="caselaw-sru-hvj-2022-1", uri="/id/caselaw/sru-hvj-2022-1",
        source_type=SourceType.CASE_LAW, official_id="SRU-HVJ-2022-1",
        title="GR 100", jurisdiction="SR",
    )
    for w in (base_law, amendment, case):
        store.save_work(w)

    expr = Expression(
        id="arbeidswet-1963-v1", uri="/id/law/arbeidswet-1963/2020-01-01",
        work_id=base_law.id, work_uri=base_law.uri,
        version_date=date(2020, 1, 1), in_force=TemporalExtent(start=date(2020, 1, 1)),
    )
    store.save_expression(expr)

    store.save_amendment_link(AmendmentLink(
        id="link1", amendment_work_id=amendment.id, base_work_id=base_law.id,
        base_work_ref="Arbeidswet 1963", resolved=True,
    ))

    store.save_citation(Citation(
        id="cit1", citation_type=CitationType.CASE_TO_LAW,
        source_work_id=case.id, target_work_id=base_law.id,
        raw_text="artikel 4 Arbeidswet 1963",
    ))
    # Citation to a work NOT in the store — should be dropped, not crash.
    store.save_citation(Citation(
        id="cit2", citation_type=CitationType.CASE_TO_CASE,
        source_work_id=case.id, target_work_id="caselaw-does-not-exist",
        raw_text="SRU-HvJ-1999-1",
    ))

    yield store
    store.close()


class TestBuildGraph:
    def test_all_works_become_nodes(self, populated_store):
        g = build_graph(populated_store)
        assert set(g.nodes) == {
            "arbeidswet-1963", "wijziging-arbeidswet-2020", "caselaw-sru-hvj-2022-1",
        }

    def test_node_type_attribute(self, populated_store):
        g = build_graph(populated_store)
        assert g.nodes["arbeidswet-1963"]["node_type"] == "legislation"
        assert g.nodes["caselaw-sru-hvj-2022-1"]["node_type"] == "case_law"

    def test_amendment_edge(self, populated_store):
        g = build_graph(populated_store)
        assert g.has_edge("wijziging-arbeidswet-2020", "arbeidswet-1963")
        edge_data = g.get_edge_data("wijziging-arbeidswet-2020", "arbeidswet-1963")
        assert any(d["edge_type"] == "AMENDS" for d in edge_data.values())

    def test_case_to_law_edge(self, populated_store):
        g = build_graph(populated_store)
        assert g.has_edge("caselaw-sru-hvj-2022-1", "arbeidswet-1963")
        edge_data = g.get_edge_data("caselaw-sru-hvj-2022-1", "arbeidswet-1963")
        assert any(d["edge_type"] == "APPLIES" for d in edge_data.values())

    def test_citation_to_unknown_work_dropped_not_crashed(self, populated_store):
        g = build_graph(populated_store)
        # cit2's target isn't a real work -> silently dropped, no phantom node
        assert "caselaw-does-not-exist" not in g.nodes
        assert g.number_of_edges() == 2  # AMENDS + the one valid citation


class TestGraphStats:
    def test_basic_counts(self, populated_store):
        g = build_graph(populated_store)
        stats = graph_stats(g)
        assert stats["nodes"] == 3
        assert stats["edges"] == 2
        assert stats["node_types"] == {"legislation": 2, "case_law": 1}
        assert stats["edge_types"] == {"AMENDS": 1, "APPLIES": 1}

    def test_top_cited_works(self, populated_store):
        g = build_graph(populated_store)
        stats = graph_stats(g)
        top = stats["top_cited_works"]
        assert top[0]["work_id"] == "arbeidswet-1963"
        assert top[0]["in_degree"] == 2  # amended AND cited

    def test_empty_graph(self):
        import networkx as nx
        g = nx.MultiDiGraph()
        stats = graph_stats(g)
        assert stats["nodes"] == 0
        assert stats["edges"] == 0
        assert stats["top_cited_works"] == []
