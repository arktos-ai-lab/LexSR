"""Knowledge graph: unifies legislation citations, amendment relationships,
and case-law citations (to legislation and to other cases) from the
canonical store into a single graph structure."""

from .knowledge_graph import build_graph, graph_stats, export_graphml, export_json_summary

__all__ = ["build_graph", "graph_stats", "export_graphml", "export_json_summary"]
