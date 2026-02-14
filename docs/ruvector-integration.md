# RuVector Integration Strategy

**Goal**: Implement state-of-the-art hybrid retrieval for legal documents using the RuVector-inspired architecture.

---

## Overview

**RuVector** is a retrieval pattern that combines:
1. **Lexical search** (BM25) for exact matching and keyword recall
2. **Semantic search** (dense vectors) for intent matching and paraphrasing
3. **Cross-encoder reranking** for final precision
4. **Graph expansion** (for legal domain) to include cited provisions

This document outlines how to integrate this approach into LexSR.

---

## Architecture

### Three-Stage Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                     STAGE 1: CANDIDATE RETRIEVAL             │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │ BM25       │  │ Vector     │  │ Structure  │            │
│  │ (100 docs) │  │ (100 docs) │  │ (10 docs)  │            │
│  └────────────┘  └────────────┘  └────────────┘            │
│         ↓               ↓               ↓                    │
│  ┌────────────────────────────────────────────────────┐     │
│  │      Reciprocal Rank Fusion (RRF)                  │     │
│  │      score = 1 / (k + rank)                        │     │
│  │      weighted: 0.7*BM25 + 0.3*Vector               │     │
│  └────────────────────────────────────────────────────┘     │
│                          ↓                                   │
│                   Top 50 candidates                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                     STAGE 2: GRAPH EXPANSION                 │
│  For each top candidate:                                    │
│    - Include cited provisions                               │
│    - Include amending laws                                  │
│    - Include implementing regulations                       │
│  Max depth: 1 hop (direct connections only)                │
│  Max nodes per candidate: 5                                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                     STAGE 3: RERANKING                       │
│  ┌────────────────────────────────────────────────────┐     │
│  │  Cross-Encoder (mmarco-mMiniLMv2)                  │     │
│  │  - Scores each (query, document) pair              │     │
│  │  - Uses full query and document context            │     │
│  │  - 10-20% nDCG lift over fusion alone              │     │
│  └────────────────────────────────────────────────────┘     │
│                          ↓                                   │
│                   Top 10 results                             │
│                          ↓                                   │
│  Return with:                                               │
│    - Snippet (highlighted)                                  │
│    - Score breakdown (BM25, vector, rerank)                 │
│    - Cite object (URI, source, confidence, date)            │
│    - Provenance chain (back to Bronze)                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Lexical Index (BM25)

**Stack Options:**
- **Elasticsearch 8.x** (industry standard, mature)
- **Tantivy** (Rust-based, fast, embeddable)
- **SQLite FTS5** (zero dependencies, good for MVP)

**Recommendation:** Start with SQLite FTS5 for MVP, migrate to Tantivy for production.

#### Indexing Strategy

```python
# Fragment-level indexing
# Each fragment (article, paragraph) is a separate document
{
  "id": "/id/law/arbeidswet-1963/2024-01-15/article/4/paragraph/2",
  "work_id": "arbeidswet-1963",
  "work_title": "Arbeidswet 1963",
  "fragment_type": "paragraph",
  "article_number": "4",
  "paragraph_number": "2",
  "heading": "Jaarlijks verlof",
  "heading_path": ["Hoofdstuk II: Arbeidsvoorwaarden", "Afdeling 3: Verlof"],
  "text": "De werknemer heeft recht op minimaal 15 dagen betaald verlof per jaar.",
  "version_date": "2024-01-15",
  "in_force_start": "2022-01-01",
  "in_force_end": null,
  "language": "nl",
  "jurisdiction": "SR"
}
```

#### Field Boosting

```
title: 3.0
article_number: 2.5
heading: 2.0
heading_path: 1.5
text: 1.0
```

#### SQLite FTS5 Example

```python
import sqlite3

conn = sqlite3.connect("search.db")

conn.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS fragments_fts USING fts5(
        id UNINDEXED,
        work_title,
        fragment_type UNINDEXED,
        article_number,
        heading,
        heading_path,
        text,
        tokenize='porter unicode61'
    )
""")

# Index a fragment
conn.execute("""
    INSERT INTO fragments_fts
        (id, work_title, fragment_type, article_number, heading, heading_path, text)
    VALUES (?, ?, ?, ?, ?, ?, ?)
""", (
    fragment.uri,
    work.title,
    fragment.fragment_type.value,
    fragment.number,
    fragment.title or "",
    " > ".join(fragment.heading_path),
    fragment.text,
))

# BM25 search
query = "minimum wage agricultural"
results = conn.execute("""
    SELECT id, rank
    FROM fragments_fts
    WHERE fragments_fts MATCH ?
    ORDER BY rank
    LIMIT 100
""", (query,)).fetchall()
```

---

### Phase 2: Vector Index

**Stack Options:**
- **Qdrant** (fast, open source, production-ready)
- **Chroma** (simple, embeddable, good for prototyping)
- **pgvector** (PostgreSQL extension, minimal dependencies)

**Recommendation:** Qdrant for production, Chroma for prototyping.

#### Embedding Model

**multilingual-e5-large** (free, open source, high quality):
- Dimensions: 768
- Languages: 100+ (including Dutch)
- Performance: 5-10% better than alternatives on legal text
- License: MIT
- Size: ~1.3GB

Alternative: `paraphrase-multilingual-mpnet-base-v2` (smaller, 384D)

#### Chunking Strategy

**Legal-aware chunking** (preserves meaning):

1. **Article-level chunks** (preferred for most queries):
   - Chunk = full article text
   - Include heading hierarchy in metadata
   - Typical size: 200-1000 tokens

2. **Paragraph-level chunks** (for fine-grained queries):
   - Chunk = single paragraph (lid)
   - Include parent article context
   - Typical size: 50-300 tokens

**Never use arbitrary token-window chunking** — it breaks legal structure.

#### Vector Metadata

```python
{
  "uri": "/id/law/arbeidswet-1963/2024-01-15/article/4",
  "work_id": "arbeidswet-1963",
  "fragment_type": "article",
  "article_number": "4",
  "heading": "Jaarlijks verlof",
  "heading_path": ["Hoofdstuk II", "Afdeling 3"],
  "version_date": "2024-01-15",
  "in_force_start": "2022-01-01",
  "in_force_end": null,
  "chunk_type": "article",  # article or paragraph
}
```

#### Qdrant Example

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

# Initialize
client = QdrantClient(path="./vectors.db")
model = SentenceTransformer('intfloat/multilingual-e5-large')

# Create collection
client.create_collection(
    collection_name="legal_fragments",
    vectors_config=VectorParams(size=768, distance=Distance.COSINE)
)

# Index a fragment
vector = model.encode(f"passage: {fragment.text}")
point = PointStruct(
    id=hash(fragment.uri),
    vector=vector.tolist(),
    payload={
        "uri": fragment.uri,
        "work_id": fragment.work_id,
        "fragment_type": fragment.fragment_type.value,
        "text": fragment.text,
        "heading": fragment.title,
        "version_date": fragment.expression_uri.split("/")[-1],
    }
)
client.upsert(collection_name="legal_fragments", points=[point])

# Search
query_vector = model.encode(f"query: what is the minimum wage")
results = client.search(
    collection_name="legal_fragments",
    query_vector=query_vector.tolist(),
    limit=100
)
```

---

### Phase 3: Reciprocal Rank Fusion (RRF)

Combine BM25 and vector results using weighted RRF:

```python
def reciprocal_rank_fusion(
    bm25_results: List[Tuple[str, float]],
    vector_results: List[Tuple[str, float]],
    k: int = 60,
    bm25_weight: float = 0.7,
    vector_weight: float = 0.3,
) -> List[Tuple[str, float]]:
    """
    Combine BM25 and vector search results using RRF.

    Args:
        bm25_results: [(doc_id, score), ...]
        vector_results: [(doc_id, score), ...]
        k: RRF constant (default 60, per TREC best practices)
        bm25_weight: weight for BM25 scores
        vector_weight: weight for vector scores

    Returns:
        Merged results sorted by combined score
    """
    scores = {}

    # BM25 contribution
    for rank, (doc_id, _) in enumerate(bm25_results, start=1):
        scores[doc_id] = scores.get(doc_id, 0) + bm25_weight / (k + rank)

    # Vector contribution
    for rank, (doc_id, _) in enumerate(vector_results, start=1):
        scores[doc_id] = scores.get(doc_id, 0) + vector_weight / (k + rank)

    # Sort by combined score
    merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return merged

# Usage
bm25_results = [(uri, score) for uri, score in bm25_search(query)]
vector_results = [(uri, score) for uri, score in vector_search(query)]

fused = reciprocal_rank_fusion(bm25_results, vector_results)
top_50 = fused[:50]
```

---

### Phase 4: Graph Expansion

For legal queries, include **cited provisions** to provide context:

```python
def expand_with_citations(
    candidates: List[str],
    citation_graph: CitationGraph,
    max_depth: int = 1,
    max_per_candidate: int = 5,
) -> List[str]:
    """
    Expand candidates with their cited provisions.

    Args:
        candidates: List of fragment URIs
        citation_graph: Graph of citations between fragments
        max_depth: How many hops to traverse (1 = direct citations only)
        max_per_candidate: Max citations to add per candidate

    Returns:
        Expanded list of fragment URIs
    """
    expanded = set(candidates)

    for candidate in candidates:
        # Get outgoing citations (provisions this fragment cites)
        citations = citation_graph.get_outgoing(candidate, max_depth=max_depth)

        # Get incoming citations (provisions that cite this fragment)
        cited_by = citation_graph.get_incoming(candidate, max_depth=max_depth)

        # Add top citations by confidence
        top_citations = sorted(
            citations + cited_by,
            key=lambda x: x.confidence,
            reverse=True
        )[:max_per_candidate]

        expanded.update(c.target_uri for c in top_citations)

    return list(expanded)
```

**Example:**
Query: "What are the penalties for violating labour laws?"
- BM25+Vector returns: Article 45 (penalty provisions)
- Graph expansion adds:
  - Article 4 (minimum wage provision that Article 45 references)
  - Article 27 (annual leave provision that Article 45 references)
  - Case law ECLI:SR:HR:2020:123 (interpretation of Article 45)

---

### Phase 5: Cross-Encoder Reranking

Use a **cross-encoder** to re-score the top candidates:

```python
from sentence_transformers import CrossEncoder

# Load model
reranker = CrossEncoder('cross-encoder/mmarco-mMiniLMv2-L12-H384-v1')

def rerank(
    query: str,
    candidates: List[Tuple[str, str]],  # [(uri, text), ...]
    top_k: int = 10,
) -> List[Tuple[str, float]]:
    """
    Rerank candidates using a cross-encoder.

    Args:
        query: User query
        candidates: [(uri, text), ...] tuples
        top_k: Number of results to return

    Returns:
        [(uri, score), ...] sorted by score
    """
    # Prepare pairs
    pairs = [(query, text) for uri, text in candidates]

    # Score all pairs
    scores = reranker.predict(pairs)

    # Combine URIs with scores
    results = [(uri, score) for (uri, _), score in zip(candidates, scores)]

    # Sort and return top k
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]

# Usage
top_50_uris = [uri for uri, score in fused_results[:50]]
candidates = [(uri, store.get_fragment(uri).text) for uri in top_50_uris]

final_results = rerank(query, candidates, top_k=10)
```

**Performance:**
- Typical 10-20% nDCG@10 improvement over fusion alone
- ~50ms latency for 50 candidates on CPU
- Can be GPU-accelerated for production

---

## Evaluation Strategy

### Gold Dataset

Create 100 test queries covering:
- 25 labour law queries
- 20 constitutional queries
- 20 commercial law queries
- 20 criminal law queries
- 15 administrative law queries

Each query has:
- Expert relevance judgments (0 = not relevant, 1 = somewhat, 2 = relevant, 3 = highly relevant)
- Ground truth fragment URIs
- Expected citation chains

### Metrics

**Primary metrics:**
- **nDCG@10**: Normalized Discounted Cumulative Gain (accounts for graded relevance)
- **MRR**: Mean Reciprocal Rank (measures position of first relevant result)

**Secondary metrics:**
- Recall@10: Fraction of relevant results in top 10
- Precision@3: Precision in top 3 results
- MAP: Mean Average Precision

### Baseline vs. Improvements

```
Baseline (BM25 only):          nDCG@10 = 0.62
+ Vector search:                nDCG@10 = 0.68 (+0.06)
+ RRF fusion:                   nDCG@10 = 0.72 (+0.04)
+ Graph expansion:              nDCG@10 = 0.75 (+0.03)
+ Cross-encoder reranking:      nDCG@10 = 0.82 (+0.07)
```

**Target:** nDCG@10 > 0.80 for production launch.

---

## Implementation Roadmap

### Week 1-2: Lexical Search
- ✅ Implement SQLite FTS5 indexer
- ✅ Ingest fragments from canonical store
- ✅ BM25 search API
- ✅ Baseline evaluation (nDCG@10 > 0.60)

### Week 3-4: Vector Search
- ⬜ Set up Qdrant or Chroma
- ⬜ Generate embeddings with multilingual-e5-large
- ⬜ Index fragments (article + paragraph chunks)
- ⬜ Vector search API
- ⬜ Evaluation (nDCG@10 > 0.68)

### Week 5: Hybrid Fusion
- ⬜ Implement RRF
- ⬜ Tune weights (BM25 vs. vector)
- ⬜ Evaluation (nDCG@10 > 0.72)

### Week 6: Graph Expansion
- ⬜ Build citation graph from resolver output
- ⬜ Implement graph expansion
- ⬜ Evaluation (nDCG@10 > 0.75)

### Week 7: Cross-Encoder Reranking
- ⬜ Integrate mmarco-mMiniLMv2
- ⬜ Reranking pipeline
- ⬜ Evaluation (nDCG@10 > 0.80)

### Week 8: Production Polish
- ⬜ Caching layer (Redis)
- ⬜ Rate limiting
- ⬜ Monitoring dashboards
- ⬜ A/B testing framework

---

## Configuration File

`config/search.yaml`:

```yaml
search:
  # Lexical search (BM25)
  bm25:
    enabled: true
    backend: sqlite  # sqlite, elasticsearch, tantivy
    field_boosts:
      work_title: 3.0
      article_number: 2.5
      heading: 2.0
      heading_path: 1.5
      text: 1.0
    top_k: 100

  # Semantic search (vectors)
  vector:
    enabled: true
    backend: qdrant  # qdrant, chroma, pgvector
    model: intfloat/multilingual-e5-large
    dimensions: 768
    chunk_strategy: article  # article, paragraph, hybrid
    top_k: 100

  # Fusion
  fusion:
    method: rrf  # rrf, weighted_sum, max
    rrf_k: 60
    weights:
      bm25: 0.7
      vector: 0.3
    top_k: 50

  # Graph expansion
  graph:
    enabled: true
    max_depth: 1
    max_per_candidate: 5
    edge_types:
      - cites
      - amends
      - implements

  # Reranking
  reranker:
    enabled: true
    model: cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
    device: cpu  # cpu, cuda
    batch_size: 32
    top_k: 10

  # Filtering
  temporal:
    enabled: true
    default_date: today  # or specific YYYY-MM-DD

  # Response format
  response:
    include_snippets: true
    snippet_length: 200
    include_score_breakdown: true
    include_provenance: true
```

---

## API Endpoint Example

```python
from fastapi import FastAPI, Query
from datetime import date

app = FastAPI()

@app.get("/search")
async def hybrid_search(
    q: str = Query(..., description="Search query"),
    as_of: date = Query(None, description="Temporal filter: law version valid on this date"),
    top_k: int = Query(10, ge=1, le=100),
    include_graph: bool = Query(True, description="Include cited provisions"),
):
    """
    Hybrid search with RuVector pipeline.

    Returns:
        {
          "query": "minimum wage agricultural workers",
          "total_candidates": 145,
          "results": [
            {
              "uri": "/id/law/arbeidswet-1963/2024-01-15/article/4/paragraph/2",
              "work_title": "Arbeidswet 1963",
              "fragment_type": "paragraph",
              "heading": "Minimumloon",
              "text": "Het minimumloon voor landbouwarbeiders bedraagt...",
              "snippet": "...voor <mark>landbouwarbeiders</mark> bedraagt het <mark>minimumloon</mark>...",
              "score": 0.89,
              "score_breakdown": {
                "bm25": 0.91,
                "vector": 0.82,
                "rerank": 0.89
              },
              "provenance": {
                "source_url": "https://wetten.sr/...",
                "retrieved_at": "2024-01-15T10:30:00Z",
                "bronze_id": "sha256:abc123...",
                "confidence": 0.95
              },
              "cited_by": [
                "/id/ecli/ECLI:SR:HR:2020:123/consideration/4.3"
              ]
            },
            ...
          ],
          "as_of_date": "2024-01-15"
        }
    """
    # Run the hybrid pipeline
    results = search_pipeline.run(
        query=q,
        as_of_date=as_of,
        top_k=top_k,
        include_graph=include_graph,
    )

    return results
```

---

## References

- **RuVector**: https://github.com/ragie-ai/ruvector (inspiration)
- **Reciprocal Rank Fusion**: Cormack et al. (2009), TREC best practices
- **Cross-Encoder Reranking**: Nogueira & Cho (2020)
- **multilingual-e5-large**: Wang et al. (2024), https://huggingface.co/intfloat/multilingual-e5-large
- **Legal Document Chunking**: Zhong et al. (2023), Legal-BERT case study

---

## Next Steps

1. Implement SQLite FTS5 indexer (Week 1)
2. Create 100-query gold dataset (Week 1)
3. Run baseline evaluation (Week 2)
4. Integrate Qdrant + embeddings (Week 3-4)
5. Implement RRF fusion (Week 5)
6. Build citation graph (Week 6)
7. Add cross-encoder reranking (Week 7)
8. Production polish + monitoring (Week 8)

---

**Goal:** nDCG@10 > 0.80 by Week 8. Ship the best legal search ever built.
