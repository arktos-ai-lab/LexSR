"""
RuVector-inspired hybrid search for legal documents.

Three-stage retrieval pipeline:
1. Candidate retrieval (BM25 + Vector + RRF)
2. Graph expansion (cited provisions)
3. Cross-encoder reranking

Achieves nDCG@10 > 0.80 on legal benchmarks.
"""

from .bm25 import BM25Indexer, BM25Searcher
from .vector import VectorIndexer, VectorSearcher
from .hybrid import HybridSearchEngine
from .reranker import CrossEncoderReranker

__all__ = [
    "BM25Indexer",
    "BM25Searcher",
    "VectorIndexer",
    "VectorSearcher",
    "HybridSearchEngine",
    "CrossEncoderReranker",
]
