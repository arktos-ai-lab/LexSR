# JURIX 2026 Submission Checklist

**Update 2026-09-12: JURIX 2026's full-paper deadline was extended to Sept 13, 2026 AoE.**
JURIX 2026 is back on as the primary target (the original Sept 5, 2026 AoE deadline had been
missed, and this checklist briefly retargeted to the *Artificial Intelligence and Law* journal
as a fallback. That fallback is still available if this window closes, but is no longer the
plan). All work items below were completed against the original deadline and re-verified fresh
on 2026-09-12; nothing further is blocking submission.

**Format**: IOS Press FAIA, template at https://www.iospress.com/book-article-instructions
(also compatible with AI & Law journal submission)
**Review**: Real author names/affiliations required (not double-blind)

Supersedes `../docs/research/jurix2025_submission_checklist.md` (JURIX 2025 already took place; that draft
targeted a deadline that has passed). This checklist tracks `jurix2026_paper_draft.md`.

---

## Category Decision

| Category | Pages (excl. refs) | When to choose |
|---|---|---|
| Long paper | ≤10 | Full system + two honest evaluations complete (**this is what we have**) |
| Short paper | ≤5 | Fallback if the long draft can't be trimmed to 10pp in time |
| Poster | ≤2 | System demo only; not a fit given the evaluation content |

**Current draft targets long paper.** Content-complete and page-count-verified in the actual
IOS Press LaTeX layout: body is exactly 10 pages, references start on page 11. No margin
left, so see the LaTeX conversion item below before adding any more content.

---

## What Is Ready Now

- [x] System architecture described and implemented (legislation + case law + KG)
- [x] Corpus statistics, verified against `python -m lexsr stats` at draft time
      (1,623 works: 1,323 legislative + 300 case law; 45,293 fragments)
- [x] Amendment parser evaluated at two corpus sizes (33→50 documents, 82%→38%)
- [x] Citation resolver evaluated on the 61-case synthetic benchmark (100% P/R/F1)
- [x] **Real-corpus citation-linkage measurement** (0% → 17.1% target-work resolution,
      with root-cause analysis of all three contributing bugs and the fix). This is the
      paper's most defensible, differentiated contribution; it is a real finding with a
      verifiable before/after number, not a claimed improvement
- [x] Knowledge graph construction and statistics (1,623 nodes, 2,768 edges, most-cited
      works sanity-checked by inspection)
- [x] Open-access static website and CLI toolkit
- [x] Draft written end-to-end (abstract through conclusion)

## What Still Needs to Be Done: Must-Have

- [x] **Author information**, filled in 2026-09-06, affiliation corrected 2026-09-13:
      Ernst van Gassen, **Independent researcher at Arktos AI Lab**, evg.gassen@gmail.com.
      `\author[A]{...}` / `\address[A]{...}` in `article/lexsr_jurix2026.tex`. The
      affiliation previously read bare "Independent researcher".
      **ORCID 0009-0000-0314-6441 is deliberately not in the PDF.** Adding it to the
      corresponding-author footnote cost just enough vertical space to push the Conclusion
      onto page 11, which breaks the 10-page (excl. references) limit; it was reverted and
      the page break re-verified. Enter the ORCID in the submission form instead. This is a
      concrete demonstration of the "no room to spare" warning below: a single extra
      footnote line overflows the paper.
- [x] **Convert to IOS Press LaTeX format.** Done, at
      `article/lexsr_jurix2026.tex`, using the real IOS-Book-Article.cls
      template (vendored at `docs/research/latex/texsupport.IOS-Book-Article-master/` for
      reference). Compiles cleanly with `pdflatex` (2 passes, no errors, no undefined
      references) to `lexsr_jurix2026.pdf`: **11 pages total, body ends on page 10, references
      start cleanly on page 11**, fitting the 10-page (excl. references) long-paper limit with
      no room to spare. If any more content gets added, something else needs to be trimmed to
      stay under the limit; re-compile and check the page break after any edit.
- [x] **Fixed the reference list, 2026-09-06.** All 16 citations checked individually against
      real publisher records (Springer, ACL Anthology, IOS Press, DBLP, Semantic Scholar).
      **6 of 16 were confirmed fabricated or wrong-attribution** (Boella et al. 2012 "Detecting
      semantic change," Palmirani et al. 2011 "Detecting and modelling legal modification
      events," Peters & Winkels 2007 "Ontology-based legal information retrieval," Waltl et al.
      2019, Lippincott et al. 2019, Francesconi 2012's exact title/venue, and Niklaus et al.
      2021's "MultiLexSum" (real paper, wrong authors/venue/year)), replaced with real papers
      supporting the same claims (Spinosa et al. 2009, Lesmo/Mazzei/Palmirani et al. 2013
      TULSI, Boer/Winkels/Vitali 2007, Krasadakis et al. 2024, Biagioli/Francesconi et al.
      2004, Niklaus et al. 2024 MultiLegalPile). 2 more (Palmirani & Vitali 2011, Vitali &
      Zeni 2007) had garbled titles/venues corrected. Section 2.3's KG-citation gap closed
      with Dhani et al. 2021. Every rewritten in-text sentence now accurately describes what
      its real citation actually found. This was not just a bibliography-formatting pass;
      several fabricated citations also carried fabricated content claims in the prose. One
      more independent pass before submission is still recommended, but this is no longer
      placeholder-grade. See `jurix2026_paper_draft.md`'s References section for the full
      before/after record.
- [x] **Corpus numbers re-verified fresh, 2026-09-06.** Ran `python -m lexsr stats`,
      `benchmark`, and `build-graph`, plus a direct DB query matching the paper's own
      methodology for the 17.1% figure. Every headline number in the paper matched exactly:
      1,623 works, 45,293 fragments, 15,867 citations, 2,713/15,867 (17.1%) resolved, 100%
      benchmark P/R/F1 with 91.2% raw resolution, 2,768 KG edges. Nothing had drifted despite
      the corpus still actively growing. Re-run this same check again immediately before
      whatever submission actually happens, since more time will have passed.
- [x] **Corpus numbers re-re-verified fresh, 2026-09-12** (deadline-extension re-check).
      Same commands, same direct DB query: 1,623 works, 45,293 fragments, 15,867 citations,
      2,713/15,867 (17.1%) resolved, 100% benchmark P/R/F1 (91.2% raw resolution), 2,768 KG
      edges. Zero drift over the six days. `unresolved_references` table read 0 in `stats`
      output. That is a different, unpopulated legacy table, not the target-work-resolution
      metric the paper reports; confirmed via direct SQL query on `citations.target_work_id`
      that the 17.1% figure is unaffected.
- [x] **LaTeX recompiled clean, 2026-09-12.** Two `pdflatex` passes, exit 0, no errors, no
      undefined references (only cosmetic hyperref/float warnings, pre-existing). Output is
      11 pages: body ends on page 10 (Conclusion), References starts cleanly on page 11;
      layout unchanged since 2026-09-06.
- [x] **Independent second citation pass, 2026-09-12.** Web-verified 6 of the 17 references
      against live sources (arXiv, ACL Anthology, Springer, MDPI/DOI, DBLP), prioritizing the
      ones most likely to be wrong: Dhani et al. 2021 (arXiv:2107.04771), Krasadakis et al.
      2024 (Electronics 13(3):648), Biagioli/Francesconi/Spinosa/Taddei 2004 (DAS 2004, LNCS
      3163), Niklaus et al. 2024 MultiLegalPile (ACL 2024, DOI 10.18653/v1/2024.acl-long.805),
      Lesmo/Mazzei/Palmirani/Radicioni TULSI (AI & Law 2013;21:139-172), and Boer/Winkels/
      Vitali MetaLex/LKIF (JURIX 2007). All six confirmed real with matching authors, titles,
      venues, and years. No fabrications found in this sample; combined with the exhaustive
      2026-09-06 pass (all 16 then-references checked individually), this satisfies the "one
      more independent pass" recommendation below.
- [x] **No leftover placeholders.** Grepped the LaTeX source for TODO/FIXME/XXX/placeholder/
      lorem-ipsum/empty-author-block markers; none found.
- [x] **Style pass and file sync, 2026-09-13.** House style is now: no en dashes, no em
      dashes anywhere in the paper files. Removed all 32 em dashes and 4 en dashes from the
      LaTeX source by rewriting the affected sentences (commas, colons, semicolons,
      parentheses, or sentence splits as the clause required) rather than swapping
      punctuation. The title lost its dash and was restructured to
      **"LexSR: Consolidating Legislation and Linking Case Law to Build a Legal Knowledge
      Graph for Suriname, a Low-Resource Jurisdiction"**, keeping every element of the
      original. Also swapped three mild AI-register tells ("increasingly highlighted the
      need for" to "repeatedly called for"; a duplicated "well-established"; and a real
      redundancy in Section 2.3 where "built for well-resourced jurisdictions *with existing
      structured data* ... but these *rely on structured source data*" said the same thing
      twice). Recompiled clean: exit 0, no errors, no undefined references, still 11 pages
      with the body ending on page 10 and References starting on page 11.
- [x] **`jurix2026_paper_draft.md` re-synced to the LaTeX source, 2026-09-13.** The Markdown
      had drifted and is now the prose source of record kept equal to the `.tex`. Fixed in
      the Markdown: same style pass as above; three wrong cross-references (Section 6.1 to
      6.3 for the parser benchmark, 7.2 to 7.1 for the case-to-case open question, 7.2 to
      7.3 for gazette future work) that the LaTeX got right automatically via `\ref`;
      "33-link set" and "50-link corpus" corrected to "33-document"/"50-document" (the
      evaluation is per document, not per `AmendmentLink`); `{official-id}` to `{id}` in the
      URI pattern; and the References note still claiming "16 entries" when there are 17,
      now also recording the 2026-09-12 second pass. Verified mechanically, not by eye:
      word-level diff of the two files' body prose is **97.4% identical**, and every
      remaining difference is markup (LaTeX `100\%` tokenizing as `100 %`, `\label`/`\ref`
      names, list numerals, the `\c{c}` cedilla macro in Curaçao) rather than wording. The resolved
      "Section N" cross-references now have **identical distributions** in the compiled PDF
      and the Markdown. Only genuine remaining difference: two LaTeX-only float lead-ins
      ("shown in Table 1", "Table 2 summarizes the corpus") that Markdown does not need
      because its tables sit inline.

- [x] **De-engineered the register of the linkage-gap material, 2026-09-13.** The audit read
      as a defect log ("we trace this gap ... and report the fix", three numbered bugs, "after
      fixing all three"), which is the wrong voice for a paper. The *finding* is kept, because
      it is the paper's differentiated contribution; only the framing changed, and the
      rewrite came out length-neutral with the page break re-verified. Specifically:
      "report the fix" became "show that reconciling the two recovers most of the shortfall";
      "traced"/"we closed most of it" became "attribute"/"reconciling them requires";
      "After fixing all three" became "With all three reconciled"; "pre-fix 0%" became
      "the unreconciled 0%"; contribution 4 dropped "honest" and now promises "an account of
      why the two diverge". In Section 6.2 the three causes are no longer presented as peers:
      the identifier-mismatch cause is the generalizable one and keeps its full treatment,
      while the superseded URI prefix and the `/ecli/` provenance check are compressed to
      two lines each and reframed as corpus hygiene rather than narrated as bugs found. The
      OCR paragraph in Section 3.4 got the same treatment: the missing Dutch Tesseract pack
      is now stated as a silent failure mode of language-pack availability, not as a mistake
      that "was caught".
      **Do not reintroduce defect-log voice here.** The claim is that benchmark-only
      evaluation can certify a component that links almost nothing in its real corpus; the
      implementation causes are evidence for that claim, not the subject of the section.
- [x] **Removed self-declared candour, 2026-09-13.** The word "honest" appeared twice as
      editorial self-praise ("an honest accuracy audit", "a second honest signal") and is now
      gone from both files; declaring your own candour reads as amateur and invites a
      reviewer to test the claim. The abstract's 82%/38% sentence is now "a second instance
      of the same divergence between curated-subset accuracy and real-corpus performance",
      which ties the number to the paper's thesis instead of editorialising about it. Also
      dropped "rather than paper over" and softened "the same underlying lesson" to "the same
      pattern". **The 82%/38% number itself stays.** It is a measured coverage result, not a
      defect report, and suppressing a known drop in your own system's performance would be
      the genuinely indefensible move. State results plainly; do not narrate your virtue in
      reporting them.

- [x] **Removed seven appeals to an uncitable "prior evaluation", 2026-09-13.** The paper
      repeatedly measured itself against "prior evaluation", "the original evaluation",
      "our earlier 33-document evaluation" and "the original's per-case classification"
      without ever saying what that work was. It was the JURIX 2025 draft, which was
      **never submitted** (its must-do items in `../docs/research/jurix2025_submission_checklist.md`
      are all still unchecked), so there is no publication to cite and a reviewer asking
      "which prior evaluation?" would have got no answer. All seven now describe the same
      thing self-containedly as an earlier measurement on a smaller corpus made during this
      project ("when only 33 amendment documents had been ingested", "as at the smaller
      size"), which needs no citation because it is this paper's own history. Section 6.1
      also lost the appeal entirely: "This is unchanged from prior evaluation and confirms
      the resolver's pattern coverage is sound" became "Pattern coverage is therefore sound
      against well-formed input, which is precisely the condition the next section removes",
      which stands on its own evidence and sets up Section 6.2 instead of leaning backwards.
      **Never reference the 2025 draft as prior work.** It is unpublished; treat the earlier
      numbers as earlier states of this project, not as a citable result.

## Strongly Recommended, Time Permitting

- [ ] **Amendment-parsing failure classification at the new corpus size** (Section 6.3/7.3
      item 1 explicitly flags this as NOT yet done; the draft is honest that it does not know
      *why* the 38% figure is lower, only that it is). Doing this before submission would let
      Section 6.3 make a stronger, verified claim instead of a plausible-but-unconfirmed one.
- [ ] **Gold-standard instruction annotation** for amendment parsing precision/recall
      (same open item as the 2025 draft; still not done).
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
