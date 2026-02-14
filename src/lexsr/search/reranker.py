"""
Cross-encoder reranking for final precision boost.

Uses cross-encoder models to re-score (query, document) pairs.
Typical improvement: 10-20% nDCG@10 lift over fusion alone.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """A reranked search result."""
    uri: str
    score: float
    rank: int
    original_rank: int
    original_score: float


class CrossEncoderReranker:
    """
    Rerank search results using a cross-encoder model.

    Model: cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
    - Multilingual (supports Dutch)
    - Lightweight (384D hidden size)
    - Trained on MS MARCO passage ranking

    Typical usage:
        reranker = CrossEncoderReranker()
        candidates = [(uri, text), ...]
        reranked = reranker.rerank(query, candidates, top_k=10)
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        device: str = "cpu",
        batch_size: int = 32,
    ):
        """
        Initialize cross-encoder reranker.

        Args:
            model_name: HuggingFace model name
            device: "cpu" or "cuda"
            batch_size: Batch size for inference
        """
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size

        try:
            from sentence_transformers import CrossEncoder

            self._ce = CrossEncoder

        except ImportError:
            raise ImportError(
                "Reranking requires sentence-transformers. "
                "Install with: pip install sentence-transformers"
            )

        logger.info(f"Loading cross-encoder: {model_name}")
        self.model = self._ce(model_name, device=device, max_length=512)

    def rerank(
        self,
        query: str,
        candidates: List[Tuple[str, str]],
        top_k: int = 10,
    ) -> List[RerankResult]:
        """
        Rerank candidates using cross-encoder scoring.

        Args:
            query: Search query
            candidates: List of (uri, text) tuples
            top_k: Number of results to return

        Returns:
            List of RerankResult sorted by cross-encoder score
        """
        if not candidates:
            return []

        # Prepare pairs for cross-encoder
        pairs = [(query, text) for uri, text in candidates]

        # Score all pairs
        logger.info(f"Reranking {len(candidates)} candidates...")
        scores = self.model.predict(pairs, batch_size=self.batch_size)

        # Combine URIs with scores
        results_with_scores = [
            (uri, score, idx)
            for idx, ((uri, _), score) in enumerate(zip(candidates, scores))
        ]

        # Sort by cross-encoder score
        results_with_scores.sort(key=lambda x: x[1], reverse=True)

        # Take top K and create RerankResult objects
        reranked = []
        for new_rank, (uri, score, original_idx) in enumerate(
            results_with_scores[:top_k], start=1
        ):
            result = RerankResult(
                uri=uri,
                score=float(score),
                rank=new_rank,
                original_rank=original_idx + 1,
                original_score=float(scores[original_idx]),
            )
            reranked.append(result)

        logger.info(f"Reranking complete. Returning top {len(reranked)} results")
        return reranked
