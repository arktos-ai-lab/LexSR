# LexSR: A Legal Knowledge Graph for a Low-Resource Jurisdiction — Consolidating Legislation and Linking Case Law for Suriname

**JURIX 2026 full-paper deadline (Sept 5, 2026 AoE) was missed** — retargeting to the
*Artificial Intelligence and Law* journal (Springer, rolling submission, IOS Press format
compatible), with JURIX 2027 / ICAIL 2027 as possible conference alternatives once their CFPs
are posted (neither had a live deadline as of 2026-09-06).

> **Submission category**: Long paper (target ≤10 pages excl. references)
> **Track**: Natural Language Processing and Machine Learning
> **Format**: IOS Press / Frontiers in AI and Applications (FAIA)

> **Authors**: Ernst van Gassen, Independent researcher (evg.gassen@gmail.com)

---

## Abstract

Access to consolidated, machine-readable legislation and linked case law is a prerequisite
for effective legal information systems. For Suriname — a Dutch-speaking jurisdiction of
fewer than 600,000 people with a predominantly scanned legal archive — no such resource
previously existed. We present **LexSR**, a pipeline that ingests raw government PDFs and
the Hof van Justitie's case-law portal, applies OCR, classifies documents, automatically
consolidates *wijzigingswetten* (amendment acts) into versioned legislative expressions
modelled on FRBR, and links case law to the legislation it applies. The pipeline produces a
corpus of **1,623 works** (1,323 legislative, 300 judicial) and **45,293 fragments**, from
which we construct a unified knowledge graph of **2,768 edges** spanning amendment,
citation, and case-application relationships. We report two evaluations: a synthetic
citation-resolution benchmark, where our resolver achieves 100% precision/recall against a
curated 61-case gold set, and — the paper's methodological contribution — a measurement of
how much of that resolution accuracy actually survives contact with the real, messily-titled
corpus it was built to run against. Only 17% of extracted citations resolve to an
in-corpus work; we trace this gap to a structural mismatch between idealized
canonical identifiers and the filename-derived IDs that real-world scraped/OCR'd ingestion
produces, and report the fix. We also measure amendment-parsing coverage as the corpus grew
from 33 to 50 amendment documents (82% → 38%), a second honest signal of how benchmark accuracy on a
curated subset can overstate real-corpus performance. We discuss implications for
low-resource legal NLP and make the corpus, code, and evaluation scripts publicly available.

---

## 1. Introduction

Consolidation — merging an amendment act's instructions into the base law it modifies — and
citation linkage — connecting case law to the provisions it applies — are both legally
critical and technically demanding. Most European jurisdictions maintain authoritative
consolidated legislation and case-law databases through governmental portals (e.g.,
*wetten.overheid.nl* and *rechtspraak.nl* in the Netherlands, EUR-Lex for EU law). Small and
developing jurisdictions often lack the institutional capacity for either, leaving
practitioners to manually track amendment chains and cross-reference case law with no
integrated view of the law in force.

Suriname illustrates this gap sharply. The *Staatsblad* (official gazette) is available as
individual scanned PDFs through several government sources, and the Hof van Justitie
publishes case decisions on a dedicated portal (*rechtspraak.sr*, launched 2019), but no
system links the two: a decision citing "artikel 4 Arbeidswet 1963" offers no way to jump to
that provision, and no portal shows any act's consolidated text as amended.

This paper makes four contributions:

1. **LexSR corpus**: a structured, FRBR-modelled database of 1,323 Surinamese legislative
   works and 300 Hof van Justitie decisions, with 45,293 fragments, derived from ten live
   government sources, the judicial case-law portal, and locally digitised archives.
2. **Amendment parser**: a hybrid regex + LLM system that extracts structured consolidation
   instructions from *wijzigingswetten*, evaluated across the corpus's full growth trajectory.
3. **Case-law integration**: a scraper and ingestion pipeline for *rechtspraak.sr* that
   segments decisions into numbered considerations and links them to cited legislation,
   reusing the same citation-resolution machinery built for legislation-to-legislation
   citations.
4. **Knowledge graph and an honest accuracy audit**: a unified graph of amendment, citation,
   and case-application edges over the full corpus, together with a measurement of the gap
   between synthetic-benchmark citation accuracy and real-corpus linkage rate — and the fix
   that closed most of it.

The remainder of this paper is organised as follows. Section 2 reviews related work.
Section 3 describes the corpus and ingestion pipeline, including the newly added case-law
source. Section 4 details amendment consolidation. Section 5 describes case-law integration
and knowledge graph construction. Section 6 presents evaluation results, including the
citation-linkage accuracy audit. Section 7 discusses limitations and future work, and
Section 8 concludes.

---

## 2. Related Work

### 2.1 Legal Document Modelling

The FRBR (Functional Requirements for Bibliographic Records) model provides a
well-established abstraction for legislative documents, distinguishing the abstract **Work**
(a law), its **Expression** (a version at a given date), its **Manifestation** (a particular
encoding), and individual **Items** [IFLA 1998]. Akoma Ntoso [Palmirani and Vitali 2011] is
the primary XML schema for legislation structured around these concepts and has been adopted
by the UN, EU, and several national parliaments. The European Legislation Identifier (ELI)
[Publications Office 2012] provides URI conventions compatible with this model. We extend
this modelling to case law following the same FRBR pattern: a court decision is a Work with
a single Expression (the published text does not get amended the way legislation does), and
its numbered considerations are Fragments — the case-law analogue of legislative articles.

### 2.2 Legal Knowledge Systems for Consolidation

Automated consolidation has received sustained attention in the legal knowledge systems
community. Biagioli, Francesconi et al. [2004] describe the *Norme in Rete* project's XML
standards and tools for cross-referencing and consolidating Italian legislation. Spinosa et
al. [2009] apply NLP-based metadata extraction to detect and classify textual amendments
(repeal, substitution, integration) for the same consolidation task. The *legislation.gov.uk*
system [Sheridan and Tennison 2010]
handles consolidation for UK law at scale with a semi-automated editorial workflow. Vitali
and Zeni [2007] discuss amendment formalisation in Akoma Ntoso. The Dutch
*wetten.overheid.nl* portal maintains consolidated texts for all Dutch and former-colonial
legislation through a government editorial process, but does not publish its consolidation
tooling [KOOP 2022]. LexSR differs from these in targeting a low-resource setting — no
existing structured archive, predominantly scanned PDFs, and no editorial support — with a
fully automated pipeline.

### 2.3 Legal Knowledge Graphs and Citation Networks

Citation network analysis of case law has a long history in AI and Law, from early work on
precedent networks to more recent graph-based approaches to legal information retrieval and
argumentation mining [Bench-Capon et al. 2012]. Legal knowledge graphs unifying legislation
and case law have been built for well-resourced jurisdictions with existing structured data —
e.g., Dhani et al. [2021] construct one from Indian court judgments and statutes for
case-similarity recommendation — but these rely on structured source data; we are
not aware of prior work constructing such a graph from scratch for a jurisdiction whose
primary source material is unstructured scanned PDFs and an unindexed WordPress-based case
portal, which is the setting this paper addresses.

### 2.4 NLP for Legal Amendment Text

Information extraction from legal amendment provisions has been studied for several European
languages. Lesmo, Mazzei, Palmirani et al. [2013] present TULSI, an NLP system combining deep
syntactic analysis with a shallow semantic interpreter to extract and classify modificatory
provisions in Italian legislative texts. For Dutch, Boer et al. [2007] propose the
MetaLex/LKIF XML standards for structuring legislation, and Hoekstra et al. [2007] extend
this with the LKIF Core ontology of basic legal concepts, but explicit amendment/consolidation
parsing for Dutch has received limited attention in the JURIX and ICAIL literature. The use of large language models for
legal text understanding is well-established [Chalkidis et al. 2020; Koreeda and Manning
2021]. Our hybrid approach — regex-first with LLM fallback for low-confidence cases — is
motivated by the need for determinism and auditability while retaining flexibility for novel
constructions.

### 2.5 Legal Corpora for Small Jurisdictions

The JURIX and ICAIL communities have increasingly highlighted the need for legal NLP
resources beyond the major European languages [Niklaus et al. 2024]. Krasadakis et al.
[2024] survey the specific challenges legal informatics poses for low-resource-language NLP.
To our knowledge, no
machine-readable structured corpus linking legislation and case law for Suriname has
previously been published.

---

## 3. Corpus and Ingestion Pipeline

### 3.1 Sources

LexSR ingests from ten live government sources plus locally digitised PDF archives: the
parliament website (DNA.sr), the legal database SRIS, the tax authority (Belastingdienst),
the central bank (MAS), the standards bureau (SSB), the main government portal, and four
ministry sites (finance, labor, natural resources, and the electoral bureau). We evaluated
all sixteen government sources our scraper infrastructure supports; six were excluded after
diagnosis showed their configured URLs no longer match the live site structure (Section 7
discusses this as a recurring low-resource-jurisdiction problem: source sites change without
notice and without a stable API to detect it). Case law is sourced separately from
*rechtspraak.sr*, the Hof van Justitie's decision portal, described in Section 5.1. All
source documents are stored immutably in a bronze layer with SHA-256 checksums and retrieval
timestamps.

### 3.2 Data Model

The canonical store implements FRBR at four levels:

| FRBR level | LexSR entity | Legislation example | Case-law example |
|---|---|---|---|
| Work | `Work` | Arbeidswet 1963 | SRU-HvJ-2022-39 |
| Expression | `Expression` | version_date=2024-01-15 | single expression (decision text) |
| Manifestation | `Manifestation` | source PDF | source HTML page |
| Item | `Fragment` | Artikel 4, lid 2 | consideration 2.1 |

Stable URIs follow an ELI-inspired pattern rooted at `/id/{scheme}/{official-id}`, with
`law` and `caselaw` as the two schemes currently populated. The amendment relation is
represented by an `AmendmentLink` table connecting an amending Work to the base Work it
modifies; the citation relation (legislation-to-legislation, case-to-legislation, and
case-to-case) is represented by a single generic `Citation` table typed by
`citation_type`, avoiding a schema split between the two document kinds.

### 3.3 Corpus Statistics

| Metric | Value |
|---|---|
| Legislative works | 1,323 |
| Case-law works (decisions) | 300 |
| Expressions | 1,633 |
| Fragments (articles, paragraphs, considerations) | 45,293 |
| Considerations extracted from case law | 1,142 |
| Citations extracted | 15,867 |
| Citations resolved to an in-corpus work | 2,713 (17.1%; see §6.2) |
| Amendment links identified | 55 |
| Amendment links fully applied by the engine | 11 |
| Knowledge graph nodes / edges | 1,623 / 2,768 |

The legislative corpus spans material from 1931 to 2025, with the densest coverage in the
2010–2025 period corresponding to the availability of digital-native PDFs. The case-law
sample spans 1952–2025 and was drawn from a discoverable pool of 900+ decisions on
*rechtspraak.sr* (Section 5.1); this paper reports on the first 300 ingested.

### 3.4 OCR and Structure Extraction

For scanned PDFs, text is extracted using a pipeline that applies standard PDF text
extraction first and falls back to Tesseract OCR for image-based pages. Article boundaries
are detected heuristically using the standard Dutch/Surinamese legislative structure:
`Artikel N` headings, `Lid N` sub-paragraphs, and lettered or numbered sub-items. OCR quality
varies substantially across the corpus; a practical, low-resource-specific finding is that
the target machine did not have the Dutch Tesseract language pack installed, silently
degrading a subset of the corpus to English-model OCR before this was caught and an
availability check added (Section 7.1).

---

## 4. Amendment Consolidation

### 4.1 Structure of a *Wijzigingswet*

A Surinamese amendment act (*wijzigingswet* or *wijzigingsbesluit*) follows a standard
template. The operative section (Artikel 1 of the amendment) names the base law and lists
labelled instructions:

```
Artikel 1
De Wet Toezicht en Controle op Financiële Dienstverlening (S.B. 2009 no. 78)
wordt als volgt gewijzigd:

A. In artikel 3 lid 2 wordt "vijftien" vervangen door "tien".
B. Na artikel 16 wordt een nieuw artikel 16a ingevoegd, luidende:
   "Artikel 16a. ..."
C. Artikel 24 vervalt.
```

The amendment act's later articles (Artikel 2, 3, ...) may amend a second base law or
specify the in-force date. The act typically concludes with a *Memorie van Toelichting*
(explanatory memorandum), which must be excluded from instruction extraction.

### 4.2 Parser Architecture

The `AmendmentParser` operates in two passes. **Pass 1 (regex)** splits the document into
sections by `Artikel N` boundaries (after stripping explanatory-memorandum text), extracts
the target law name from the section header or preamble, splits labelled instruction blocks
(A., B., C. or Roman-numeral labels), and classifies each block against a priority-ordered
set of ~20 regex patterns covering the standard Dutch amendment constructions (repeal,
replacement, insertion, phrase substitution). **Pass 2 (LLM fallback)**, used only when a
regex-classified instruction's confidence falls below 0.70, re-sends the section to an LLM
with a structured JSON prompt; results are merged, with LLM output overriding regex output
where its confidence is higher. This pass is disabled for the benchmark in Section 6.1 to
report a clean regex-only baseline, consistent with our original evaluation methodology.

The LLM pass now supports both a local model (Qwen2.5-Coder-7B-Instruct via vLLM) and any
OpenAI-compatible hosted chat endpoint, selected by URL shape. In practice we found hosted
reasoning models require substantially larger token budgets than a plain completion model of
similar size — a fixed 512–2048 token cap silently truncated every response, since part of
the budget is consumed by hidden reasoning tokens before any answer content is emitted. We
report this as a practical deployment note for others integrating hosted LLMs into
constrained-latency legal NLP pipelines.

### 4.3 Consolidation Engine

`ConsolidationEngine` consumes `AmendmentInstruction` objects and applies them to the current
expression of the base law to produce a new `Expression` at the amendment's effective date.
Base-law resolution — mapping the amendment's raw target-law reference to a Work in the
store — uses fuzzy title matching (exact match, normalized match, then length-guarded
substring containment) rather than exact-ID lookup, because the amendment's stated law name
essentially never matches the filename-derived work ID that real ingestion produces. We
factored this matching logic into a shared module once we discovered the citation resolver
needed the identical fallback for the identical reason (Section 6.2).

---

## 5. Case-Law Integration and Knowledge Graph

### 5.1 Scraping *rechtspraak.sr*

*rechtspraak.sr* is a WordPress-based site with no listing or search API; the only reliable
enumeration mechanism is the WordPress XML sitemap, which we parse recursively (sitemap
index → per-type sub-sitemaps → individual decision URLs). This alone surfaced 900+
decisions spanning 1952–2025. Each decision page exposes clean structured metadata (court,
case number, decision and publication dates, legal area) as label/value pairs, and full
decision text as HTML — considerably cleaner input than the OCR'd legislative PDFs, since
no scanning or recognition step is involved.

### 5.2 Consideration Segmentation

Surinamese court decisions structure their legal reasoning as numbered paragraphs under a
"De beoordeling" (assessment) heading, using section.paragraph numbering (e.g., "2.1", "4.7")
rather than an explicit "r.o." (*rechtsoverweging*) label. We segment on this numbering
pattern directly; decisions without recognizable numbering (typically older or very short
judgments) are kept as a single fragment rather than discarded, so no decision's text is
lost to a structural-parsing failure. Across the 300 ingested decisions this produced 1,142
consideration-level fragments.

### 5.3 Citation Extraction from Case Law

Legislative citations within case-law text ("artikel 4 lid 2 Arbeidswet 1963") are extracted
using the identical citation resolver and extraction pipeline built for legislation-to-
legislation citations — no case-law-specific resolution logic was needed, since a citation is
a citation regardless of source document type. This yielded 526 case-to-legislation
citations across the 300-decision sample. Case-to-case citations (a decision citing another
by its site-assigned identifier, e.g. "SRU-HvJ-2019-3") use a separate lightweight regex
match, since these identifiers are specific to this one source and not part of the general
citation-resolution grammar; none were found in this sample, which we discuss as an open
question in Section 7.2 rather than assume is a parsing gap.

### 5.4 Knowledge Graph Construction

We assemble a unified graph directly from the canonical store — no additional schema or
storage layer — with one node per Work (typed `legislation` or `case_law`) and three edge
types: `AMENDS` (from `AmendmentLink`), `CITES` (legislation-to-legislation citations), and
`APPLIES` (case-to-legislation citations). The resulting graph over the full corpus has
1,623 nodes and 2,768 edges (2,322 CITES, 391 APPLIES, 55 AMENDS), with a largest connected
component of 706 nodes. The ten most-cited works are, in order: Personeelswet (civil service
law), Burgerlijk Wetboek (Civil Code), Wetboek van Strafrecht (Criminal Code), Grondwet
(Constitution), Wetboek van Koophandel (Commercial Code), and several tax and electoral
statutes — a distribution that matches expectation for a general legal system and offers a
face-validity check on the extraction pipeline independent of the benchmark in Section 6.1.

---

## 6. Evaluation

### 6.1 Citation Resolution: Synthetic Benchmark

We evaluate the citation resolver on a curated 61-case known-answer dataset spanning
citation, temporal, and gazette-reference categories. The resolver achieves a 100% pass
rate, 100% precision/recall/F1, and 91.2% raw resolution rate (the remainder being
deliberately-unresolvable negative test cases). This is unchanged from prior evaluation and
confirms the resolver's pattern coverage is sound against well-formed input.

### 6.2 Citation Resolution: Real-Corpus Linkage Gap

Synthetic-benchmark accuracy measures whether the resolver correctly identifies *that* a
reference exists and what canonical URI it should map to. It does not measure whether that
URI actually corresponds to anything in a real corpus — and for LexSR, at the time we built
the knowledge graph, it did not: **every one of 13,949 citations extracted from the corpus
had a null target work reference**, despite each having passed resolution. Three
compounding causes, uncovered by inspecting the (previously unexamined) `target_work_id`
column directly rather than the aggregate "citations resolved" count reported by the
ingestion CLI:

1. **Stale identifier scheme.** 788 works and their expressions, ingested before a URI
   prefix convention was corrected mid-project, retained the old `sr/law/...` form instead
   of `/id/law/...`; direct URI lookup naturally failed for all of them. A one-time migration
   fixed this class.
2. **Idealized vs. filename-derived identifiers.** The resolver's abbreviation registry maps
   "Grondwet" to the canonical slug `grondwet-1987` — a clean identifier reflecting how the
   corpus *should* be organized. Real ingestion, run against scraped/OCR'd source documents
   with no canonical-naming authority, instead produces IDs derived from the source filename
   (`grondwet-met-mvt-4fb9cced`). No amount of resolver accuracy against a synthetic
   benchmark closes this gap, because the gap is not in resolution logic — it is a mismatch
   between two different, independently-reasonable identifier schemes. We closed most of it
   by reusing the fuzzy title-matching fallback already built for amendment base-law
   resolution (Section 4.3) as a fallback when direct URI lookup fails.
3. **Case-law scheme not recognized.** A citation-type classifier that checks source/target
   URIs for an `/ecli/` substring to detect case-law provenance silently mis-typed every
   citation originating from a case-law fragment as `unknown`, since this corpus's actual
   case-law scheme is `/id/caselaw/...` (Section 3.2) — a straightforward but easy-to-miss
   consequence of extending a system originally built for one document type to a second.

After fixing all three, target-work resolution across the corpus rose from 0/13,949 to
2,713/15,867 (17.1%; the citation count itself grew between measurements as case-law
ingestion added citations from decision text). The remaining 83% are overwhelmingly gazette
references (*Staatsblad*/*Gouvernementsblad* citations), which are correctly extracted and
typed but cannot resolve further because the corpus does not model individual gazette issues
as first-class entities — a genuine scope boundary, not a resolution failure, and one we
flag as future work (Section 7.2) rather than paper over.

We report this gap because we believe it generalizes: a resolver validated only against a
synthetic or curated benchmark can report perfect accuracy while linking nothing in the
corpus it is meant to serve, if the benchmark's identifiers do not reflect how real
ingestion actually names things. We are not aware of this specific failure mode being
discussed in the low-resource legal NLP literature and suggest it as a checklist item for
similar projects: *measure resolution against the real corpus's actual identifiers, not just
against curated ground truth.*

### 6.3 Amendment Parsing: Coverage Over Corpus Growth

We evaluate the amendment parser (regex pass only, matching the methodology of our earlier
33-document evaluation) on all amendment documents currently in the corpus (a document may
target more than one base law, so this is evaluated per amendment document, not per
`AmendmentLink` row — the corpus has 55 links across 50 unique documents). Table 1 reports
both measurements.

| Corpus state | Amendment documents | OK (≥1 instruction extracted) | Rate |
|---|---|---|---|
| Original (curated subset) | 33 | 27 | 81.8% |
| Current (full live-scraped corpus) | 50 | 19 | 38.0% |

**Table 1.** Amendment parsing coverage before and after corpus expansion.

The drop is a second instance of the same underlying lesson as Section 6.2: the original
33-link set was disproportionately drawn from cleanly-digitised, well-OCR'd sources, while
the expanded corpus includes material from ten additional live-scraped sources with more
variable OCR quality and, in some cases, genuinely different amendment-drafting
conventions we have not yet characterized. As with the original evaluation, failures are
concentrated in cases where the operative instruction text itself is missing or garbled in
the source fragment, not in cases where legible operative text was misparsed — but we have
not yet re-run the original's per-case failure classification (OCR garbling vs. missing
text vs. novel construction) at the new scale, and flag this as immediate future work
(Section 7.3) rather than assert a cause we have not verified at this corpus size.

### 6.4 Engine Validation

Eleven amendments have been fully applied by the consolidation engine (up from 2 at the
prior evaluation) and are available for inspection in the canonical store; the remainder of
the 19 parseable-but-unapplied cases fail engine-level base-law resolution or produce
low-confidence instructions withheld pending review, rather than being blocked by parsing.

---

## 7. Discussion and Future Work

### 7.1 Limitations

**Corpus coverage and source stability.** Six of sixteen candidate scraper sources were
excluded because their configured URLs no longer resolve or the site structure has changed
— a specific instance of a general low-resource-jurisdiction problem: government sites are
maintained inconsistently and rarely expose a stable API, so scraper configurations decay
silently over time with no error signal beyond "zero documents found." Automated periodic
health-checking of scraper coverage is future infrastructure work, not yet built.

**Real-corpus linkage.** Section 6.2's 17.1% real-corpus citation linkage rate, while a large
improvement over the pre-fix 0%, remains low in absolute terms; the majority of the gap is
the un-modelled gazette-issue scope boundary rather than a resolution failure, but this
should be stated as a limitation of the current corpus's entity coverage, not treated as
solved.

**Amendment-parsing coverage.** The 38% current-corpus OK rate (Section 6.3) is a lower bar
than we would want for a production consolidation system, though it should be read alongside
the fact that "OK" here means at least one clean instruction was extracted per amendment —
many practically important amendments are simpler, single-instruction acts well within this
capability.

**Case-to-case citation coverage.** Zero case-to-case citations were found in the 300-decision
sample (Section 5.3); we do not yet know whether this reflects a genuine rarity of explicit
cross-citation in this corpus (plausible for a small jurisdiction with a correspondingly
small body of precedent) or an extraction-pattern gap, and consider this an open
methodological question rather than a settled negative result.

### 7.2 Broader Implications

Suriname shares its legislative drafting conventions (Dutch-language templates derived from
former colonial law) with the Dutch Caribbean islands (Aruba, Curaçao, Sint Maarten). The
LexSR pipeline may be directly applicable to these jurisdictions with minimal adaptation.
More broadly, the paper's central methodological point — that synthetic benchmark accuracy
and real-corpus linkage rate are different measurements that can diverge sharply — applies
to any legal knowledge system built by combining a hand-curated resolution component with
uncurated, real-world ingestion, independent of jurisdiction or language.

### 7.3 Future Work

1. **Failure-mode analysis at scale**: Re-run the original's per-case classification
   (OCR garbling vs. missing operative text vs. novel construction) across the current
   50-link amendment corpus.
2. **Gazette-issue modelling**: Represent individual *Staatsblad*/*Gouvernementsblad* issues
   as first-class entities to close the largest remaining share of the citation-linkage gap.
3. **Case-law scale-up**: Ingest the remaining 600+ decisions available on *rechtspraak.sr*
   and re-evaluate case-to-case citation coverage at that scale.
4. **Gold-standard instruction annotation**: Annotate amendment acts at instruction level
   (target article, operation type, find/replace text) for precision/recall evaluation
   beyond the current binary OK/NO_MATCH measure.
5. **Source health monitoring**: Automated detection of scraper configuration decay
   (Section 7.1) rather than manual discovery.
6. **User evaluation**: Study practitioner use of the portal and knowledge graph through a
   user study with Surinamese legal practitioners.

---

## 8. Conclusion

We presented LexSR, a pipeline for building a structured, versioned corpus of Surinamese
legislation and case law, automatically consolidating amendment acts, and constructing a
unified knowledge graph linking legislation, amendments, and case-law citations. Beyond the
system itself, this paper's central contribution is methodological: we measured, rather than
assumed, how much of our citation resolver's synthetic-benchmark accuracy (100% precision/
recall) survives contact with a real, uncurated corpus (17.1% linkage), traced the gap to a
structural mismatch between idealized and filename-derived identifiers, and report the fix.
A parallel measurement of amendment-parsing coverage across corpus growth (82% → 38%) tells
the same story from a different angle. We believe both findings generalize beyond this
jurisdiction: legal NLP systems evaluated only against curated benchmarks can silently fail
to serve the real corpora they are built for, and that gap is worth measuring directly. The
corpus (1,623 works, 45,293 fragments, 2,768 knowledge-graph edges), code, and evaluation
scripts are released under open licences to support future research on legal NLP for small
jurisdictions.

---

## References

> **✅ Verified 2026-09-06.** All 16 entries below were checked against actual publisher
> records (Springer, ACL Anthology, IOS Press, DBLP, Semantic Scholar) individually. Six
> entries in the prior draft were confirmed fabricated or wrong-attribution (nonexistent
> papers, or real authors credited with the wrong paper/venue/year) and have been replaced
> with real citations that support the same claims — see the LaTeX source
> (`latex/paper/lexsr_jurix2026.tex`) for the corresponding in-text rewrites. Two more
> (Palmirani & Vitali 2011, Vitali & Zeni 2007) had garbled titles/venues corrected to match
> the real publications. This list should still get one more independent pass before
> submission, but it is no longer placeholder-grade.

[Bench-Capon et al. 2012] Bench-Capon, T., et al. A history of AI and Law in 50 papers.
*AI & Law*, 20(3):215–319, 2012.

[Dhani et al. 2021] Dhani, J.S., Bhatt, R., Ganesan, B., Sirohi, P., and Bhatnagar, V. Similar
Cases Recommendation using Legal Knowledge Graphs. arXiv:2107.04771, 2021.

[Biagioli et al. 2004] Biagioli, C., Francesconi, E., Spinosa, P., and Taddei, M. XML
Documents Within a Legal Domain: Standards and Tools for the Italian Legislative Environment.
In *Document Analysis Systems VI (DAS 2004)*, LNCS vol. 3163, Springer, 2004.

[Boer et al. 2007] Boer, A., Winkels, R., and Vitali, F. Proposed XML standards for law:
MetaLex and LKIF. In *Proc. JURIX 2007*, IOS Press.

[Chalkidis et al. 2020] Chalkidis, I., et al. LEGAL-BERT: The muppets straight out of law
school. In *Findings of EMNLP 2020*.

[Hoekstra et al. 2007] Hoekstra, R., Breuker, J., Di Bello, M., and Boer, A. The LKIF core
ontology of basic legal concepts. In *Proc. LOAIT Workshop*, CEUR Workshop Proceedings vol.
321, 2007, pp. 43–63.

[IFLA 1998] IFLA Study Group. *Functional Requirements for Bibliographic Records*. IFLA
Publications, 1998.

[Koreeda and Manning 2021] Koreeda, Y. and Manning, C. ContractNLI: A dataset for document-
level natural language inference for contracts. In *Findings of EMNLP 2021*.

[KOOP 2022] KOOP. *Officiële bekendmakingen — wetten.overheid.nl*. Kennis- en
exploitatiecentrum voor officiële overheidspublicaties, 2022.

[Krasadakis et al. 2024] Krasadakis, P., Sakkopoulos, E., and Verykios, V.S. A Survey on
Challenges and Advances in Natural Language Processing with a Focus on Legal Informatics and
Low-Resource Languages. *Electronics*, 13(3):648, 2024.

[Lesmo et al. 2013] Lesmo, L., Mazzei, A., Palmirani, M., and Radicioni, D.P. TULSI: an NLP
system for extracting legal modificatory provisions. *Artificial Intelligence and Law*,
21:139–172, 2013.

[Niklaus et al. 2024] Niklaus, J., et al. MultiLegalPile: A 689GB Multilingual Legal Corpus.
In *Proc. ACL 2024* (Volume 1: Long Papers).

[Palmirani and Vitali 2011] Palmirani, M. and Vitali, F. Akoma-Ntoso for Legal Documents. In
Sartor, G., et al. (eds.), *Legislative XML for the Semantic Web*, Springer, 2011, pp. 75–100.

[Publications Office 2012] Publications Office of the EU. *European Legislation Identifier (ELI)*,
OJ 2012/C 325/02.

[Sheridan and Tennison 2010] Sheridan, J. and Tennison, J. Linking UK government data.
In *Proc. LDOW 2010*.

[Spinosa et al. 2009] Spinosa, P., Giardiello, G., Cherubini, M., Marchi, S., Venturi, G., and
Montemagni, S. NLP-based metadata extraction for legal text consolidation. In *Proc. ICAIL
2009*, pp. 40–49.

[Vitali and Zeni 2007] Vitali, F. and Zeni, F. Towards a country-independent data format: the
Akoma Ntoso experience. In *Proc. V Legislative XML Workshop*, Florence, 2007.
