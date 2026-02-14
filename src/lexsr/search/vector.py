"""
Vector search using dense embeddings.

Uses multilingual-e5-large (768D) for semantic similarity.
Backend: Qdrant (local mode) or Chroma (lightweight alternative).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.models import Fragment

logger = logging.getLogger(__name__)


@dataclass
class VectorResult:
    """A single vector search result."""
    uri: str
    score: float
    rank: int
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class VectorIndexer:
    """
    Index fragments as dense vectors for semantic search.

    Uses sentence-transformers with multilingual-e5-large (768D).
    Stores in Qdrant (local mode) for fast similarity search.
    """

    def __init__(
        self,
        collection_name: str = "legal_fragments",
        model_name: str = "intfloat/multilingual-e5-large",
        storage_path: str = "data/vectors.db",
    ):
        self.collection_name = collection_name
        self.model_name = model_name
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Lazy imports (only load if vector search is used)
        try:
            from sentence_transformers import SentenceTransformer
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams, PointStruct

            self._st = SentenceTransformer
            self._qc = QdrantClient
            self._dist = Distance
            self._vp = VectorParams
            self._ps = PointStruct

        except ImportError:
            raise ImportError(
                "Vector search requires sentence-transformers and qdrant-client. "
                "Install with: pip install sentence-transformers qdrant-client"
            )

        # Initialize model and client
        logger.info(f"Loading embedding model: {model_name}")
        self.model = self._st(model_name)
        self.dim = self.model.get_sentence_embedding_dimension()

        logger.info(f"Initializing Qdrant at {storage_path}")
        self.client = self._qc(path=str(self.storage_path))

        # Create collection if it doesn't exist
        self._ensure_collection()

    def _ensure_collection(self):
        """Create collection if it doesn't exist."""
        collections = self.client.get_collections().collections
        if not any(c.name == self.collection_name for c in collections):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=self._vp(size=self.dim, distance=self._dist.COSINE)
            )
            logger.info(f"Created collection: {self.collection_name}")

    def _uri_to_id(self, uri: str) -> str:
        """Convert URI to a stable integer ID for Qdrant."""
        return hashlib.sha256(uri.encode()).hexdigest()[:16]

    def index_fragment(self, fragment: Fragment, metadata: Dict[str, Any]) -> None:
        """
        Index a single fragment.

        Args:
            fragment: Fragment to index
            metadata: Additional metadata (work_title, version_date, etc.)
        """
        # Prepare text for embedding
        # For multilingual-e5, prefix with "passage: "
        text_parts = []

        if fragment.title:
            text_parts.append(fragment.title)

        text_parts.append(fragment.text)

        full_text = " ".join(text_parts)
        embedding_text = f"passage: {full_text}"

        # Generate embedding
        vector = self.model.encode(embedding_text).tolist()

        # Prepare payload
        payload = {
            "uri": fragment.uri,
            "work_id": fragment.work_id,
            "expression_id": fragment.expression_id,
            "fragment_type": fragment.fragment_type.value,
            "article_number": fragment.number or "",
            "heading": fragment.title or "",
            "heading_path": fragment.heading_path or [],
            "text_preview": fragment.text[:200],
            "version_date": metadata.get("version_date"),
            "work_title": metadata.get("work_title", ""),
            "in_force_start": metadata.get("in_force_start"),
            "in_force_end": metadata.get("in_force_end"),
            "language": metadata.get("language", "nl"),
            "jurisdiction": metadata.get("jurisdiction", "SR"),
        }

        # Create point
        point = self._ps(
            id=self._uri_to_id(fragment.uri),
            vector=vector,
            payload=payload,
        )

        # Upsert to collection
        self.client.upsert(
            collection_name=self.collection_name,
            points=[point],
        )

    def index_fragments(self, fragments: List[tuple[Fragment, Dict[str, Any]]]) -> int:
        """
        Batch index multiple fragments.

        Args:
            fragments: List of (fragment, metadata) tuples

        Returns:
            Number of fragments indexed
        """
        points = []

        for fragment, metadata in fragments:
            # Prepare text
            text_parts = []
            if fragment.title:
                text_parts.append(fragment.title)
            text_parts.append(fragment.text)
            full_text = " ".join(text_parts)
            embedding_text = f"passage: {full_text}"

            # Generate embedding
            vector = self.model.encode(embedding_text).tolist()

            # Prepare payload
            payload = {
                "uri": fragment.uri,
                "work_id": fragment.work_id,
                "expression_id": fragment.expression_id,
                "fragment_type": fragment.fragment_type.value,
                "article_number": fragment.number or "",
                "heading": fragment.title or "",
                "heading_path": fragment.heading_path or [],
                "text_preview": fragment.text[:200],
                "version_date": metadata.get("version_date"),
                "work_title": metadata.get("work_title", ""),
                "in_force_start": metadata.get("in_force_start"),
                "in_force_end": metadata.get("in_force_end"),
                "language": metadata.get("language", "nl"),
                "jurisdiction": metadata.get("jurisdiction", "SR"),
            }

            point = self._ps(
                id=self._uri_to_id(fragment.uri),
                vector=vector,
                payload=payload,
            )
            points.append(point)

        # Batch upsert
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )

        logger.info(f"Indexed {len(points)} fragments in vector store")
        return len(points)

    def delete_fragment(self, uri: str) -> bool:
        """Delete a fragment from the index."""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=[self._uri_to_id(uri)],
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete {uri}: {e}")
            return False

    def count(self) -> int:
        """Return the total number of indexed fragments."""
        info = self.client.get_collection(self.collection_name)
        return info.points_count


class VectorSearcher:
    """
    Search indexed fragments using vector similarity.

    Uses cosine similarity on multilingual-e5-large embeddings.
    """

    def __init__(
        self,
        collection_name: str = "legal_fragments",
        model_name: str = "intfloat/multilingual-e5-large",
        storage_path: str = "data/vectors.db",
    ):
        self.collection_name = collection_name
        self.storage_path = Path(storage_path)

        if not self.storage_path.exists():
            raise FileNotFoundError(f"Vector index not found: {storage_path}")

        # Lazy imports
        try:
            from sentence_transformers import SentenceTransformer
            from qdrant_client import QdrantClient

            self._st = SentenceTransformer
            self._qc = QdrantClient

        except ImportError:
            raise ImportError(
                "Vector search requires sentence-transformers and qdrant-client. "
                "Install with: pip install sentence-transformers qdrant-client"
            )

        # Initialize
        logger.info(f"Loading embedding model: {model_name}")
        self.model = self._st(model_name)

        logger.info(f"Connecting to Qdrant at {storage_path}")
        self.client = self._qc(path=str(self.storage_path))

    def search(
        self,
        query: str,
        limit: int = 100,
        as_of_date: Optional[str] = None,
        work_id: Optional[str] = None,
    ) -> List[VectorResult]:
        """
        Search for fragments using vector similarity.

        Args:
            query: Search query
            limit: Maximum results to return
            as_of_date: Optional temporal filter (YYYY-MM-DD)
            work_id: Optional filter by work ID

        Returns:
            List of VectorResult objects sorted by similarity
        """
        # Encode query with "query: " prefix for multilingual-e5
        query_vector = self.model.encode(f"query: {query}").tolist()

        # Build filter conditions
        filter_conditions = []

        if as_of_date:
            filter_conditions.append({
                "key": "in_force_start",
                "match": {"any": [None, {"lte": as_of_date}]},
            })
            filter_conditions.append({
                "key": "in_force_end",
                "match": {"any": [None, {"gt": as_of_date}]},
            })

        if work_id:
            filter_conditions.append({
                "key": "work_id",
                "match": {"value": work_id},
            })

        # Search
        search_result = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter={"must": filter_conditions} if filter_conditions else None,
        )

        # Convert to results
        results = []
        for rank, hit in enumerate(search_result, start=1):
            result = VectorResult(
                uri=hit.payload["uri"],
                score=hit.score,
                rank=rank,
                metadata={
                    "work_title": hit.payload.get("work_title", ""),
                    "article_number": hit.payload.get("article_number", ""),
                    "heading": hit.payload.get("heading", ""),
                    "text_preview": hit.payload.get("text_preview", ""),
                    "version_date": hit.payload.get("version_date"),
                }
            )
            results.append(result)

        logger.info(f"Vector search for '{query}' returned {len(results)} results")
        return results
