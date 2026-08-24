"""
Builds a unified knowledge graph from the canonical store.

Nodes: every Work (legislation or case law), typed by source_type.
Edges:
  - AMENDS      : amendment_links (amendment work -> base law it modifies)
  - CITES       : citations where citation_type = law_to_law
  - APPLIES     : citations where citation_type = case_to_law
                  (a court decision applying/interpreting legislation)
  - FOLLOWS     : citations where citation_type = case_to_case
                  (a court decision citing another decision)

No new tables — this reads the existing `works`, `amendment_links`, and
`citations` tables directly, the same data already populated by
`lexsr consolidate` and `lexsr link-citations` / `lexsr ingest-caselaw`.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any, Dict, Optional

import networkx as nx

from ..core.store import CanonicalStore

logger = logging.getLogger(__name__)

_CITATION_EDGE_LABELS = {
    "law_to_law": "CITES",
    "case_to_law": "APPLIES",
    "case_to_case": "FOLLOWS",
    "law_to_case": "CITES",
    "unknown": "CITES",
}


def build_graph(store: CanonicalStore) -> nx.MultiDiGraph:
    """Assemble the full knowledge graph from the canonical store."""
    g = nx.MultiDiGraph()

    work_rows = store._conn.execute(
        "SELECT id, title, source_type, jurisdiction, document_type, status, official_id "
        "FROM works"
    ).fetchall()

    for row in work_rows:
        work_id, title, source_type, jurisdiction, document_type, status, official_id = row
        g.add_node(
            work_id,
            title=title,
            node_type=source_type,
            jurisdiction=jurisdiction,
            document_type=document_type,
            status=status,
            official_id=official_id,
        )

    known_ids = set(g.nodes)

    amendment_rows = store._conn.execute(
        "SELECT amendment_work_id, base_work_id, confidence, resolved, effective_date "
        "FROM amendment_links WHERE base_work_id IS NOT NULL"
    ).fetchall()

    skipped_amendments = 0
    for amendment_work_id, base_work_id, confidence, resolved, effective_date in amendment_rows:
        if amendment_work_id not in known_ids or base_work_id not in known_ids:
            skipped_amendments += 1
            continue
        g.add_edge(
            amendment_work_id, base_work_id,
            edge_type="AMENDS",
            confidence=confidence,
            resolved=bool(resolved),
            effective_date=effective_date,
        )

    citation_rows = store._conn.execute(
        "SELECT source_work_id, target_work_id, citation_type, confidence, raw_text "
        "FROM citations WHERE target_work_id IS NOT NULL"
    ).fetchall()

    skipped_citations = 0
    for source_work_id, target_work_id, citation_type, confidence, raw_text in citation_rows:
        if source_work_id not in known_ids or target_work_id not in known_ids:
            skipped_citations += 1
            continue
        g.add_edge(
            source_work_id, target_work_id,
            edge_type=_CITATION_EDGE_LABELS.get(citation_type, "CITES"),
            citation_type=citation_type,
            confidence=confidence,
            raw_text=(raw_text or "")[:200],
        )

    if skipped_amendments or skipped_citations:
        logger.info(
            "Skipped %d amendment edges and %d citation edges with an "
            "endpoint not resolved to a work in the store (e.g. citations "
            "resolved only to a fragment URI, not a work_id)",
            skipped_amendments, skipped_citations,
        )

    logger.info(
        "Built graph: %d nodes, %d edges", g.number_of_nodes(), g.number_of_edges()
    )
    return g


def graph_stats(g: nx.MultiDiGraph) -> Dict[str, Any]:
    """Summary statistics for a knowledge graph."""
    node_types = Counter(data.get("node_type", "unknown") for _, data in g.nodes(data=True))
    edge_types = Counter(data.get("edge_type", "unknown") for _, _, data in g.edges(data=True))

    degrees = dict(g.degree())
    top_cited = sorted(
        ((n, g.in_degree(n)) for n in g.nodes),
        key=lambda x: x[1], reverse=True,
    )[:10]

    undirected = g.to_undirected()
    components = list(nx.connected_components(undirected))
    largest_component = max((len(c) for c in components), default=0)

    return {
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
        "node_types": dict(node_types),
        "edge_types": dict(edge_types),
        "connected_components": len(components),
        "largest_component_size": largest_component,
        "isolated_nodes": sum(1 for d in degrees.values() if d == 0),
        "top_cited_works": [
            {"work_id": n, "title": g.nodes[n].get("title", ""), "in_degree": d}
            for n, d in top_cited if d > 0
        ],
    }


def export_graphml(g: nx.MultiDiGraph, path: str) -> None:
    """Export for visualization tools (Gephi, yEd, Cytoscape)."""
    # GraphML requires scalar attribute values; drop None-valued attrs.
    clean = nx.MultiDiGraph()
    for n, data in g.nodes(data=True):
        clean.add_node(n, **{k: v for k, v in data.items() if v is not None})
    for u, v, data in g.edges(data=True):
        clean.add_edge(u, v, **{k: v for k, v in data.items() if v is not None})
    nx.write_graphml(clean, path)
    logger.info("Wrote GraphML to %s", path)


def export_json_summary(stats: Dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    logger.info("Wrote graph stats to %s", path)
