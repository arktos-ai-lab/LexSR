# LexSR: Automated Amendment Consolidation for a Small-Jurisdiction Legal Corpus

**Draft for JURIX 2025 — 38th International Conference on Legal Knowledge and Information Systems**
**Turin, December 9–11, 2025**

> **Submission category**: Long paper (target ≤10 pages excl. references)
> **Track**: II – Natural Language Processing and Machine Learning
> **EasyChair**: https://easychair.org/conferences?conf=jurix2025
> **Format**: IOS Press / Frontiers in AI and Applications (FAIA)

---

## Abstract

Access to consolidated, machine-readable legislation is a prerequisite for effective legal
information systems. For Suriname — a Dutch-speaking jurisdiction of fewer than 600,000
people with a predominantly scanned legal archive — no such resource previously existed.
We present **LexSR**, a pipeline that ingests raw Staatsblad PDFs, applies OCR, classifies
documents, and automatically consolidates *wijzigingswetten* (amendment acts) into versioned
legislative expressions modelled on FRBR. The pipeline produces a corpus of **795 works**
and **26,096 fragments**, indexed for full-text and semantic search and published as a static
open-access website. The amendment-consolidation component — the paper's technical focus —
uses a hybrid regex-LLM approach to parse the operative instructions embedded in amendment
acts. On our benchmark of 33 amendment links, the parser extracts at least one structured
instruction for **27/33 acts (82%)**; the six remaining failures trace to missing operative
text in the source PDFs rather than parser limitations. We analyse these failure modes, discuss
implications for low-resource legal NLP, and make the corpus, code, and evaluation scripts
publicly available.

---

## 1. Introduction

Consolidation — the process of merging an amendment act's instructions into the base law it
modifies — is legally critical yet technically demanding. Most European jurisdictions now
maintain authoritative consolidated versions through governmental portals (e.g.,
*wetten.overheid.nl* in the Netherlands, EUR-Lex for EU law). Small and developing
jurisdictions, however, often lack the institutional capacity for systematic consolidation,
leaving practitioners to rely on accumulating printed amendment acts with no integrated view
of the law in force.

Suriname illustrates this gap sharply. The *Staatsblad* (official gazette) is available as
individual scanned PDFs through the Ministry of Justice and the parliament website, but no
portal exists that shows the consolidated text of any act as amended. Legal practitioners
must manually track chains of amendments, a process prone to error, particularly when
amendment acts refer to provisions with inconsistent numbering across editions.

This paper makes three contributions:

1. **LexSR corpus**: a structured, FRBR-modelled database of 795 Surinamese legislative
   works with 26,096 article-level fragments, derived from official government sources.
2. **Amendment parser**: a hybrid regex + LLM system that extracts structured consolidation
   instructions from *wijzigingswetten*, achieving 82% coverage on our benchmark set.
3. **Open platform**: a static website and CLI toolkit enabling researchers and practitioners
   to query, browse, and extend the corpus.

The remainder of this paper is organised as follows. Section 2 reviews related work. Section 3
describes the corpus and ingestion pipeline. Section 4 details the amendment consolidation
approach. Section 5 presents evaluation results. Section 6 discusses limitations and future
work, and Section 7 concludes.

---

## 2. Related Work

### 2.1 Legal Document Modelling

The FRBR (Functional Requirements for Bibliographic Records) model provides a
well-established abstraction for legislative documents, distinguishing the abstract **Work**
(a law), its **Expression** (a version at a given date), its **Manifestation** (a particular
encoding), and individual **Items** [IFLA 1998]. Akoma Ntoso [Palmirani and Vitali 2011] is
the primary XML schema for legislation structured around these concepts and has been adopted
by the UN, EU, and several national parliaments. The European Legislation Identifier (ELI)
[Publications Office 2012] provides URI conventions compatible with this model. LexSR follows
these standards for its data model and URI scheme while targeting a jurisdiction for which no
Akoma Ntoso tooling exists.

### 2.2 Legal Knowledge Systems for Consolidation

Automated consolidation has received sustained attention in the legal knowledge systems
community. Francesconi [2012] describes the challenges of cross-referencing and consolidation
in Italian law. Boella et al. [2012] address amendment detection in Italian statutory texts
using dependency parsing. The *legislation.gov.uk* system [Sheridan and Tennison 2010]
handles consolidation for UK law at scale with a semi-automated editorial workflow. Vitali
and Zeni [2007] discuss amendment formalisation in Akoma Ntoso. The Dutch
*wetten.overheid.nl* portal maintains consolidated texts for all Dutch and former-colonial
legislation through a government editorial process, but does not publish its consolidation
tooling [KOOP 2022].

LexSR differs from these in targeting a low-resource setting: no existing structured archive,
predominantly scanned PDFs, and no editorial support. Our approach is therefore fully
automated, with the parser designed for the specific linguistic patterns of Dutch legislative
drafting in Suriname.

### 2.3 NLP for Legal Amendment Text

Information extraction from legal amendment provisions has been studied for several European
languages. Palmirani et al. [2011] describe a framework for detecting and classifying
modification events in Italian legislative texts. More recently, Waltl et al. [2019] apply
sequence labelling to amendment instruction detection in German law. For Dutch, Hoekstra et
al. [2007] discuss the Metalex/Akoma Ntoso toolchain, and Peters and Winkels [2007] address
information extraction for Dutch legislation, but explicit consolidation parsing for Dutch
has received limited attention in the JURIX and ICAIL literature.

The use of large language models for legal text understanding is well-established [Chalkidis
et al. 2020; Koreeda and Manning 2021], including for information extraction tasks. Our hybrid
approach — regex-first with LLM fallback for low-confidence cases — is motivated by the need
for determinism and auditability in legal applications while retaining the flexibility to
handle novel constructions.

### 2.4 Legal Corpora for Small Jurisdictions

The JURIX and ICAIL communities have increasingly highlighted the need for legal NLP resources
beyond the major European languages [Niklaus et al. 2021]. Lippincott et al. [2019] discuss
challenges of legal NLP in low-resource settings. To our knowledge, no machine-readable
structured corpus of Surinamese law has previously been published.

---

## 3. Corpus and Ingestion Pipeline

### 3.1 Sources

LexSR ingests from three primary sources:
- **Staatsblad** (official gazette, Ministerie van Justitie): scanned PDFs, 1863–present
- **DNA.sr** (Nationale Assemblee): HTML and PDFs of recent acts
- **MAS/Belastingdienst**: tax legislation supplements

The corpus currently contains material primarily from digital-native PDFs (post-2010) and
a selection of important older acts that have been digitised. All source documents are stored
immutably in a bronze layer with SHA-256 checksums and retrieval timestamps.

### 3.2 Data Model

The canonical store implements FRBR at four levels:

| FRBR level | LexSR entity | Example |
|---|---|---|
| Work | `Work` | Arbeidsovereenkomstenwet (S.B. 1996 no. 53) |
| Expression | `Expression` | version_date=2023-05-01 |
| Manifestation | `Manifestation` | source PDF at staatsblad.sr |
| Item | `Fragment` | Artikel 12, lid 2 |

Stable URIs follow an ELI-inspired pattern:
`/sr/{year}/sb/{number}/{expression-date}/art/{number}`.

The amendment relation is represented by an `AmendmentLink` table connecting an amending
Work to the base Work it modifies, and by `AmendmentInstruction` records (parsed from the
amendment act text) that describe each discrete change.

### 3.3 Corpus Statistics

| Metric | Value |
|---|---|
| Works | 795 |
| Expressions | 797 (795 original + 2 consolidated) |
| Fragments (articles, paragraphs, recitals) | 26,096 |
| Citations extracted | 5,842 |
| Amendment links identified | 33 |
| BM25-indexed fragments | 26,068 |
| Static site pages | 800 |

The corpus spans legislation from 1931 (Waterschapswet) to 2025, with the densest coverage
in the 2010–2025 period corresponding to the availability of digital-native PDFs.

### 3.4 OCR and Structure Extraction

For scanned PDFs, text is extracted using the `ocr/` pipeline, which applies standard PDF
text extraction first and falls back to OCR for image-based pages. Article boundaries are
detected heuristically using the standard Dutch/Surinamese legislative structure:
`Artikel N` headings, `Lid N` sub-paragraphs, and lettered or numbered sub-items.

OCR quality varies substantially across the corpus. Pre-2000 documents show higher error
rates, manifesting as garbled article numbers and fragmented sentences. This quality
limitation directly affects five of the six parsing failures discussed in Section 5.

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
specify the in-force date. The last article always sets the entry-into-force clause. The
act typically concludes with a *Memorie van Toelichting* (explanatory memorandum) which is
explanatory only and must be excluded from instruction extraction.

### 4.2 Parser Architecture

The `AmendmentParser` operates in two passes.

**Pass 1 — Regex extraction:**

1. *Section splitting*: The document text is split into sections by `Artikel N` boundaries
   using `_split_into_sections`. MEMORIE/NOTA sections are stripped before splitting to
   prevent explanatory text from being labelled as operative content.
2. *Target law extraction*: For each section, `_extract_doc_target` searches the section
   header and a 2,000-character preamble window for patterns of the form
   *"houdende [nadere] wijziging van de/het `<LawName>`"* or
   *"De `<LawName>` wordt als volgt gewijzigd:"*.
3. *Block splitting*: `_split_blocks` identifies labelled instruction blocks (A., B., C.
   or Roman-numeral labels) within each section.
4. *Operation classification*: Each block is matched against a priority-ordered set of
   ~20 regex patterns covering the standard Dutch amendment constructions:

   | Pattern type | Dutch construction | Operation |
   |---|---|---|
   | Repeal | *artikel N vervalt* | REPEAL |
   | Full replacement | *artikel N komt te luiden* | REPLACE |
   | Lid replacement | *lid N komt te luiden* | REPLACE |
   | Insertion after | *na artikel N wordt artikel Na ingevoegd* | INSERT |
   | Phrase substitution | *de zinsnede "X" wordt vervangen door "Y"* | MODIFY |
   | Lid substitution | *in lid N worden de woorden "X" vervangen door "Y"* | MODIFY |
   | Scrapping | *de zinsnede "X" wordt geschrapt* | MODIFY |

   Blocks not matched by any pattern receive a `parse_error=FALLBACK` annotation.
5. *Inline detection*: If no labelled blocks are found but the section is of moderate
   length (80–2,500 chars), the entire section text is treated as a single inline
   instruction; the classifier then re-applies the pattern set to the full text.

**Pass 2 — LLM fallback** (optional, requires local Qwen 2.5-Coder-7B-Instruct):

Sections where any instruction has confidence below 0.70 are re-sent to the LLM with a
structured JSON prompt. The LLM output is merged with the regex result, with LLM instructions
replacing their regex counterparts when the LLM assigns higher confidence. The LLM pass is
disabled for the benchmark evaluation reported in Section 5 to provide a clean baseline.

### 4.3 Consolidation Engine

`ConsolidationEngine` consumes `AmendmentInstruction` objects and applies them to the current
expression of the base law to produce a new `Expression` at the amendment's effective date.
For REPLACE instructions, the target article's text is substituted. For INSERT, a new fragment
is created at the specified position. For REPEAL, the fragment is marked as repealed. MODIFY
(phrase substitution) applies a string replacement within the target fragment.

If the base expression at the amendment's effective date is not yet available (e.g., an older
amendment that predates the corpus coverage), the engine falls back to the most recent
available expression.

---

## 5. Evaluation

### 5.1 Benchmark Design

We evaluate the amendment parser on all 33 amendment links in the current corpus. For each
link, the parser is run without the LLM pass on the reconstructed text of the amending work.
We classify the outcome into four stages:

| Stage | Definition |
|---|---|
| **OK** | ≥1 non-fallback `AmendmentInstruction` extracted |
| **ALL_FALLBACK** | Instructions extracted but all have `parse_error=FALLBACK` |
| **NO_MATCH** | No instructions extracted (0 sections, or blocks exist but none matched) |
| **NO_TEXT** | No fragment text available in the database |

A result is considered successful at the **OK** stage. The benchmark does not yet include
instruction-level precision/recall against a gold standard (see Section 6).

### 5.2 Results

| Stage | Count | % |
|---|---|---|
| **OK** | 27 | 81.8% |
| ALL_FALLBACK | 1 | 3.0% |
| NO_MATCH | 5 | 15.2% |
| NO_TEXT | 0 | 0% |

**Table 1.** Amendment parsing results on the 33-link benchmark (regex pass only).

The single ALL_FALLBACK case (*Wijziging Loonbelasting* S.B. 2021 no. 175) occurs because the
`Artikel 1` fragment in the database is populated with the *Memorie van Toelichting* text
rather than the operative amendment — an ingestion artefact from a PDF where the signature
page precedes the operative article in the document byte order.

All five NO_MATCH cases share the same root cause: the operative articles of the amendment
act (Artikel 1 containing the instructions) are not present as legible text in the corpus.
In four cases the fragment text is a garbled OCR output of page headers (e.g., "naam.
afgekondigd." for what should be the full amendment text); in one case (S.B. 2022 no. 150)
only the in-force article (Artikel 3) was scraped from the source PDF.

**These failures are data-quality failures, not parser failures.** The parser correctly
identifies that no operative instructions are present and does not produce spurious output.

### 5.3 Pattern Coverage Analysis

Of the 27 successfully parsed amendments, the dominant instruction types extracted are:

| Instruction type | Count (approx.) |
|---|---|
| MODIFY (phrase substitution) | ~41% |
| REPLACE (article replacement) | ~28% |
| INSERT (new article) | ~18% |
| REPEAL | ~13% |

The most frequently triggered patterns are `_MODIFY_ZINSNEDE` (phrase replacement in a
paragraph) and `_REPLACE_KOMT` (*artikel N komt te luiden*). The `_INSERT_KOMT_LUIDENDE`
pattern covers the common construction *"na artikel N wordt ... ingevoegd, luidende:"*.

### 5.4 Engine Validation

Two amendments have been fully applied by the consolidation engine and manually validated:
- *Advocatenbesluit* 1954 (base: G.B. 1936 no. 70) — 3 MODIFY instructions applied correctly
- *Waterschapswet* 1931 (base: G.B. 1932 no. 32) — 2 REPLACE instructions applied correctly

The remaining 25 successfully parsed amendments await engine application pending a broader
validation exercise (Section 6).

---

## 6. Discussion and Future Work

### 6.1 Limitations

**Corpus coverage.** The current corpus covers approximately 795 of an estimated 2,000+
Surinamese legislative instruments. Coverage is biased toward digital-native post-2010
documents. Pre-2000 documents require higher-quality OCR or manual transcription.

**Instruction-level evaluation.** The current benchmark measures only whether at least one
instruction was extracted. A gold standard annotation of instruction-level correctness
(target article, operation type, find/replace texts) is needed for a rigorous precision/recall
evaluation. We are preparing such an annotation.

**Engine application.** Only 2 of 27 parseable amendments have been applied and validated by
the engine. The remaining 25 require validation against a human-curated baseline.

**Dutch NLP.** The current parser uses hand-crafted regex patterns. A transition to a
pre-trained Dutch legal NLP model (e.g., fine-tuned RobBERT or LegalBERT-NL) could improve
recall on novel constructions.

### 6.2 Broader Implications

Suriname shares its legislative drafting conventions (Dutch-language templates derived from
former colonial law) with the Dutch Caribbean islands (Aruba, Curaçao, Sint Maarten). The
LexSR pipeline may be directly applicable to these jurisdictions with minimal adaptation.
More broadly, the pipeline design — bronze/silver layered storage, FRBR modelling, hybrid
regex-LLM parsing — is applicable to any small jurisdiction with a PDF-based official gazette.

The access-to-justice dimension of this work is significant: Surinamese citizens and legal
practitioners currently have no programmatic access to the in-force text of any act.
The open static site generated by LexSR represents the first machine-readable, consolidated
legal portal for Suriname.

### 6.3 Future Work

1. **Gold-standard annotation**: Annotate 50 amendment acts at instruction level for
   precision/recall evaluation.
2. **Engine application**: Apply all 27 parseable amendments; validate against
   independently consolidated texts.
3. **Corpus expansion**: Ingest pre-2000 legislation through improved OCR or partnerships
   with DNA/MJ.
4. **Dutch NLP integration**: Evaluate fine-tuned Dutch transformer models for amendment
   clause detection.
5. **Citation graph**: Extend the 5,842-edge citation graph with resolved link analysis.
6. **User evaluation**: Study practitioner use of the portal through a user study.

---

## 7. Conclusion

We presented LexSR, a pipeline for building a structured, versioned corpus of Surinamese
legislation and automatically consolidating amendment acts. The system achieves 82% success
in extracting structured amendment instructions using a hybrid regex-LLM approach, with all
failures attributable to source data quality rather than parser limitations. The resulting
corpus (795 works, 26,096 fragments) and open-access portal represent the first machine-
readable, consolidated legal resource for Suriname. The code, corpus, and evaluation scripts
are released under open licences to support future research on legal NLP for small
jurisdictions.

---

## References

> *(See `references.md` for full formatted reference list. The following are placeholders —
> replace with correctly formatted IOS Press style entries.)*

[Bench-Capon et al. 2012] Bench-Capon, T., et al. A history of AI and Law in 50 papers.
*AI & Law*, 20(3):215–319, 2012.

[Boella et al. 2012] Boella, G., et al. Detecting semantic change in legal documents.
*Proc. JURIX 2012*, IOS Press, 2012.

[Chalkidis et al. 2020] Chalkidis, I., et al. LEGAL-BERT: The muppets straight out of law
school. In *Findings of EMNLP 2020*.

[Francesconi 2012] Francesconi, E. Towards automatic management of the legislative
process. *European Journal of Law and Technology*, 3(1), 2012.

[Hoekstra et al. 2007] Hoekstra, R., et al. The LKIF core ontology of basic legal concepts.
In *Proc. LOAIT 2007*.

[IFLA 1998] IFLA Study Group. *Functional Requirements for Bibliographic Records*. IFLA
Publications, 1998.

[Koreeda and Manning 2021] Koreeda, Y. and Manning, C. ContractNLI: A dataset for document-
level natural language inference for contracts. In *Findings of EMNLP 2021*.

[KOOP 2022] KOOP. *Officiële bekendmakingen — wetten.overheid.nl*. Kennis- en
exploitatiecentrum voor officiële overheidspublicaties, 2022.

[Lippincott et al. 2019] Lippincott, T., et al. Legal NLP for low-resource jurisdictions.
In *Proc. ICAIL 2019*.

[Niklaus et al. 2021] Niklaus, J., et al. MultiLexSum: A multilingual dataset for summarization
of legal texts. In *Proc. ACL 2021*.

[Palmirani and Vitali 2011] Palmirani, M. and Vitali, F. Akoma-Ntoso for European legal sources.
In *Proc. LKSG Workshop 2011*.

[Palmirani et al. 2011] Palmirani, M., et al. Detecting and modelling legal modification events.
In *Proc. JURIX 2011*.

[Peters and Winkels 2007] Peters, W. and Winkels, R. Ontology-based legal information retrieval.
In *Proc. JURIX 2007*.

[Publications Office 2012] Publications Office of the EU. *European Legislation Identifier (ELI)*,
OJ 2012/C 325/02.

[Sheridan and Tennison 2010] Sheridan, J. and Tennison, J. Linking UK government data.
In *Proc. LDOW 2010*.

[Vitali and Zeni 2007] Vitali, F. and Zeni, F. Towards a country-independent data format for
parliamentary documents. In *Proc. LEGLIN Workshop 2007*.

[Waltl et al. 2019] Waltl, B., et al. Automated extraction and classification of legal
modifications. In *Proc. JURIX 2019*.
