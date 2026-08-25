# JURIX 2026 Submission Checklist

**Conference**: JURIX 2026, 39th International Conference on Legal Knowledge and Information Systems, Toulouse, December 8–10, 2026
**Deadlines**: Abstract (recommended, not mandatory) August 28, 2026 — Full paper September 5, 2026 (AoE)
**CFP**: https://www.irit.fr/jurix2026/call-for-papers/
**Format**: IOS Press FAIA — template at https://www.iospress.com/book-article-instructions
**Review**: Single-blind (real author names/affiliations required in the submission)

Supersedes `jurix2025_submission_checklist.md` (JURIX 2025 already took place; that draft
targeted a deadline that has passed). This checklist tracks `jurix2026_paper_draft.md`.

---

## Category Decision

| Category | Pages (excl. refs) | When to choose |
|---|---|---|
| Long paper | ≤10 | Full system + two honest evaluations complete — **this is what we have** |
| Short paper | ≤5 | Fallback if the long draft can't be trimmed to 10pp in time |
| Poster | ≤2 | System demo only — not a fit given the evaluation content |

**Current draft targets long paper.** Content-complete and page-count-verified in the actual
IOS Press LaTeX layout: body is exactly 10 pages, references start on page 11. No margin
left — see the LaTeX conversion item below before adding any more content.

---

## What Is Ready Now

- [x] System architecture described and implemented (legislation + case law + KG)
- [x] Corpus statistics, verified against `python -m lexsr stats` at draft time
      (1,623 works: 1,323 legislative + 300 case law; 45,293 fragments)
- [x] Amendment parser evaluated at two corpus sizes (33→50 documents, 82%→38%)
- [x] Citation resolver evaluated on the 61-case synthetic benchmark (100% P/R/F1)
- [x] **Real-corpus citation-linkage measurement** (0% → 17.1% target-work resolution,
      with root-cause analysis of all three contributing bugs and the fix) — this is the
      paper's most defensible, differentiated contribution; it's a real finding with a
      verifiable before/after number, not a claimed improvement
- [x] Knowledge graph construction and statistics (1,623 nodes, 2,768 edges, most-cited
      works sanity-checked by inspection)
- [x] Open-access static website and CLI toolkit
- [x] Draft written end-to-end (abstract through conclusion)

## What Still Needs to Be Done — Must-Have

- [ ] **Author information**: single-blind — replace `[AUTHOR NAME(S)]` / `[AFFILIATION(S)]`
      placeholders in the draft header with real names/affiliations/emails.
      In the LaTeX source: `docs/research/latex/paper/lexsr_jurix2026.tex`, the
      `\author[A]{...}` / `\address[A]{...}` lines near the top.
- [x] **Convert to IOS Press LaTeX format.** Done —
      `docs/research/latex/paper/lexsr_jurix2026.tex`, using the real IOS-Book-Article.cls
      template (vendored at `docs/research/latex/texsupport.IOS-Book-Article-master/` for
      reference). Compiles cleanly with `pdflatex` (2 passes, no errors, no undefined
      references) to `lexsr_jurix2026.pdf`: **11 pages total, body ends on page 10, references
      start cleanly on page 11** — fits the 10-page (excl. references) long-paper limit with
      no room to spare. If any more content gets added, something else needs to be trimmed to
      stay under the limit; re-compile and check the page break after any edit.
- [ ] **Fix the reference list.** Every citation in `## References` is flagged
      `UNVERIFIED PLACEHOLDER` in the draft itself — carried over from the JURIX 2025 draft
      and never independently checked. Before submission:
  - Verify every entry's title/venue/year/pages against the actual publication
  - Add real citations for Section 2.3 (Legal Knowledge Graphs and Citation Networks) —
    currently only cites Bench-Capon et al. 2012 generically; needs specific KG/citation-
    network papers from JURIX/ICAIL/AI&Law
  - Format per IOS Press bibliography style
- [ ] **Re-verify all corpus numbers immediately before submission.** Run
      `python -m lexsr stats`, `python -m lexsr benchmark`, and `python -m lexsr build-graph`
      fresh and confirm Table values in Sections 3.3, 6.1–6.4 still match — the corpus is
      still being actively grown (case-law ingestion has only covered 300 of 900+ available
      decisions; the 6 broken scrapers may get fixed) and stale numbers in a submitted paper
      are a correctness problem, not just a formatting one.

## Strongly Recommended, Time Permitting

- [ ] **Amendment-parsing failure classification at the new corpus size** (Section 6.3/7.3
      item 1 explicitly flags this as NOT yet done — the draft is honest that it doesn't know
      *why* the 38% figure is lower, only that it is). Doing this before submission would let
      Section 6.3 make a stronger, verified claim instead of a plausible-but-unconfirmed one.
- [ ] **Gold-standard instruction annotation** for amendment parsing precision/recall
      (same open item as the 2025 draft — still not done).
- [ ] Have a second reader sanity-check the case-law consideration-segmentation examples
      against real *rechtspraak.sr* pages before claiming the regex pattern generalizes.

## Explicitly Not Attempted (documented as future work in the draft, don't silently claim otherwise)

- Case-to-case citation extraction found zero matches in the 300-decision sample; the draft
  states this is unresolved (rarity vs. extraction gap), not fixed.
- Gazette-issue entities are not modelled; ~83% of extracted citations that don't resolve to
  a work are gazette references, and the draft says so plainly rather than folding them into
  a rosier aggregate resolution number.
- Six of sixteen government scraper sources remain broken (wrong/guessed URLs); not fixed as
  part of this paper, documented as a limitation instead.
