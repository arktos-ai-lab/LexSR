# JURIX 2025 Submission Checklist

**Conference**: JURIX 2025, Turin, December 9–11, 2025
**Deadline**: September 4, 2025 (abstract August 28)
**EasyChair**: https://easychair.org/conferences?conf=jurix2025
**Format**: IOS Press FAIA — download template from https://www.iospress.com/book-article-instructions

---

## Category Decision

| Category | Pages | When to choose |
|---|---|---|
| Long paper | ≤10 (excl. refs) | Full evaluation + gold-standard annotation complete |
| Short paper | ≤5 (excl. refs) | Current state — 82% parsing, 2 engine validations |
| Poster | ≤2 | System demo only |

**Recommended now**: **Short paper** — the corpus + parsing result is a solid preliminary
contribution. Upgrade to long paper if you complete the gold-standard annotation before
September 4.

---

## What Is Ready Now

- [x] System architecture described and implemented
- [x] Corpus statistics (795 works, 26,096 fragments)
- [x] Amendment parser (27/33 = 82% benchmark)
- [x] Failure mode analysis (all 6 failures are data quality, not parser)
- [x] Pattern type breakdown (MODIFY ~41%, REPLACE ~28%, INSERT ~18%, REPEAL ~13%)
- [x] Two manually validated engine applications (Advocatenbesluit, Waterschapswet)
- [x] Open-access static website
- [x] CLI toolkit + open source code

---

## What Still Needs to Be Done

### Must-have for any submission

- [ ] **Convert to IOS Press LaTeX format**
  - Download: https://www.iospress.com/book-article-instructions
  - Template: `IOS-Book-Article.zip`
  - Compile to PDF; check page count

- [ ] **Author information** (single-blind — include names/affiliation)

- [ ] **Fix placeholder references**
  - Verify all citations in Section 2 are real papers with correct details
  - Confirm Waltl et al. 2019 JURIX paper title and proceedings
  - Add any missing JURIX/ICAIL/AI&Law citations (reviewers will check)
  - Format as IOS Press bibliography style

- [ ] **Verify corpus numbers are final**
  - Re-run `python -m lexsr stats` before submission to confirm 795/797/26096
  - Table 1 numbers must match what the code produces

### Strongly recommended for long paper

- [ ] **Gold-standard instruction annotation**
  - Annotate 20–30 amendment acts at instruction level
  - For each instruction: target article, operation type, find text, replace text
  - Measure precision and recall against parser output
  - This is the biggest gap — currently only document-level (OK/not OK)

- [ ] **Apply all 27 parseable amendments through the engine**
  - Validate 3–5 more against independently consolidated texts
  - Report instruction-level application accuracy

- [ ] **Comparison table with related systems**
  - wetten.overheid.nl (Dutch): editorial, not automated
  - EUR-Lex (EU): XML-native, different language
  - Boella et al. 2012 / Waltl et al. 2019 systems: different jurisdiction/language
  - Shows where LexSR fits in the landscape

### Nice to have

- [ ] **Qualitative failure analysis with 2–3 example failure cases**
  - Show the actual fragment text that caused the failure
  - Explain why the OCR produced garbage

- [ ] **Dutch NLP model comparison**
  - Run a fine-tuned Dutch/legal BERT model on the same 33 amendments
  - Even a negative result (regex ≥ BERT for this task) is publishable

- [ ] **Search evaluation**
  - Prepare 10–15 natural language queries with relevant-document judgments
  - Run BM25 and vector search; compute MRR@10
  - Adds the "information retrieval" angle to the paper

---

## Key Reviewer Concerns to Address

Based on JURIX reviewer expectations:

1. **Novelty**: Clarify that no structured Surinamese legal corpus previously existed.
   The low-resource small-jurisdiction angle is the primary novelty claim.

2. **JURIX/ICAIL literature**: Reviewers will verify that you cite the relevant JURIX
   and ICAIL papers. Check proceedings of JURIX 2019–2024 and ICAIL 2019–2023 for any
   work on amendment parsing or consolidation. Add missing citations.

3. **Evaluation rigour**: The current 82% is document-level (did we extract anything?).
   Reviewers may push back that this is not true precision/recall. Be explicit in the
   paper that this is a *coverage* metric, and frame the gold-standard annotation as
   future work with a concrete plan.

4. **Reproducibility**: The paper should state whether the corpus and code are publicly
   available (GitHub URL). If you want reviewers to trust the numbers, the DB must be
   available or a sample must be released.

5. **Language specificity**: State clearly that the regex patterns are Surinamese/Dutch
   legislative style and discuss transferability to other Dutch-language jurisdictions
   (Aruba, Curaçao, Sint Maarten).

---

## Timeline (working backward from September 4)

| Date | Milestone |
|---|---|
| **Aug 1** | LaTeX draft compiled; all references verified |
| **Aug 10** | Gold-standard annotation of 20 acts completed |
| **Aug 15** | Precision/recall numbers computed; Section 5 updated |
| **Aug 20** | Internal review by co-author(s) |
| **Aug 28** | **Abstract submitted to EasyChair** (recommended) |
| **Sep 1** | Final paper review |
| **Sep 4** | **Paper submitted to EasyChair** |

---

## Submission Instructions

1. Register at https://easychair.org/conferences?conf=jurix2025
2. Select paper category (long/short/poster) at submission time
3. Upload PDF compiled from IOS Press template
4. Enter title, abstract, author list, and topic keywords
5. Camera-ready deadline if accepted: **October 15, 2025**

---

## Title Options

1. **"LexSR: Automated Amendment Consolidation for Surinamese Legislation"** ← current draft
2. "Building a Legal Knowledge Base for a Small Jurisdiction: Amendment Parsing for Surinamese Law"
3. "Hybrid Regex-LLM Amendment Consolidation for a Low-Resource Dutch Legal Corpus"

Option 1 is cleanest and most searchable. Option 3 emphasises the method if you add more
LLM evaluation.

---

## Potential Co-authors / Reviewers to Recruit

Before submitting, consider asking:
- A Surinamese legal scholar to validate the corpus accuracy and practical relevance
- A Dutch NLP researcher to validate the linguistic analysis
- A JURIX community member for a pre-submission review

This is especially important for the "added value" criterion — a legal practitioner who
confirms the access-to-justice impact would significantly strengthen the paper.
