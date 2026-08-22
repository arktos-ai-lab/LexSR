# LexSR - Suriname Legal Knowledge Fabric

**The best legal database ever built from the ground up.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> A three-layer legal knowledge fabric for Suriname that **never loses the original**, provides **stable identifiers everywhere**, supports **temporal versioning**, treats **links as first-class data**, and enables **evaluation from day 1**.

---

## 🎯 The North Star: A "Legal Knowledge Fabric"

Your "best database ever" is not one thing. It is a **stack** where every layer is measurable, reproducible, and traceable back to official sources.

### Non-Negotiables

1. **Never lose the original**: Store raw payloads (XML, HTML, PDFs) immutable. Every derived text, chunk, triple, and embedding points back to raw bytes + retrieval timestamp + source URL.
2. **Stable identifiers everywhere**: Every document, version, and fragment (article, paragraph, r.o., consideration) has a stable ID and canonical URI.
3. **Versioning + time travel**: Represent "what was valid on date X" for legislation and "what text was published on date Y" for everything.
4. **Links are first-class data**: Citations, amendments, implementations, referrals, and sameAs mappings are as important as text.
5. **Evaluation from day 1**: Retrieval quality, link quality, and answer faithfulness get automated tests and dashboards.

---

## 📚 Table of Contents

- [Architecture Overview](#architecture-overview)
- [What's Implemented](#whats-implemented)
- [Data Model (FRBR)](#data-model-frbr)
- [URI System (ELI-Style)](#uri-system-eli-style)
- [Versioning & Temporal Queries](#versioning--temporal-queries)
- [Citation Resolution](#citation-resolution)
- [Storage Layers](#storage-layers)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Roadmap](#roadmap)
- [RuVector Integration](#ruvector-integration)
- [Contributing](#contributing)

---

## 🏗️ Architecture Overview

### Three-Layer Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         GOLD LAYER                            │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐ │
│  │ Knowledge Graph│  │ Search Indexes │  │  Citation Graph│ │
│  │ (entities,     │  │ (BM25 + Vector)│  │  (amendments,  │ │
│  │  concepts,     │  │                │  │   references)  │ │
│  │  relations)    │  │                │  │                │ │
│  └────────────────┘  └────────────────┘  └────────────────┘ │
└──────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌──────────────────────────────────────────────────────────────┐
│                        SILVER LAYER                           │
│  ┌────────────────────────────────────────────────────────┐  │
│  │      Canonical Documents (FRBR Model)                  │  │
│  │  ┌──────────┐  ┌────────────┐  ┌──────────────────┐   │  │
│  │  │   Work   │  │ Expression │  │  Manifestation   │   │  │
│  │  │          │  │  (version) │  │    (format)      │   │  │
│  │  │  (what)  │  │   (when)   │  │     (how)        │   │  │
│  │  └──────────┘  └────────────┘  └──────────────────┘   │  │
│  │                                                          │  │
│  │  Fragments: article, paragraph, consideration, etc.     │  │
│  │  Each with stable URIs and provenance                   │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌──────────────────────────────────────────────────────────────┐
│                        BRONZE LAYER                           │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Immutable Raw Storage (exact bytes retrieved)         │  │
│  │  - PDFs (scanned + digital)                            │  │
│  │  - HTML from scrapers                                  │  │
│  │  - XML from SRU endpoints                              │  │
│  │  - JSON from APIs                                      │  │
│  │                                                          │  │
│  │  Each record: checksum + timestamp + source URL        │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### Serving Layers

```
┌─────────────────────────────────────────────────────────┐
│                    PUBLIC INTERFACES                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ REST API     │  │ Linked Data  │  │ Static Site  │  │
│  │ (FastAPI)    │  │ (JSON-LD)    │  │ (GitHub Pgs) │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │         RAG + GraphRAG Integration               │   │
│  │  (Hybrid retrieval → Graph expansion → Rerank)  │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## ✅ What's Implemented

### Core Infrastructure (~7,500 LOC)

- ✅ **FRBR Data Model** (`core/models.py`): Work, Expression, Manifestation, Fragment
- ✅ **ELI-Style URI System** (`core/identifiers.py`): Canonical URIs for every object
- ✅ **Temporal Versioning** (`core/versioning.py`): Point-in-time queries, version chains
- ✅ **Citation Resolver** (`core/resolver.py`): Multi-pass reference extraction with context
- ✅ **SQLite Store** (`core/store.py`): Persistent canonical storage
- ✅ **Bronze Layer** (`ingestion/bronze.py`): Immutable raw document storage
- ✅ **OCR Pipeline** (`ocr/`): Qwen2.5-VL/Tesseract extraction, structure detection, citation extraction
- ✅ **Amendment Consolidation** (`consolidation/`): Regex + LLM (local Qwen or OpenRouter) document classifier and amendment-instruction parser
- ✅ **Evaluation Framework** (`evaluation/`): Metrics, benchmarks, datasets
- ✅ **Manual Correction System** (`corrections/`): Web UI for fixing OCR errors, citations, metadata
- ✅ **Web Scrapers** (`ingestion/scrapers/`): DNA, Belastingdienst (Tax), MAS, SRIS + generic fallback scraper
- ✅ **Batch Processing** (`ingestion/batch_processor.py`): Bulk PDF ingestion pipeline

The REST API and standalone quality-dashboard modules from earlier prototypes have been removed; retrieval and browsing are currently served through the static site generator (`static_gen/`).

### What Works Right Now

```python
from lexsr.core.store import CanonicalStore
from lexsr.core.identifiers import law_fragment_uri
from datetime import date

# Open the canonical store
store = CanonicalStore("data/canonical.db")

# Get a specific version of a law valid on a date
expression = store.get_expression_at_date(
    work_id="arbeidswet-1963",
    query_date=date(2024, 1, 15)
)

# Resolve a citation from text
from lexsr.core.resolver import CitationResolver

resolver = CitationResolver(store=store)
refs = resolver.resolve_text(
    "Zoals bepaald in artikel 4 lid 2 Arbeidswet 1963"
)

for ref in refs:
    print(f"{ref.uri} (confidence: {ref.confidence})")
# Output: /id/law/arbeidswet-1963/2024-01-15/article/4/paragraph/2 (confidence: 0.85)
```

---

## 📖 Data Model (FRBR)

We use the **FRBR** (Functional Requirements for Bibliographic Records) model adapted for legal documents:

```
Work (abstract legal act)
  ↓
Expression (text at a point in time)
  ↓
Manifestation (published format: XML, HTML, PDF)
  ↓
Fragment (addressable part: article, paragraph, consideration)
```

### Example: Labour Act 1963

```
Work:
  - URI: /id/law/arbeidswet-1963
  - Title: "Arbeidswet 1963"
  - Official ID: arbeidswet-1963
  - Status: in_force

Expression (version as of 2024-01-15):
  - URI: /id/law/arbeidswet-1963/2024-01-15
  - Version date: 2024-01-15
  - In force: [1963-01-15 → ...]
  - Previous: /id/law/arbeidswet-1963/2022-01-01
  - Next: None

Manifestation (XML format):
  - URI: /id/law/arbeidswet-1963/2024-01-15/xml
  - Format: application/akn+xml
  - Storage: bronze/sha256-abc123...
  - Checksum: abc123...

Fragment (Article 4, paragraph 2):
  - URI: /id/law/arbeidswet-1963/2024-01-15/article/4/paragraph/2
  - Type: paragraph
  - Text: "De werknemer heeft recht op..."
  - Anchor: /article[@eId='art_4']/paragraph[@eId='art_4__para_2']
```

### Fragment Types

**Legislation:**
- book, title, chapter, section, paragraph_group
- article, paragraph, sub, annex

**Case Law:**
- consideration (r.o.), facts, opinion, decision, dissent

**Parliamentary:**
- agenda_item, speaker_turn, motion, amendment

---

## 🔗 URI System (ELI-Style)

Every object has a **stable, canonical URI** that never changes.

### URI Patterns

```
Legislation Work:       /id/law/{official_id}
Legislation Expression: /id/law/{official_id}/{date}
Legislation Fragment:   /id/law/{official_id}/{date}/article/{nr}/paragraph/{nr}

Case Law:               /id/ecli/{ECLI}
Case Law Fragment:      /id/ecli/{ECLI}/consideration/{nr}

EU Law:                 /id/celex/{CELEX}
Gazette:                /id/gazette/{jurisdiction}/{year}/{number}
Parliamentary:          /id/parliamentary/{jurisdiction}/{doc_id}
```

### Examples

```
/id/law/arbeidswet-1963
/id/law/arbeidswet-1963/2024-01-15
/id/law/arbeidswet-1963/2024-01-15/article/4
/id/law/arbeidswet-1963/2024-01-15/article/4/paragraph/2
/id/law/arbeidswet-1963/2024-01-15/article/4/paragraph/2/sub/a

/id/ecli/ECLI:SR:HR:2020:1234
/id/ecli/ECLI:SR:HR:2020:1234/consideration/4.3

/id/celex/32016R0679
/id/gazette/sr/2024/123
```

### Abbreviation Registry

Common law abbreviations are resolved to official IDs:

```python
from lexsr.core.identifiers import resolve_abbreviation

resolve_abbreviation("Arbeidswet")  # → "arbeidswet-1963"
resolve_abbreviation("AW")          # → "arbeidswet-1963"
resolve_abbreviation("BW")          # → "burgerlijk-wetboek"
resolve_abbreviation("WvSr")        # → "wetboek-van-strafrecht"
```

---

## ⏰ Versioning & Temporal Queries

The system maintains a **complete version history** for every legal work.

### Version Chain

Each Work has a VersionChain tracking all Expressions in chronological order:

```python
from lexsr.core.versioning import VersionChain, TemporalIndex
from datetime import date

# Build a version chain
chain = VersionChain(work)
chain.add_expression(expr_2022)
chain.add_expression(expr_2024)

# Query: "What was the law on 2023-06-15?"
expr = chain.at_date(date(2023, 6, 15))
# Returns: expr_2022 (the version valid at that date)

# Get all versions between two dates
versions = chain.versions_between(date(2022, 1, 1), date(2024, 12, 31))
```

### Temporal Index

The TemporalIndex provides fast lookups across all works:

```python
index = TemporalIndex()
index.add_chain(chain_arbeidswet)
index.add_chain(chain_grondwet)

# Get all works in force on a specific date
works = index.works_in_force_on(date(2023, 1, 1))

# Find all works that changed between two dates
changes = index.changes_between(date(2024, 1, 1), date(2024, 12, 31))
```

### TemporalExtent

Every Expression has a TemporalExtent defining when it was valid:

```python
from lexsr.core.models import TemporalExtent
from datetime import date

extent = TemporalExtent(
    start=date(2022, 1, 1),
    end=date(2024, 6, 15)
)

extent.contains(date(2023, 1, 1))  # True
extent.contains(date(2025, 1, 1))  # False
extent.is_open()                    # False (has an end date)
```

---

## 🔍 Citation Resolution

The **CitationResolver** extracts and resolves legal references from text using a **multi-pass** strategy.

### Multi-Pass Extraction

1. **Deterministic identifiers**: ECLI, CELEX (high confidence: 0.90-0.98)
2. **Structured citations**: "artikel 4 lid 2 Arbeidswet 1963" (medium confidence: 0.85)
3. **EU legislation**: Directives, Regulations (medium confidence: 0.80-0.85)
4. **Gazette references**: Staatsblad, Gouvernementsblad (medium confidence: 0.75-0.80)
5. **Bare article references**: "artikel 12" (low confidence: 0.30, needs context)

### Example Usage

```python
from lexsr.core.resolver import CitationResolver

resolver = CitationResolver()

text = """
Volgens artikel 4 lid 2 van de Arbeidswet 1963 (S.B. 1963, nr. 163)
heeft de werknemer recht op verlof. Zie ook ECLI:NL:HR:2020:1234, r.o. 4.3
en Verordening (EU) 2016/679.
"""

refs = resolver.resolve_text(text)

for ref in refs:
    print(f"Found: {ref.raw_text}")
    print(f"  URI: {ref.uri}")
    print(f"  Type: {ref.ref_type.value}")
    print(f"  Confidence: {ref.confidence:.2f}")
    print()

# Output:
# Found: artikel 4 lid 2 van de Arbeidswet 1963
#   URI: /id/law/arbeidswet-1963/2026-02-14/article/4/paragraph/2
#   Type: legislation_citation
#   Confidence: 0.85
#
# Found: S.B. 1963, nr. 163
#   URI: /id/gazette/sr/1963/163
#   Type: gazette
#   Confidence: 0.80
#
# Found: ECLI:NL:HR:2020:1234, r.o. 4.3
#   URI: /id/ecli/ECLI:NL:HR:2020:1234/consideration/4.3
#   Type: ecli
#   Confidence: 0.95
#
# Found: Verordening (EU) 2016/679
#   URI: /id/celex/32016R0679
#   Type: eu_regulation
#   Confidence: 0.80
```

### Contextual Disambiguation

For bare references like "artikel 5", the resolver uses **contextual tracking**:

```python
text = """
De Arbeidswet 1963 regelt arbeidsvoorwaarden.
Artikel 5 bepaalt de minimumlonen.
"""

refs = resolver.resolve_text(text)
# The bare "artikel 5" is resolved to:
#   /id/law/arbeidswet-1963/2026-02-14/article/5
# because "Arbeidswet 1963" was mentioned nearby (confidence boosted to 0.45)
```

### Unresolved Reference Queue

References that cannot be resolved are queued for later review:

```python
# Enable the unresolved queue
resolver = CitationResolver(unresolved_db_path="data/unresolved.db")

# After processing documents, get statistics
stats = resolver.get_unresolved_stats()
print(stats)
# {
#   'total_unresolved': 42,
#   'by_type': {
#     'legislation_citation': {'count': 28, 'avg_attempts': 2.3},
#     'unknown': {'count': 14, 'avg_attempts': 1.5}
#   },
#   'top_frequent': [...]
# }

# Manually resolve a queued reference
resolver.resolve_from_queue(ref_id="abc123", uri="/id/law/custom-law/article/5")
```

---

## 💾 Storage Layers

### Bronze Layer: Immutable Raw Storage

The Bronze layer stores **exact bytes** retrieved from sources:

```python
from lexsr.ingestion.bronze import BronzeStore, BronzeRecord

store = BronzeStore("data/bronze.db")

# Store a raw PDF
record = BronzeRecord(
    id="labour-act-1963-sb-163",
    source_type="sb_gazette",
    source_url="https://example.com/sb-1963-163.pdf",
    content_type="application/pdf",
    content=pdf_bytes,
)

store.store(record)
# Returns True if new, False if duplicate (by content hash)

# Retrieve by ID
record = store.get("labour-act-1963-sb-163")

# Retrieve by source URL (may have multiple versions)
records = store.get_by_url("https://example.com/sb-1963-163.pdf")
```

**Key features:**
- Deduplication by SHA-256 checksum
- HTTP headers and metadata preserved
- Immutable: once stored, never modified
- Every derived product traces back to Bronze

### Silver Layer: Canonical Store

The Silver layer stores **structured, normalized documents** using the FRBR model:

```python
from lexsr.core.store import CanonicalStore
from lexsr.core.models import Work, Expression, Fragment

store = CanonicalStore("data/canonical.db")

# Save a Work
work = Work(
    id="arbeidswet-1963",
    uri="/id/law/arbeidswet-1963",
    source_type=SourceType.LEGISLATION,
    official_id="arbeidswet-1963",
    title="Arbeidswet 1963",
    jurisdiction="SR",
)
store.save_work(work)

# Save an Expression
expression = Expression(
    id="arbeidswet-1963-2024-01-15",
    uri="/id/law/arbeidswet-1963/2024-01-15",
    work_id="arbeidswet-1963",
    work_uri="/id/law/arbeidswet-1963",
    version_date=date(2024, 1, 15),
)
store.save_expression(expression)

# Save Fragments
fragment = Fragment(
    id="arbeidswet-1963-2024-01-15-art4-para2",
    uri="/id/law/arbeidswet-1963/2024-01-15/article/4/paragraph/2",
    expression_id="arbeidswet-1963-2024-01-15",
    expression_uri="/id/law/arbeidswet-1963/2024-01-15",
    work_id="arbeidswet-1963",
    fragment_type=FragmentType.PARAGRAPH,
    number="2",
    text="De werknemer heeft recht op...",
)
store.save_fragment(fragment)

# Query by URI
work = store.get_work_by_uri("/id/law/arbeidswet-1963")

# Temporal query
expr = store.get_expression_at_date("arbeidswet-1963", date(2024, 6, 15))

# Get all fragments for an expression
fragments = store.get_fragments_for_expression("arbeidswet-1963-2024-01-15")
```

### Gold Layer: Knowledge Products (Planned)

The Gold layer will contain:
- **Knowledge Graph**: Documents, fragments, entities, concepts, relationships with provenance
- **Search Indexes**: BM25 (lexical) + Vector (semantic) hybrid search
- **Citation Graph**: All citations resolved to internal nodes with confidence scores

---

## 🚀 Installation

### Prerequisites

- Python 3.10+
- (Optional) Local Qwen 2.5 Coder 7B via vLLM for code generation

### Install from source

```bash
git clone https://github.com/your-org/wetten-van-suriname.git
cd wetten-van-suriname

# Install core (no dependencies except stdlib)
pip install -e .

# Install with all optional features
pip install -e ".[all]"

# Install specific features
pip install -e ".[api,search,eval]"
```

### Available extras

- `api`: FastAPI, uvicorn, pydantic (REST API server)
- `ingestion`: requests, lxml (data scrapers)
- `ocr`: torch, transformers, pypdfium2, Pillow (OCR pipeline)
- `search`: chromadb, sentence-transformers (hybrid search)
- `scraper`: httpx, beautifulsoup4 (web scrapers)
- `static`: jinja2 (static site generation)
- `eval`: numpy (evaluation metrics)
- `dev`: pytest, pytest-cov, ruff (development tools)
- `all`: All of the above

---

## 🏃 Quick Start

### 1. Create a canonical store and add a law

```python
from lexsr.core.store import CanonicalStore
from lexsr.core.models import Work, Expression, SourceType, DocumentStatus
from datetime import date

# Initialize store
store = CanonicalStore("data/canonical.db")

# Create a Work
work = Work(
    id="grondwet-1987",
    uri="/id/law/grondwet-1987",
    source_type=SourceType.LEGISLATION,
    official_id="grondwet-1987",
    title="Grondwet voor de Republiek Suriname",
    short_title="Grondwet",
    jurisdiction="SR",
    status=DocumentStatus.IN_FORCE,
    date_enacted=date(1987, 10, 30),
)
store.save_work(work)

# Create an Expression
expression = Expression(
    id="grondwet-1987-2024",
    uri="/id/law/grondwet-1987/2024-01-01",
    work_id="grondwet-1987",
    work_uri="/id/law/grondwet-1987",
    version_date=date(2024, 1, 1),
    status=DocumentStatus.IN_FORCE,
)
store.save_expression(expression)

print(f"Saved: {work.title}")
```

### 2. Resolve citations from text

```python
from lexsr.core.resolver import CitationResolver

resolver = CitationResolver()

text = "Artikel 10 van de Grondwet waarborgt de vrijheid van meningsuiting."

refs = resolver.resolve_text(text)
for ref in refs:
    if ref.status.value == "resolved":
        print(f"Resolved: {ref.raw_text} → {ref.uri}")
```

### 3. Launch the manual correction UI

```bash
python examples/07_correction_ui.py
```

Visit http://127.0.0.1:5001 to correct OCR errors, citations, and metadata.

See [CORRECTIONS.md](CORRECTIONS.md) for full documentation.

### 4. Use the CLI

```bash
python -m lexsr stats               # database statistics
python -m lexsr ingest-pdfs         # OCR pipeline over data/raw/
python -m lexsr consolidate         # apply amendments to base laws
python -m lexsr link-citations      # backfill citation links
python -m lexsr index                # build the BM25 search index
python -m lexsr index-vectors        # build the dense vector index (multilingual-e5-large)
python -m lexsr generate             # build the static site -> site/
python -m lexsr serve                # serve the generated site locally
python -m lexsr search "artikel 4 arbeidswet"   # hybrid BM25+vector if a vector index exists
python -m lexsr benchmark           # run the citation-resolution benchmark
```

Run `python -m lexsr <command> --help` for per-command options. There is no REST API server currently — retrieval and browsing are served through the generated static site.

---

## 🗺️ Roadmap

### Phase 1: Foundation (✅ Complete)

- ✅ FRBR data model
- ✅ ELI-style URI system
- ✅ Temporal versioning
- ✅ Citation resolver
- ✅ SQLite canonical store
- ✅ Bronze layer (immutable raw storage)

### Phase 2: Ingestion & OCR (✅ Complete)

- ✅ PDF OCR pipeline (Qwen2.5-VL / Tesseract, with structure detection)
- ✅ Structure extraction from OCR text
- ✅ Web scrapers for Suriname sources (DNA, Belastingdienst, MAS, SRIS + generic/SSB)
- ✅ Batch processor: Bronze → OCR → Canonical, with search indexing
- ✅ Manual correction system (web UI for data quality)
- ✅ Amendment consolidation (classify → parse → apply, `lexsr consolidate`)
- ⬜ Deduplication and quality checks

### Phase 3: Search & Graph (🚧 In Progress)

- ✅ BM25 lexical search (`search/bm25.py`)
- ✅ Vector search + hybrid retrieval + reranker scaffolding (`search/vector.py`, `hybrid.py`, `reranker.py`)
- ⬜ Production embedding model wiring (multilingual-e5-large) and evaluation against quality targets below
- ⬜ Citation graph builder
- ⬜ Amendment chain extractor
- ⬜ Graph traversal for GraphRAG

### Phase 4: Knowledge Graph & RAG (🔮 Future)

- ⬜ Entity extraction (courts, organizations, persons)
- ⬜ Concept linking (controlled vocabulary)
- ⬜ Knowledge graph (documents + entities + relations + provenance)
- ⬜ GraphRAG retrieval (hybrid search + graph expansion + reranking)
- ⬜ Answer synthesis with grounded citations
- ⬜ Faithfulness checks (citation coverage, contradiction detection)

### Phase 5: Publishing & Sustainability

- ✅ Static site generator (`static_gen/`, `lexsr generate`/`lexsr serve`)
- ⬜ JSON-LD / RDF exports (Linked Data)
- ⬜ SPARQL endpoint (optional)
- ⬜ Python SDK (PyPI)
- ⬜ Quality dashboards and alerting
- ⬜ Community contribution workflows

---

## 🔬 RuVector Integration

**RuVector** is a hybrid retrieval architecture that combines lexical search (BM25), semantic search (dense vectors), and reranking to achieve state-of-the-art retrieval quality.

### Three-Stage Retrieval Pipeline

```
User Query: "What is the minimum wage for agricultural workers?"
                              ↓
        ┌───────────────────┬─────────────────────┬──────────────┐
        ↓                   ↓                     ↓              ↓
   [BM25 (100)]        [Semantic (100)]    [Structure (10)]   [Graph]
   - Exact phrase        - Intent match      - Legal           - Citations
   - Keywords            - Similarity          hierarchy       - Amendments
        ↓                   ↓                     ↓              ↓
        └───────────────────┴─────────────────────┴──────────────┘
                              ↓
                 Reciprocal Rank Fusion
                   (weighted merge)
                              ↓
                       Top 50 candidates
                              ↓
                   [Cross-Encoder Reranker]
                  (score all query-doc pairs)
                              ↓
                      Return Top 10
                              ↓
        Response includes:
          - Snippet with highlighting
          - Score breakdown (BM25: 0.91, Semantic: 0.82, Rerank: 0.89)
          - Cite object (URI, source, confidence, effective date)
          - Provenance chain back to Bronze
```

### Implementation Plan

1. **Lexical Index** (Elasticsearch or Tantivy):
   - BM25 scoring
   - Article-level and paragraph-level chunking
   - Field boosting (title > article number > heading > text)

2. **Vector Index** (Qdrant or Chroma):
   - Embeddings: `multilingual-e5-large` (768D, free, multilingual)
   - Article-level and paragraph-level chunks
   - Store metadata (heading hierarchy, document type, temporal extent)

3. **Reranker** (cross-encoder):
   - Model: `mmarco-mMiniLMv2` (lightweight, good quality)
   - Re-scores top candidates using full query-document context
   - 10-20% nDCG lift over hybrid alone

4. **Legal-Aware Features**:
   - Boost exact matches for identifiers (ECLI, article numbers)
   - Temporal filtering (only return versions valid on query date)
   - Graph expansion (include cited provisions and amendments)

### Quality Targets

- **nDCG@10**: >0.75 (MVP baseline), >0.80 (production)
- **MRR**: >0.85 (correct answer usually rank 1-2)
- **Recall@10**: >0.70 (find most relevant provisions)
- **Precision@3**: >0.50 (majority of top 3 useful)

See [docs/ruvector-integration.md](docs/ruvector-integration.md) for detailed implementation.

---

## 🎓 Key Principles

### 1. Fragment URIs and Versioning

**Design fragment URIs correctly** — this is irreversible later.

```
/id/law/{official_id}/{version_date}/article/{nr}/paragraph/{nr}/sub/{letter}
```

Every fragment has:
- A canonical URI that never changes
- Multiple anchor strategies (structural path + text hash)
- Provenance metadata (extraction method, confidence, timestamp)

### 2. Citation Resolution and Integrity

**Build the citation resolver and integrity jobs** — link quality is your moat.

- Multi-pass extraction (deterministic → pattern-based → contextual)
- Resolver service (takes parsed reference → returns fragment URI)
- Link integrity jobs (broken target detection, duplicate merges, orphan fragments)
- Unresolved queue for human review

### 3. Evaluation Harness

**Create an evaluation harness** — so "best" is provable, not vibes.

- 100+ gold test queries (all difficulty levels, all document types)
- Expert relevance judgments (0-3 scale)
- Automated metrics (nDCG, MRR, Recall, Precision)
- Weekly regression tests
- A/B testing for new features

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests (`pytest tests/`)
5. Run code quality checks (`ruff check src/`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

### Development Setup

```bash
# Clone the repo
git clone https://github.com/your-org/wetten-van-suriname.git
cd wetten-van-suriname

# Install in development mode with all extras
pip install -e ".[dev,all]"

# Run tests
pytest tests/ -v --cov=src/lexsr

# Run code quality checks
ruff check src/
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

**Data License**: The structured annotations and metadata are released under CC0 1.0 (Public Domain). Original legal texts remain under their respective jurisdictions' copyright (typically public domain for legislation).

---

## 🙏 Acknowledgments

- **OASIS Akoma Ntoso**: International standard for legal document markup
- **European Legislation Identifier (ELI)**: URI scheme for legislation
- **FRBR**: Functional Requirements for Bibliographic Records
- **RuVector**: Hybrid retrieval architecture inspiration
- **UK legislation.gov.uk**: Akoma Ntoso implementation reference
- **Estonia Riigi Teataja**: Temporal versioning model
- **EU EUR-Lex**: Linked data publication patterns

---

## 🔧 Manual Corrections

The system includes a clean web interface for correcting data:

- **Fix OCR errors** - Correct text extraction mistakes
- **Update citations** - Fix incorrectly parsed references
- **Adjust metadata** - Correct titles, dates, categories
- **Full audit trail** - Every correction logged with timestamp, author, reason

```bash
python examples/07_correction_ui.py
# Visit http://127.0.0.1:5001
```

See [CORRECTIONS.md](CORRECTIONS.md) for complete documentation.

---

## 📞 Contact

- **Project Repository**: https://github.com/your-org/wetten-van-suriname
- **Issues**: https://github.com/your-org/wetten-van-suriname/issues
- **Discussions**: https://github.com/your-org/wetten-van-suriname/discussions

---

**Built with ❤️ for transparency, access to justice, and the rule of law in Suriname.**
