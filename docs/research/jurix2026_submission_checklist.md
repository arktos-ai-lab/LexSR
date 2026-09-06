# JURIX 2026 Submission Checklist (superseded — see note)

**JURIX 2026's full-paper deadline (Sept 5, 2026 AoE) was missed** — this checklist's original
target. Retargeting to the *Artificial Intelligence and Law* journal (Springer, rolling
submission, no deadline) as the primary next venue; JURIX 2027 and ICAIL 2027 are possible
conference alternatives once their CFPs post (neither had one as of 2026-09-06). The content
below is kept because the underlying work items were real and mostly still apply — only the
venue and its deadline have changed.

**Format**: IOS Press FAIA — template at https://www.iospress.com/book-article-instructions
(also compatible with AI & Law journal submission)
**Review**: Real author names/affiliations required (not double-blind)

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

- [x] **Author information** — filled in 2026-09-06: Ernst van Gassen, Independent researcher,
      evg.gassen@gmail.com. `\author[A]{...}` / `\address[A]{...}` in
      `docs/research/latex/paper/lexsr_jurix2026.tex`.
- [x] **Convert to IOS Press LaTeX format.** Done —
      `docs/research/latex/paper/lexsr_jurix2026.tex`, using the real IOS-Book-Article.cls
      template (vendored at `docs/research/latex/texsupport.IOS-Book-Article-master/` for
      reference). Compiles cleanly with `pdflatex` (2 passes, no errors, no undefined
      references) to `lexsr_jurix2026.pdf`: **11 pages total, body ends on page 10, references
      start cleanly on page 11** — fits the 10-page (excl. references) long-paper limit with
      no room to spare. If any more content gets added, something else needs to be trimmed to
      stay under the limit; re-compile and check the page break after any edit.
- [x] **Fixed the reference list — 2026-09-06.** All 16 citations checked individually against
      real publisher records (Springer, ACL Anthology, IOS Press, DBLP, Semantic Scholar).
      **6 of 16 were confirmed fabricated or wrong-attribution** (Boella et al. 2012 "Detecting
      semantic change," Palmirani et al. 2011 "Detecting and modelling legal modification
      events," Peters & Winkels 2007 "Ontology-based legal information retrieval," Waltl et al.
      2019, Lippincott et al. 2019, Francesconi 2012's exact title/venue, and Niklaus et al.
      2021's "MultiLexSum" — real paper, wrong authors/venue/year) — replaced with real papers
      supporting the same claims (Spinosa et al. 2009, Lesmo/Mazzei/Palmirani et al. 2013
      TULSI, Boer/Winkels/Vitali 2007, Krasadakis et al. 2024, Biagioli/Francesconi et al.
      2004, Niklaus et al. 2024 MultiLegalPile). 2 more (Palmirani & Vitali 2011, Vitali &
      Zeni 2007) had garbled titles/venues corrected. Section 2.3's KG-citation gap closed
      with Dhani et al. 2021. Every rewritten in-text sentence now accurately describes what
      its real citation actually found — this was not just a bibliography-formatting pass;
      several fabricated citations also carried fabricated content claims in the prose. One
      more independent pass before submission is still recommended, but this is no longer
      placeholder-grade. See `jurix2026_paper_draft.md`'s References section for the full
      before/after record.
- [x] **Corpus numbers re-verified fresh — 2026-09-06.** Ran `python -m lexsr stats`,
      `benchmark`, and `build-graph`, plus a direct DB query matching the paper's own
      methodology for the 17.1% figure. Every headline number in the paper matched exactly:
      1,623 works, 45,293 fragments, 15,867 citations, 2,713/15,867 (17.1%) resolved, 100%
      benchmark P/R/F1 with 91.2% raw resolution, 2,768 KG edges. Nothing had drifted despite
      the corpus still actively growing. Re-run this same check again immediately before
      whatever submission actually happens, since more time will have passed.

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
