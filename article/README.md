# Article

The LexSR paper, targeting **JURIX 2026** (full-paper deadline Sept 13, 2026 AoE).

| File | Role |
|---|---|
| `lexsr_jurix2026.pdf` | **The artifact to submit.** 11 pages: body ends p10, references start p11. |
| `lexsr_jurix2026.tex` | LaTeX source the PDF compiles from. |
| `jurix2026_paper_draft.md` | Prose source of record, kept word-for-word in sync with the `.tex`. |
| `jurix2026_submission_checklist.md` | Submission status log and verification record. |
| `IOS-Book-Article.cls`, `vancouver.bst` | IOS Press FAIA template files; must sit beside the `.tex` to compile. |

## Build

```bash
pdflatex lexsr_jurix2026.tex && pdflatex lexsr_jurix2026.tex
```

Two passes, to resolve `\ref` cross-references. A clean build is exit 0 with no errors and no
undefined references, producing 11 pages.

## House style

No en dashes and no em dashes anywhere in these files. Rewrite the sentence rather than
swapping the punctuation.

## Keeping the two sources equal

`jurix2026_paper_draft.md` and `lexsr_jurix2026.tex` must not drift. Any edit to one gets
mirrored in the other. The Markdown's section numbers are written out by hand, so they are
the part most likely to rot; the LaTeX resolves its own via `\ref`. After editing either
file, check that the resolved "Section N" mentions still match:

```bash
pdftotext lexsr_jurix2026.pdf - | grep -oE "Section [0-9]+(\.[0-9]+)?" | sort | uniq -c
grep -oE "Section [0-9]+(\.[0-9]+)?" jurix2026_paper_draft.md | sort | uniq -c
```

The two counts should be identical. Re-compile and confirm the page break after any content
edit: the body has to stay within 10 pages, and there is no room to spare.

## Related, left in place

- `../docs/research/latex/texsupport.IOS-Book-Article-master/` vendored IOS Press template,
  kept for reference.
- `../docs/research/jurix2025_*` superseded JURIX 2025 drafts.
- `../docs/research/references.md` bibliography working notes.
