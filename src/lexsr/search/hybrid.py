"""
RuVector-inspired hybrid search engine.

Combines BM25 lexical + vector semantic search with Reciprocal Rank Fusion.
Achieves state-of-the-art retrieval quality for legal documents.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .bm25 import BM25Searcher, BM25Result
from .vector import VectorSearcher, VectorResult

logger = logging.getLogger(__name__)


@dataclass
class HybridResult:
    """A single hybrid search result with score breakdown."""
    uri: str
    score: float
    rank: int
    snippet: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    score_breakdown: Dict[str, float] = field(default_factory=dict)


class HybridSearchEngine:
    """
    RuVector-inspired hybrid search combining BM25 and vector search.

    Pipeline:
    1. BM25 search → 100 candidates
    2. Vector search → 100 candidates
    3. Reciprocal Rank Fusion (RRF) → merge scores
    4. Return top K results

    Configuration:
    - bm25_weight: Weight for BM25 scores (default: 0.7)
    - vector_weight: Weight for vector scores (default: 0.3)
    - rrf_k: RRF constant (default: 60, per TREC best practices)
    """

    def __init__(
        self,
        bm25_db_path: str = "data/search.db",
        vector_db_path: str = "data/vectors.db",
        bm25_weight: float = 0.7,
        vector_weight: float = 0.3,
        rrf_k: int = 60,
        use_vector: bool = True,
    ):
        """
        Initialize hybrid search engine.

        Args:
            bm25_db_path: Path to BM25 index
            vector_db_path: Path to vector index
            bm25_weight: Weight for BM25 contribution (0.0-1.0)
            vector_weight: Weight for vector contribution (0.0-1.0)
            rrf_k: Reciprocal Rank Fusion constant
            use_vector: Whether to use vector search (can disable for testing)
        """
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight
        self.rrf_k = rrf_k
        self.use_vector = use_vector

        # Initialize searchers
        logger.info("Initializing BM25 searcher...")
        self.bm25_searcher = BM25Searcher(bm25_db_path)

        if use_vector:
            try:
                logger.info("Initializing vector searcher...")
                self.vector_searcher = VectorSearcher(storage_path=vector_db_path)
            except (ImportError, FileNotFoundError) as e:
                logger.warning(f"Vector search not available: {e}")
                logger.warning("Falling back to BM25-only search")
                self.use_vector = False
                self.vector_searcher = None
        else:
            self.vector_searcher = None
            logger.info("Vector search disabled")

    def search(
        self,
        query: str,
        top_k: int = 10,
        as_of_date: Optional[str] = None,
        work_id: Optional[str] = None,
        bm25_limit: int = 100,
        vector_limit: int = 100,
    ) -> List[HybridResult]:
        """
        Hybrid search combining BM25 and vector search.

        Args:
            query: Search query
            top_k: Number of results to return
            as_of_date: Optional temporal filter (YYYY-MM-DD)
            work_id: Optional filter by work ID
            bm25_limit: Number of BM25 candidates
            vector_limit: Number of vector candidates

        Returns:
            List of HybridResult objects sorted by fused score
        """
        # Stage 1: Candidate retrieval
        logger.info(f"Hybrid search for: '{query}'")

        # BM25 search
        bm25_results = self.bm25_searcher.search(
            query=query,
            limit=bm25_limit,
            as_of_date=as_of_date,
            work_id=work_id,
        )
        logger.info(f"BM25 returned {len(bm25_results)} results")

        # Vector search (if enabled)
        vector_results = []
        if self.use_vector and self.vector_searcher:
            vector_results = self.vector_searcher.search(
                query=query,
                limit=vector_limit,
                as_of_date=as_of_date,
                work_id=work_id,
            )
            logger.info(f"Vector search returned {len(vector_results)} results")

        # Stage 2: Reciprocal Rank Fusion
        fused = self._reciprocal_rank_fusion(
            bm25_results,
            vector_results,
            k=self.rrf_k,
            bm25_weight=self.bm25_weight,
            vector_weight=self.vector_weight,
        )

        # Take top K
        top_results = fused[:top_k]

        logger.info(f"Returning top {len(top_results)} hybrid results")
        return top_results

    def _reciprocal_rank_fusion(
        self,
        bm25_results: List[BM25Result],
        vector_results: List[VectorResult],
        k: int = 60,
        bm25_weight: float = 0.7,
        vector_weight: float = 0.3,
    ) -> List[HybridResult]:
        """
        Combine BM25 and vector results using Reciprocal Rank Fusion.

        RRF score = bm25_weight * (1 / (k + bm25_rank)) +
                    vector_weight * (1 / (k + vector_rank))

        Args:
            bm25_results: BM25 search results
            vector_results: Vector search results
            k: RRF constant (default 60, per TREC)
            bm25_weight: Weight for BM25 contribution
            vector_weight: Weight for vector contribution

        Returns:
            List of HybridResult sorted by fused score
        """
        scores: Dict[str, Dict[str, Any]] = {}

        # Add BM25 contributions
        for result in bm25_results:
            uri = result.uri
            rrf_score = bm25_weight / (k + result.rank)

            scores[uri] = {
                "uri": uri,
                "rrf_score": rrf_score,
                "bm25_score": result.score,
                "bm25_rank": result.rank,
                "vector_score": 0.0,
                "vector_rank": None,
                "snippet": result.snippet,
                "metadata": result.metadata,
            }

        # Add vector contributions
        for result in vector_results:
            uri = result.uri
            rrf_score = vector_weight / (k + result.rank)

            if uri in scores:
                # URI appears in both: add vector contribution
                scores[uri]["rrf_score"] += rrf_score
                scores[uri]["vector_score"] = result.score
                scores[uri]["vector_rank"] = result.rank
            else:
                # URI only in vector results
                scores[uri] = {
                    "uri": uri,
                    "rrf_score": rrf_score,
                    "bm25_score": 0.0,
                    "bm25_rank": None,
                    "vector_score": result.score,
                    "vector_rank": result.rank,
                    "snippet": "",
                    "metadata": result.metadata,
                }

        # Sort by fused score
        sorted_results = sorted(
            scores.values(),
            key=lambda x: x["rrf_score"],
            reverse=True,
        )

        # Convert to HybridResult objects
        hybrid_results = []
        for rank, item in enumerate(sorted_results, start=1):
            result = HybridResult(
                uri=item["uri"],
                score=item["rrf_score"],
                rank=rank,
                snippet=item["snippet"],
                metadata=item["metadata"],
                score_breakdown={
                    "bm25_score": item["bm25_score"],
                    "bm25_rank": item["bm25_rank"],
                    "vector_score": item["vector_score"],
                    "vector_rank": item["vector_rank"],
                    "rrf_score": item["rrf_score"],
                }
            )
            hybrid_results.append(result)

        return hybrid_results

    def close(self):
        """Close search connections."""
        self.bm25_searcher.close()
        if self.vector_searcher:
            # Qdrant client doesn't need explicit close
            pass
