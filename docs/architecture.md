# LexSR Architecture

**Complete system design for the Suriname Legal Knowledge Fabric.**

---

## System Overview

LexSR is built as a **three-layer knowledge fabric** with clear separation of concerns:

1. **Bronze Layer**: Immutable raw storage (never lose the original)
2. **Silver Layer**: Canonical structured data (FRBR model with stable URIs)
3. **Gold Layer**: Knowledge products (search indexes, citation graph, entity graph)

Every layer is **measurable**, **reproducible**, and **traceable** back to official sources.

---

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   REST API   │  │  Static Site │  │  Python SDK (PyPI)   │  │
│  │  (FastAPI)   │  │ (GitHub Pgs) │  │  import lexsr        │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                         SERVICE LAYER                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   Search     │  │   Citation   │  │    Versioning        │  │
│  │   Service    │  │   Resolver   │  │    Service           │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                          GOLD LAYER                              │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────────┐  │
│  │ Search Indexes │  │ Citation Graph │  │ Knowledge Graph  │  │
│  │ BM25 + Vector  │  │  (NetworkX)    │  │ (entities, rels) │  │
│  │ (Qdrant + FTS) │  └────────────────┘  └──────────────────┘  │
│  └────────────────┘                                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                         SILVER LAYER                             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │             Canonical Store (SQLite)                     │   │
│  │  ┌──────┐  ┌────────────┐  ┌──────────────┐  ┌────────┐ │   │
│  │  │ Work │  │ Expression │  │Manifestation │  │Fragment│ │   │
│  │  └──────┘  └────────────┘  └──────────────┘  └────────┘ │   │
│  │                                                            │   │
│  │  - Stable URIs (ELI-style)                               │   │
│  │  - Temporal versioning (point-in-time queries)           │   │
│  │  - Full provenance (source URL, checksum, timestamp)     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                         BRONZE LAYER                             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         Immutable Raw Storage (SQLite + files)           │   │
│  │                                                            │   │
│  │  - PDFs (scanned + digital)                              │   │
│  │  - HTML (web scrapers)                                   │   │
│  │  - XML (SRU endpoints, Akoma Ntoso)                      │   │
│  │  - JSON (API responses)                                  │   │
│  │                                                            │   │
│  │  Each record: SHA-256 checksum + timestamp + HTTP headers│   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                       INGESTION LAYER                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   Scrapers   │  │  OCR Engine  │  │  Structure Extractor │  │
│  │  (wetten.sr) │  │  (Qwen2.5-VL)  │  │  (Akoma Ntoso)       │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Ingestion Pipeline (Bronze → Silver)

```
1. SCRAPER
   ↓
   Fetch raw document (PDF, HTML, XML)
   ↓
2. BRONZE STORE
   ↓
   Store immutable bytes with checksum + metadata
   ↓
3. OCR (if PDF)
   ↓
   Extract text using Qwen2.5-VL/Tesseract
   ↓
4. STRUCTURE EXTRACTION
   ↓
   Parse into FRBR model:
     - Identify Work, Expression, Manifestation
     - Extract Fragments (articles, paragraphs, etc.)
     - Create fragment anchors (structural paths + text hashes)
   ↓
5. CANONICAL STORE (Silver)
   ↓
   Persist Work, Expression, Fragments with URIs
   ↓
6. CITATION RESOLVER
   ↓
   Extract references from text
   Resolve to canonical URIs
   Build citation graph
   ↓
7. GOLD LAYER INDEXING
   ↓
   Index in search (BM25 + vectors)
   Build knowledge graph
   Create amendment chains
```

### Query Pipeline (Search → Response)

```
1. USER QUERY
   ↓
   "What is the minimum wage for agricultural workers?"
   ↓
2. SEARCH SERVICE
   ↓
   a. BM25 search → 100 candidates
   b. Vector search → 100 candidates
   c. Reciprocal Rank Fusion → 50 candidates
   d. Graph expansion → include cited provisions
   e. Cross-encoder rerank → 10 results
   ↓
3. CANONICAL STORE
   ↓
   Fetch full Fragment objects for top 10 URIs
   ↓
4. TEMPORAL FILTER (optional)
   ↓
   Apply "as_of_date" filter
   Return version valid on query date
   ↓
5. RESPONSE
   ↓
   Return results with:
     - Fragment text + snippet
     - URI + provenance
     - Score breakdown
     - Cited provisions
     - Amendment history
```

---

## Module Design

### Core Modules (`src/lexsr/core/`)

#### `models.py` (~400 LOC)
- FRBR data classes: Work, Expression, Manifestation, Fragment
- Enums: DocumentStatus, SourceType, FragmentType, etc.
- TemporalExtent, FragmentAnchor
- Full type safety with dataclasses

#### `identifiers.py` (~624 LOC)
- LegalURI, URIScheme, FragmentPath
- ELI-style URI builder/parser
- Abbreviation registry (law name → official ID)
- Validation for ECLI, CELEX patterns

#### `versioning.py` (~268 LOC)
- VersionChain: ordered list of Expressions for a Work
- TemporalIndex: fast lookup across all Works
- VersionDiff: tracks what changed between versions
- Point-in-time queries: "expression valid on date X"

#### `resolver.py` (~1,260 LOC)
- ReferenceParser: multi-pass extraction
- CitationResolver: resolve to canonical URIs
- Contextual disambiguation
- Unresolved reference queue (SQLite)

#### `store.py` (~800+ LOC)
- CanonicalStore: SQLite-backed persistence
- CRUD for Work, Expression, Manifestation, Fragment
- URI-based lookups
- Temporal queries

#### `integrity.py`
- Link integrity checks
- Broken target detection
- Duplicate fragment merging
- Data quality metrics

#### `jurisdiction.py`
- Jurisdiction-specific configuration
- Official ID patterns
- Abbreviation registries per country

---

### Ingestion Modules (`src/lexsr/ingestion/`)

#### `bronze.py` (~200 LOC)
- BronzeStore: immutable raw storage
- Deduplication by SHA-256 checksum
- HTTP metadata preservation

#### `pipeline.py`
- Orchestrates Bronze → Silver transformation
- Handles OCR, structure extraction, canonicalization

#### `silver.py`
- Silver layer pipeline logic
- Document normalization
- Fragment extraction

#### `scrapers/` (`src/lexsr/ingestion/scrapers/`)
- `dna.py`: Scraper for DNA (parliament)
- `belastingdienst.py`: Scraper for the Tax Authority
- `mas.py`, `sris.py`: Ministry / legal-database scrapers
- `generic.py`: Configurable fallback scraper (used for SSB and other sources)

#### `batch_processor.py`
- Orchestrates Bronze → OCR → Canonical → search indexing for a scraper or a directory of PDFs
- Used by `lexsr ingest` and `lexsr ingest-pdfs`

---

### OCR Modules (`src/lexsr/ocr/`)

#### `extractor.py`
- `PDFExtractor`: digital-text extraction with OCR fallback
- Tesseract (and optional Qwen2.5-VL) engines behind a common `OCREngine` interface

#### `detector.py`
- Structure detection: articles, paragraphs, headings from raw OCR text

#### `citation_extractor.py`
- Multi-pass citation extraction from OCR'd fragments (used by `lexsr link-citations`)

#### `pipeline.py`
- `OCRPipeline`: PDF → OCR → structure detection → FRBR models → citation extraction, end to end

---

### Consolidation Modules (`src/lexsr/consolidation/`)

Two-pass (regex + optional LLM) pipeline that turns wijzigingswetten into
applied amendments against their base law. Used by `lexsr consolidate`.

#### `classifier.py`
- `DocumentClassifier`: regex scoring, with an LLM fallback pass for ambiguous documents
- Classifies base_law / amendment / decree / case_law / regulation / unknown

#### `parser.py`
- `AmendmentParser`: extracts `AmendmentInstruction`s (replace/insert/repeal/modify) from amendment text
- LLM pass merges in instructions the regex pass missed or scored low-confidence

#### `llm_client.py`
- Shared `call_llm()` helper for the classifier/parser LLM fallback
- Supports both a local vLLM completions endpoint and OpenAI-compatible chat
  endpoints (e.g. OpenRouter), selected by URL shape
- API key resolved from an explicit arg, `OPENROUTER_API_KEY`, or a repo-root `.env`

#### `engine.py`
- `ConsolidationEngine`: applies parsed instructions to the base law's latest
  expression, creates a new versioned expression, and records `AmendmentLink`s

#### `amendment.py`
- Shared dataclasses: `AmendmentInstruction`, `OperationType`, `ParsedAmendment`

---

### Search Modules (`src/lexsr/search/`)

#### `bm25.py`
- SQLite FTS5 or Tantivy integration
- Field boosting configuration
- Article-level and paragraph-level indexing

#### `vector.py`
- Qdrant or Chroma integration
- multilingual-e5-large embeddings
- Legal-aware chunking

#### `hybrid.py`
- Reciprocal Rank Fusion (RRF)
- Weighted score merging
- Candidate filtering

#### `reranker.py`
- Cross-encoder reranking
- mmarco-mMiniLMv2 integration
- Batch processing

#### `graph_expansion.py`
- Citation graph traversal
- Amendment chain inclusion
- Confidence-based filtering

---

### Graph Modules (`src/lexsr/graph/`) (planned)

#### `citation_graph.py`
- Build citation graph from resolver output
- NetworkX or graph database backend
- Node: Fragment URI
- Edge: CITES, AMENDS, IMPLEMENTS, etc.

#### `entity_graph.py`
- Entity extraction (courts, organizations, persons)
- Concept linking (controlled vocabulary)
- Knowledge graph builder

#### `amendment_chains.py`
- Extract amendment relationships
- Build version lineage
- Detect repealed provisions

---

### CLI (`src/lexsr/__main__.py`)

There is no REST API server in the current implementation; the `lexsr`
console script (also runnable as `python -m lexsr`) is the primary
interface for running the pipeline and serving the output:

- `stats` — database statistics (works, fragments, citations, amendment links)
- `ingest` — scrape all live sources and ingest into the canonical store
- `ingest-pdfs` — process PDFs already in `data/raw/`
- `consolidate` — classify, parse, and apply amendments to base laws
- `link-citations` — backfill citation links for all fragments
- `index` / `index-vectors` — build the BM25 / dense-vector search indexes
- `generate` — build the static site
- `serve` — serve the generated site locally
- `search <query>` — query the knowledge base (BM25 or hybrid)
- `benchmark` — run the citation-resolution benchmark suite

A prior prototype exposed this functionality via a FastAPI REST layer
(`src/lexsr/api/`) with Pydantic schemas and an active-learning /
quality-dashboard module (`src/lexsr/improvement/`); both were removed
in favor of the CLI + static site approach above. Re-introducing a REST
API (e.g. for a hosted search UI) remains a reasonable future direction,
but should be scoped fresh against the current data model rather than
resurrecting the old code.

---

### Evaluation Modules (`src/lexsr/evaluation/`)

#### `metrics.py`
- nDCG, MRR, MAP, Recall, Precision
- Citation quality metrics
- Temporal accuracy metrics

#### `benchmark.py`
- Gold dataset loader
- Automated evaluation runner
- Regression test framework

#### `dataset.py`
- Known-answer seed dataset (`KnownAnswerDataset.suriname_legal_seed()`)
- Ground truth fragment URIs, organized by category (citation, temporal, ...)

#### `structure.py`
- Structure-quality metrics for OCR output (article/paragraph detection accuracy)

---

## Storage Design

### SQLite Databases

**Why SQLite?**
- Single-file deployment
- No server needed
- ACID transactions
- Built-in full-text search (FTS5)
- Easy backups (just copy the file)
- Great for up to ~100GB of data

**Databases:**

1. **`canonical.db`** (Silver Layer)
   - Tables: works, expressions, manifestations, fragments, version_diffs
   - Indexes: URI, official_id, version_date
   - WAL mode for concurrent reads

2. **`bronze.db`** (Bronze Layer)
   - Tables: bronze_records
   - Indexes: checksum_sha256, source_url, source_type
   - Stores raw bytes in BLOB columns

3. **`search.db`** (Gold Layer - optional, can use Qdrant instead)
   - Tables: fragments_fts (FTS5 virtual table)
   - BM25 lexical search

4. **`unresolved.db`** (Resolver queue)
   - Tables: unresolved_references
   - Tracks references that couldn't be resolved

5. **`vectors.db`** (Gold Layer - if using Qdrant's local mode)
   - Managed by Qdrant
   - Vector embeddings + metadata

### File Storage (optional for large PDFs)

```
data/
  bronze/
    sha256/
      ab/
        abcdef123...  (raw PDF bytes)
  manifestations/
    xml/
      arbeidswet-1963-2024-01-15.xml
    html/
      arbeidswet-1963-2024-01-15.html
```

---

## Scalability Considerations

### Current Design (SQLite)

**Good for:**
- Up to 1M fragments (~10k works)
- Read-heavy workloads with WAL mode
- Single-server deployments
- Development and prototyping

**Limits:**
- Concurrent writes bottleneck
- No horizontal scaling

### Migration Path (if needed)

**When to migrate:**
- >100GB canonical data
- >10k concurrent users
- Global distribution requirements

**PostgreSQL + Distributed Search:**
```
Canonical store:  PostgreSQL (pgvector for embeddings)
Search:           Elasticsearch cluster or Qdrant Cloud
Cache:            Redis
Load balancer:    nginx
```

---

## Deployment Architectures

### Option 1: Single Server (MVP)

```
┌─────────────────────────────────────┐
│         Ubuntu 22.04 VPS            │
│                                     │
│  ┌──────────────────────────────┐  │
│  │   FastAPI (uvicorn)          │  │
│  │   Port 8000                  │  │
│  └──────────────────────────────┘  │
│                ↓                    │
│  ┌──────────────────────────────┐  │
│  │   SQLite databases           │  │
│  │   - canonical.db             │  │
│  │   - bronze.db                │  │
│  │   - search.db                │  │
│  └──────────────────────────────┘  │
│                ↓                    │
│  ┌──────────────────────────────┐  │
│  │   Qdrant (local)             │  │
│  │   vectors.db                 │  │
│  └──────────────────────────────┘  │
│                                     │
│  nginx (reverse proxy)              │
│  Port 80/443 → 8000                 │
└─────────────────────────────────────┘

Cost: $20-50/month (Hetzner, Linode, DigitalOcean)
```

### Option 2: Cloud Managed (Production)

```
┌─────────────────────────────────────────────┐
│              AWS / GCP / Azure              │
│                                             │
│  CloudFront / CloudFlare CDN               │
│             ↓                               │
│  ┌────────────────────────────────────┐    │
│  │   API Gateway / Load Balancer      │    │
│  └────────────────────────────────────┘    │
│             ↓                               │
│  ┌────────────────────────────────────┐    │
│  │   ECS Fargate (FastAPI containers) │    │
│  │   Auto-scaling 2-10 instances      │    │
│  └────────────────────────────────────┘    │
│             ↓                               │
│  ┌──────────────┐  ┌──────────────────┐    │
│  │  RDS         │  │ Elasticsearch    │    │
│  │  PostgreSQL  │  │ Service          │    │
│  └──────────────┘  └──────────────────┘    │
│             ↓                               │
│  ┌──────────────┐  ┌──────────────────┐    │
│  │ S3           │  │ Qdrant Cloud     │    │
│  │ (Bronze PDFs)│  │ (Vectors)        │    │
│  └──────────────┘  └──────────────────┘    │
│                                             │
│  Redis ElastiCache (caching)               │
└─────────────────────────────────────────────┘

Cost: $500-2000/month (depending on scale)
```

### Option 3: University Partnership (Free)

```
┌─────────────────────────────────────────────┐
│      Anton de Kom University IT             │
│                                             │
│  University web server                      │
│  Faculty resources                          │
│  PhD student maintenance                    │
│                                             │
│  Cost: $0 (covered by university budget)    │
└─────────────────────────────────────────────┘
```

---

## Security & Privacy

### Data Security

- All PDFs scanned for malware before storage
- Content Security Policy headers
- Rate limiting (per IP and per API key)
- CORS configuration for allowed origins

### Privacy (for case law with PII)

- Pseudonymization of personal names
- Redaction of sensitive information
- Compliance with data protection regulations

### Authentication (optional)

- Public tier: No auth required
- Premium tier: API keys for rate limits
- Admin tier: OAuth2 for management endpoints

---

## Monitoring & Observability

### Metrics (Prometheus)

```python
# Search quality
search_requests_total
search_latency_seconds
search_ndcg_score

# Citation resolution
citations_resolved_total
citations_unresolved_total
resolver_confidence_histogram

# Ingestion
documents_ingested_total
ocr_accuracy_score
bronze_storage_bytes

# System health
api_requests_total
api_errors_total
database_size_bytes
```

### Dashboards (Grafana)

1. **Search Quality**:
   - nDCG@10 over time
   - Latency percentiles (p50, p95, p99)
   - Top queries by volume

2. **Data Quality**:
   - OCR confidence distribution
   - Citation resolution rate
   - Unresolved reference queue size

3. **System Health**:
   - Request rate
   - Error rate
   - Database size growth

### Alerting

- nDCG@10 drops below 0.75 → Slack alert
- API error rate >5% → PagerDuty
- Unresolved queue >1000 → Email to reviewers

---

## Development Workflow

### Local Development

```bash
# Clone repo
git clone https://github.com/your-org/wetten-van-suriname.git
cd wetten-van-suriname

# Install dependencies
pip install -e ".[dev,all]"

# Run tests
pytest tests/ -v

# Run API locally
uvicorn lexsr.api.app:app --reload

# Generate sample data
python scripts/generate_sample_data.py

# Run search experiments
python scripts/evaluate_search.py
```

### CI/CD Pipeline

```yaml
# .github/workflows/ci.yml
on: [push, pull_request]

jobs:
  test:
    - Run pytest
    - Run ruff (linting)
    - Check code coverage (>80%)

  evaluate:
    - Run search evaluation
    - Compare nDCG@10 to baseline
    - Fail if quality regresses

  build:
    - Build Docker image
    - Push to registry

  deploy:
    - Deploy to staging (on main branch)
    - Run smoke tests
    - Deploy to production (on release tag)
```

---

## Performance Targets

### Latency

- `/provision/{uri}`: <50ms (p99)
- `/search`: <500ms (p99) without reranking, <1s with reranking
- `/versions/{work_id}`: <100ms (p99)

### Throughput

- API: 1000 requests/second (single server)
- Ingestion: 100 documents/hour

### Quality

- nDCG@10: >0.80
- MRR: >0.85
- OCR accuracy: >95%
- Citation resolution: >90%

---

## Future Enhancements

### Phase 1 (Months 1-3)
- ✅ Core FRBR model
- ✅ URI system
- ✅ Versioning
- ✅ Citation resolver
- ⬜ OCR pipeline
- ⬜ Web scrapers

### Phase 2 (Months 4-6)
- ⬜ Hybrid search (BM25 + vector)
- ⬜ Citation graph
- ⬜ GraphRAG retrieval
- ⬜ Static site generator

### Phase 3 (Months 7-9)
- ⬜ Knowledge graph (entities + concepts)
- ⬜ Answer synthesis with citations
- ⬜ Faithfulness checks
- ⬜ Multilingual support (English)

### Phase 4 (Months 10-12)
- ⬜ SPARQL endpoint
- ⬜ JSON-LD exports
- ⬜ Community contribution workflows
- ⬜ Production hardening

---

## References

- **FRBR**: https://www.ifla.org/publications/functional-requirements-for-bibliographic-records/
- **Akoma Ntoso**: https://www.oasis-open.org/standard/akn-v1-0/
- **ELI**: https://en.wikipedia.org/wiki/European_Legislation_Identifier
- **UK legislation.gov.uk**: https://www.legislation.gov.uk/developer
- **RuVector**: https://ragie.ai/blog/hybrid-search-ruvector
- **FastAPI**: https://fastapi.tiangolo.com/

---

**Next**: See [ruvector-integration.md](ruvector-integration.md) for hybrid search implementation.
