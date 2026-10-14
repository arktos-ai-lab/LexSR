# LexSR: Surinamese legislation and case law as linked data

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

LexSR turns Suriname's scattered, mostly scanned legal publications into a structured,
versioned corpus. It scrapes government sources and the Hof van Justitie's case-law portal
(*rechtspraak.sr*), runs OCR where needed, consolidates amendment acts
(*wijzigingswetten*) into dated versions of the laws they change, and links court
decisions to the legislation they apply. The result is a knowledge graph of amendment,
citation and case-application edges.

This repository accompanies the paper:

> Ernst van Gassen. *LexSR: Consolidating Legislation and Linking Case Law to Build a Legal
> Knowledge Graph for Suriname, a Low-Resource Jurisdiction.* JURIX 2026 (accepted).

The paper source is in [`article/`](article/).

## Corpus at a glance

Figures for the corpus reported in the paper:

| | |
|---|---|
| Legislative works | 1,323 (1931 to 2025) |
| Case-law decisions | 300 (1952 to 2025) |
| Fragments (articles, paragraphs, considerations) | 45,293 |
| Citations extracted | 15,867 |
| Citations linked to a work in the corpus | 2,713 (17.1%) |
| Knowledge graph | 1,623 nodes, 2,768 edges |

The corpus database is not yet included in this repository; see
[Data availability](#data-availability).

## How it works

1. **Ingestion.** Scrapers for ten live government sources (parliament, SRIS, tax
   authority, central bank, standards bureau, government portal and ministry sites) plus
   *rechtspraak.sr*, which is enumerated through its WordPress sitemap. Source files are
   kept unchanged on disk.
2. **OCR and structure.** Embedded PDF text first, Tesseract OCR as fallback. Articles,
   paragraphs (*leden*) and sub-items are segmented by the standard Dutch legislative
   headings; court decisions are segmented into numbered considerations.
3. **Data model.** FRBR-style: a `Work` (a law or decision) has dated `Expression`s, and
   each expression is split into addressable `Fragment`s. Identifiers follow an
   ELI-inspired pattern, `/id/law/...` and `/id/caselaw/...`.
4. **Amendment consolidation.** A regex parser (about 20 patterns for repeal, replacement,
   insertion and phrase substitution) extracts instructions from amendment acts; the
   consolidation engine applies them to produce a new expression at the effective date.
   An optional LLM pass, off by default, re-reads low-confidence instructions.
5. **Citation linking.** References such as *artikel 4 lid 2 Arbeidswet 1963* are
   extracted from legislation and case law and resolved to works, falling back to title
   matching because scraped documents do not carry canonical identifiers.
6. **Knowledge graph.** One node per work; `AMENDS`, `CITES` and `APPLIES` edges, exported
   as GraphML.

## Installation

Requires Python 3.10 or later. The core package has no dependencies; features are
installed as extras.

```bash
git clone https://github.com/arktos-ai-lab/LexSR.git
cd LexSR
pip install -e ".[all]"      # or pick extras: ingestion, scraper, ocr, search, static, eval, graph
```

OCR of scanned PDFs also needs [Tesseract](https://github.com/tesseract-ocr/tesseract)
with the Dutch language pack (`nld`).

## Usage

All commands run through `python -m lexsr`:

```bash
python -m lexsr ingest                 # scrape the live government sources
python -m lexsr ingest-pdfs            # process PDFs already in data/raw/
python -m lexsr ingest-caselaw         # scrape rechtspraak.sr
python -m lexsr consolidate            # parse and apply amendment acts
python -m lexsr link-citations         # (re)link citations for all fragments
python -m lexsr build-graph            # write data/knowledge_graph.graphml
python -m lexsr stats                  # corpus statistics
python -m lexsr benchmark              # citation-resolution benchmark
python -m lexsr index                  # BM25 search index
python -m lexsr search "arbeidswet"    # search the corpus
python -m lexsr generate               # build the static website
```

## Reproducing the paper's evaluations

```bash
python -m lexsr benchmark                                   # 61-case citation benchmark
python scripts/amendment_diagnostics.py --db data/canonical.db --n 100   # amendment parsing coverage
python -m lexsr build-graph                                 # graph statistics
```

## Known limitations

These are discussed in the paper:

- 83% of extracted citations are not linked; most are gazette references
  (*Staatsblad*, *Gouvernementsblad*) that the resolver does not yet match.
- 36 of 50 amendment documents yield at least one classified instruction. All failures
  trace to operative text missing from the ingested source, not to the parser rules.
- Six of sixteen candidate government sources were excluded because their sites changed.
- OCR quality and document classification are not evaluated separately.
- The 61-case citation benchmark was produced together with the resolver patterns and
  measures pattern coverage, not generalisation.

## Data availability

The corpus database and knowledge graph will be released separately. This section will
link to the release once it is available.

## Repository layout

```
src/lexsr/       package: core model, ingestion, OCR, consolidation, graph, search, site
scripts/         one-off diagnostics and maintenance scripts
tests/           pytest suite
article/         JURIX 2026 paper (LaTeX source and PDF)
docs/            architecture notes
```

## Development

LexSR was developed by one researcher with AI coding assistants. Run the tests with:

```bash
pip install -e ".[dev]"
pytest
```

## Licence

Code is released under the [MIT License](LICENSE).

## Contact

Ernst van Gassen, Arktos AI Lab ([ORCID 0009-0000-0314-6441](https://orcid.org/0009-0000-0314-6441))
