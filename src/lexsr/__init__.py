"""
LexSR - Suriname Legal Knowledge Fabric.

An OCR-first legal document portal for Suriname legislation:
canonical identity, citation resolution, hybrid search,
temporal versioning, static site generation, and API serving.

Modules:
    core        - FRBR data model, URI system, versioning, store, resolver, integrity
    ocr         - DeepSeek OCR pipeline for scanned PDFs
    extraction  - Structure extraction from OCR text
    scraper     - Web scrapers for Suriname legal sources
    search      - BM25 + vector hybrid search (RuVector)
    graph       - Citation graph and amendment chains
    static_gen  - Static HTML site generator (GitHub Pages)
    evaluation  - Benchmark suite, metrics, known-answer datasets
    ingestion   - Bronze/Silver pipeline for document data
    api         - REST API serving layer
    improvement - Active learning and quality monitoring
"""

__version__ = "0.4.0"
