"""
ConsolidationEngine — apply AmendmentInstructions to the CanonicalStore.

Given a classified amendment document (from the classifier) whose
AmendmentInstructions have been extracted (by the parser), this engine:

  1. Resolves the target base law (raw reference → Work.id)
  2. Loads the latest Expression + all its Fragments
  3. Applies each instruction in document order:
       REPEAL  → marks fragment text as "[Vervallen]", sets status=REPEALED
       REPLACE → updates fragment text (article or paragraph)
       INSERT  → creates a new Fragment with adjusted position
       MODIFY  → applies find/replace within fragment text
  4. Creates a new Expression with version_date = effective date of the amendment
  5. Persists new Expression + all changed/new Fragments
  6. Records a VersionDiff linking the amendment work to the new Expression
  7. Marks the AmendmentLink as resolved

Unresolvable instructions (article not found in store, confidence < threshold)
are written to a review queue rather than applied blindly.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from ..core.models import (
    AmendmentLink,
    Citation,
    CitationType,
    DocumentStatus,
    Expression,
    Fragment,
    FragmentType,
    TemporalExtent,
    Work,
)
from ..core.store import CanonicalStore
from ..core.versioning import VersionDiff
from .amendment import AmendmentInstruction, OperationType, ParsedAmendment

logger = logging.getLogger(__name__)

# Instructions below this confidence are queued for human review
REVIEW_THRESHOLD = 0.70

# Text inserted for repealed articles
REPEALED_PLACEHOLDER = "[Vervallen]"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ApplicationResult:
    """Outcome of applying one AmendmentInstruction."""
    instruction: AmendmentInstruction
    applied: bool
    reason: str = ""
    fragment_id: Optional[str] = None   # created or modified fragment


@dataclass
class ConsolidationResult:
    """Outcome of a full consolidation run for one amendment."""
    amendment_work_id: str
    base_work_id: Optional[str]
    new_expression_id: Optional[str] = None
    applied: List[ApplicationResult] = field(default_factory=list)
    skipped: List[ApplicationResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.new_expression_id is not None and not self.errors

    def summary(self) -> Dict[str, Any]:
        return {
            "amendment_work_id": self.amendment_work_id,
            "base_work_id": self.base_work_id,
            "new_expression_id": self.new_expression_id,
            "applied": len(self.applied),
            "skipped": len(self.skipped),
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Fragment addressing helpers
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    """Normalize an article number for fuzzy matching."""
    return re.sub(r'\s+', '', s.strip().lower().lstrip('0')) or s.strip().lower()


def _find_article(
    fragments: List[Fragment], article_nr: str
) -> Optional[Fragment]:
    """Find an ARTICLE fragment by number (fuzzy: strip leading zeros, lowercase)."""
    target = _norm(article_nr)
    for f in fragments:
        if f.fragment_type == FragmentType.ARTICLE and _norm(f.number) == target:
            return f
    return None


def _find_paragraph(
    fragments: List[Fragment], article_nr: str, paragraph_nr: str
) -> Optional[Fragment]:
    """Find a PARAGRAPH fragment inside an article."""
    article = _find_article(fragments, article_nr)
    if not article:
        return None
    target_p = _norm(paragraph_nr)
    for f in fragments:
        if (f.fragment_type == FragmentType.PARAGRAPH
                and f.parent_fragment_id == article.id
                and _norm(f.number) == target_p):
            return f
    return None


def _new_fragment_id(base_id: str, suffix: str) -> str:
    """Derive a stable new fragment ID from an existing one."""
    raw = f"{base_id}:{suffix}"
    return "f-" + hashlib.sha1(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Base law resolver
# ---------------------------------------------------------------------------

_STOP_WORDS = re.compile(r'\b(?:de|het|van|der|den|een|the)\b', re.I)


def _normalize_ref(raw: str) -> str:
    """Normalize a law reference for fuzzy matching."""
    s = _STOP_WORDS.sub('', raw).strip()
    return re.sub(r'\s+', ' ', s.lower())


def _resolve_base_work(
    raw_ref: str, store: CanonicalStore
) -> Optional[Work]:
    """
    Resolve a raw law reference (e.g. "de Arbeidswet 1963") to a Work.

    Strategy (in order):
    1. Exact title match
    2. Normalized title (strip stop words)
    3. Substring: normalized ref ⊆ normalized title
    4. Year + keyword match
    """
    norm_ref = _normalize_ref(raw_ref)

    works = store.list_works(limit=10_000)

    # 1 + 2: exact or normalized title match
    for work in works:
        if work.title.strip().lower() == raw_ref.strip().lower():
            return work
        if _normalize_ref(work.title) == norm_ref:
            return work

    # 3: substring — ref is contained in title or title is contained in ref.
    # A very short normalized string (OCR noise, a stray single letter) is a
    # substring of almost everything, so require a minimum length before
    # trusting either direction of the containment check.
    MIN_SUBSTRING_LEN = 4
    if len(norm_ref) >= MIN_SUBSTRING_LEN:
        for work in works:
            norm_title = _normalize_ref(work.title)
            if len(norm_title) < MIN_SUBSTRING_LEN:
                continue
            if norm_ref in norm_title or norm_title in norm_ref:
                return work

    # 4: year + at least 2 distinctive words
    year_m = re.search(r'\b(\d{4})\b', raw_ref)
    if year_m:
        year = year_m.group(1)
        words = [w for w in norm_ref.split() if len(w) > 3]
        for work in works:
            if year in work.title:
                norm_t = _normalize_ref(work.title)
                if any(w in norm_t for w in words):
                    return work

    logger.warning("Could not resolve base law: %r", raw_ref)
    return None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ConsolidationEngine:
    """
    Apply a ParsedAmendment to the CanonicalStore, producing a new Expression.

    Usage
    -----
        engine = ConsolidationEngine(store)
        result = engine.consolidate(
            parsed_amendment=parsed,
            amendment_work_id="w-sb-1975-100",
            effective_date=date(1976, 1, 1),
        )
        print(result.summary())
    """

    def __init__(self, store: CanonicalStore) -> None:
        self.store = store

    # ── Public API ─────────────────────────────────────────────────────────

    def consolidate(
        self,
        parsed_amendment: ParsedAmendment,
        amendment_work_id: str,
        effective_date: date,
        base_work_id: Optional[str] = None,     # override auto-resolution
        skip_review: bool = False,               # apply even low-confidence instructions
    ) -> ConsolidationResult:
        """
        Apply all instructions in parsed_amendment to the appropriate base law.

        Parameters
        ----------
        parsed_amendment:
            Output from AmendmentParser.parse().
        amendment_work_id:
            The Work ID of the wijzigingswet in the store.
        effective_date:
            The date the amendment takes effect (becomes the new Expression's
            version_date).
        base_work_id:
            Override automatic base law resolution.
        skip_review:
            If True, apply instructions even when confidence < REVIEW_THRESHOLD.

        Returns
        -------
        ConsolidationResult with per-instruction outcomes.
        """
        result = ConsolidationResult(
            amendment_work_id=amendment_work_id,
            base_work_id=base_work_id,
        )

        # Group instructions by target law (multi-law amendments)
        by_target: Dict[str, List[AmendmentInstruction]] = {}
        for inst in parsed_amendment.instructions:
            by_target.setdefault(inst.target_work_ref, []).append(inst)

        for target_ref, instructions in by_target.items():
            # Resolve base work
            if base_work_id:
                base_work = self.store.get_work(base_work_id)
            else:
                base_work = _resolve_base_work(target_ref, self.store)

            if not base_work:
                msg = f"Cannot resolve base law: {target_ref!r}"
                result.errors.append(msg)
                for inst in instructions:
                    result.skipped.append(ApplicationResult(
                        instruction=inst, applied=False, reason=msg
                    ))
                continue

            result.base_work_id = base_work.id

            # Load current expression + fragments.
            # Fall back to latest available expression when no expression is
            # found at effective_date — this happens when all expressions carry
            # the ingestion date (2026-xx-xx) which is after historical
            # effective dates (1970s–2010s).
            base_expr = self.store.get_expression_at_date(
                base_work.id, effective_date
            )
            if not base_expr:
                exprs = self.store.get_expressions_for_work(base_work.id)
                base_expr = exprs[-1] if exprs else None
            if not base_expr:
                msg = (
                    f"No expression found for {base_work.id!r} "
                    f"at or before {effective_date}"
                )
                result.errors.append(msg)
                continue

            fragments = self.store.get_fragments_for_expression(base_expr.id)

            # Apply instructions, mutating the fragment list in-memory
            app_results, updated_fragments = self._apply_all(
                instructions, fragments, base_work, base_expr,
                effective_date, skip_review
            )
            result.applied.extend([r for r in app_results if r.applied])
            result.skipped.extend([r for r in app_results if not r.applied])

            if not any(r.applied for r in app_results):
                logger.warning(
                    "No instructions were applied for base law %s — skipping new expression",
                    base_work.id
                )
                continue

            # Create new Expression
            new_expr = self._create_new_expression(
                base_work, base_expr, effective_date
            )
            self.store.save_expression(new_expr)

            # Create NEW Fragment rows owned by the new Expression.
            # FRBR principle: each Expression owns its own Fragment rows.
            # We cannot simply update expression_id on existing rows because
            # save_fragment's ON CONFLICT clause only updates text/metadata,
            # not expression_id.
            old_id_to_new: Dict[str, str] = {}
            new_fragments: List[Fragment] = []
            for frag in sorted(updated_fragments, key=lambda f: (f.depth, f.position)):
                new_frag_id = _new_fragment_id(new_expr.id, frag.number or frag.id)
                old_id_to_new[frag.id] = new_frag_id
                # Replace the old expression URI prefix so fragment URIs are
                # unique per Expression (avoids UNIQUE constraint on uri column).
                new_frag_uri = frag.uri.replace(base_expr.uri, new_expr.uri, 1)
                # Fallback: if base_expr.uri wasn't found in frag.uri (date mismatch
                # or different path format), build a unique URI from the new expr URI.
                if new_frag_uri == frag.uri:
                    suffix = frag.uri.split("/", 4)[-1] if frag.uri.count("/") >= 4 else frag.id
                    new_frag_uri = f"{new_expr.uri}/{suffix}"
                new_fragments.append(Fragment(
                    id=new_frag_id,
                    uri=new_frag_uri,
                    expression_id=new_expr.id,
                    expression_uri=new_expr.uri,
                    work_id=frag.work_id,
                    fragment_type=frag.fragment_type,
                    number=frag.number,
                    title=frag.title,
                    parent_fragment_id=(
                        old_id_to_new.get(frag.parent_fragment_id)
                        if frag.parent_fragment_id else None
                    ),
                    position=frag.position,
                    depth=frag.depth,
                    text=frag.text,
                    heading_path=list(frag.heading_path),
                    anchors=list(frag.anchors),
                    extraction_method=frag.extraction_method,
                    confidence=frag.confidence,
                    extracted_at=frag.extracted_at,
                    metadata=dict(frag.metadata),
                ))
            self.store.save_fragments_bulk(new_fragments)

            # Update fragment_ids in applied results so VersionDiff references
            # the new IDs, not the old base-expression fragment IDs.
            for r in app_results:
                if r.applied and r.fragment_id and r.fragment_id in old_id_to_new:
                    r.fragment_id = old_id_to_new[r.fragment_id]

            result.new_expression_id = new_expr.id

            # Record VersionDiff
            diff = VersionDiff(
                from_expression_id=base_expr.id,
                to_expression_id=new_expr.id,
                effective_date=effective_date,
                change_type="amendment",
                change_law_id=amendment_work_id,
                change_law_title=parsed_amendment.amendment_work_ref,
                affected_fragments=[
                    r.fragment_id for r in app_results
                    if r.applied and r.fragment_id
                ],
                summary=self._build_summary(app_results),
                staatsblad_ref=parsed_amendment.staatsblad_ref,
            )
            self.store.save_version_diff(diff)

            # Mark AmendmentLink resolved
            self._resolve_amendment_link(
                amendment_work_id, base_work.id, effective_date,
                parsed_amendment.staatsblad_ref,
            )

            logger.info(
                "Consolidated %s → %s: %d applied, %d skipped",
                amendment_work_id, base_work.id,
                len(result.applied), len(result.skipped),
            )

        return result

    # ── Instruction application ────────────────────────────────────────────

    def _apply_all(
        self,
        instructions: List[AmendmentInstruction],
        fragments: List[Fragment],
        base_work: Work,
        base_expr: Expression,
        effective_date: date,
        skip_review: bool,
    ) -> Tuple[List[ApplicationResult], List[Fragment]]:
        """Apply instructions in order. Returns (results, mutated fragment list)."""
        results: List[ApplicationResult] = []
        # Work on a copy so we don't mutate the store objects directly
        frags = [Fragment(**{
            k: v for k, v in f.__dict__.items()
        }) for f in fragments]

        for inst in instructions:
            # Stamp the resolved work ID
            inst.target_work_id = base_work.id

            if not skip_review and inst.confidence < REVIEW_THRESHOLD:
                results.append(ApplicationResult(
                    instruction=inst,
                    applied=False,
                    reason=f"confidence {inst.confidence:.2f} below threshold — needs review",
                ))
                continue

            ar = self._apply_one(inst, frags, base_work, base_expr, effective_date)
            results.append(ar)

        return results, frags

    def _apply_one(
        self,
        inst: AmendmentInstruction,
        frags: List[Fragment],
        work: Work,
        expr: Expression,
        effective_date: date,
    ) -> ApplicationResult:
        """Dispatch one instruction to the right handler."""
        handlers = {
            OperationType.REPEAL:  self._apply_repeal,
            OperationType.REPLACE: self._apply_replace,
            OperationType.INSERT:  self._apply_insert,
            OperationType.MODIFY:  self._apply_modify,
            OperationType.RENUMBER: self._apply_renumber,
        }
        handler = handlers.get(inst.operation)
        if not handler:
            return ApplicationResult(
                instruction=inst, applied=False,
                reason=f"Unknown operation: {inst.operation}",
            )
        return handler(inst, frags, work, expr, effective_date)

    # ── REPEAL ────────────────────────────────────────────────────────────

    def _apply_repeal(
        self, inst: AmendmentInstruction, frags: List[Fragment],
        work: Work, expr: Expression, effective_date: date,
    ) -> ApplicationResult:
        target = _find_article(frags, inst.target_article or "")
        if inst.target_paragraph and target:
            p = _find_paragraph(frags, inst.target_article, inst.target_paragraph)
            if p:
                target = p

        if not target:
            return ApplicationResult(
                instruction=inst, applied=False,
                reason=f"Article {inst.target_article!r} not found in base law",
            )

        target.text = REPEALED_PLACEHOLDER
        target.metadata["status"] = "repealed"
        target.metadata["repealed_by"] = work.id
        target.metadata["repealed_on"] = effective_date.isoformat()

        return ApplicationResult(
            instruction=inst, applied=True,
            reason="repealed", fragment_id=target.id,
        )

    # ── REPLACE ───────────────────────────────────────────────────────────

    def _apply_replace(
        self, inst: AmendmentInstruction, frags: List[Fragment],
        work: Work, expr: Expression, effective_date: date,
    ) -> ApplicationResult:
        if not inst.new_text:
            return ApplicationResult(
                instruction=inst, applied=False,
                reason="REPLACE instruction has no new_text",
            )

        if inst.target_paragraph:
            target = _find_paragraph(
                frags, inst.target_article or "", inst.target_paragraph
            )
        else:
            target = _find_article(frags, inst.target_article or "")

        if not target:
            return ApplicationResult(
                instruction=inst, applied=False,
                reason=f"Fragment art={inst.target_article!r} lid={inst.target_paragraph!r} not found",
            )

        target.text = inst.new_text.strip()
        target.metadata["replaced_by"] = work.id
        target.metadata["replaced_on"] = effective_date.isoformat()

        return ApplicationResult(
            instruction=inst, applied=True,
            reason="replaced", fragment_id=target.id,
        )

    # ── INSERT ────────────────────────────────────────────────────────────

    def _apply_insert(
        self, inst: AmendmentInstruction, frags: List[Fragment],
        work: Work, expr: Expression, effective_date: date,
    ) -> ApplicationResult:
        if not inst.new_text:
            return ApplicationResult(
                instruction=inst, applied=False,
                reason="INSERT instruction has no new_text",
            )

        # Find insertion position: after which article?
        after = _find_article(frags, inst.position_after or "")
        insert_position = (after.position + 1) if after else len(frags)

        # Shift positions of all subsequent articles
        for f in frags:
            if f.fragment_type == FragmentType.ARTICLE and f.position >= insert_position:
                f.position += 1

        # Create the new fragment
        new_nr = inst.new_article_number or f"{inst.position_after}a"
        new_id = _new_fragment_id(expr.id, f"art{new_nr}")

        from ..core.identifiers import law_fragment_uri
        new_uri = law_fragment_uri(work.official_id, effective_date, new_nr)

        new_frag = Fragment(
            id=new_id,
            uri=new_uri,
            expression_id=expr.id,   # will be rewritten to new expr by caller
            expression_uri=expr.uri,
            work_id=work.id,
            fragment_type=FragmentType.ARTICLE,
            number=new_nr,
            title=f"Artikel {new_nr}",
            position=insert_position,
            depth=0,
            text=inst.new_text.strip(),
            metadata={
                "inserted_by": work.id,
                "inserted_on": effective_date.isoformat(),
            },
        )
        frags.append(new_frag)
        # Re-sort by position for consistency
        frags.sort(key=lambda f: (f.depth, f.position))

        return ApplicationResult(
            instruction=inst, applied=True,
            reason=f"inserted after art {inst.position_after}",
            fragment_id=new_id,
        )

    # ── MODIFY ────────────────────────────────────────────────────────────

    def _apply_modify(
        self, inst: AmendmentInstruction, frags: List[Fragment],
        work: Work, expr: Expression, effective_date: date,
    ) -> ApplicationResult:
        if not inst.find_text or not inst.replace_text:
            return ApplicationResult(
                instruction=inst, applied=False,
                reason="MODIFY instruction missing find_text or replace_text",
            )

        # Determine target fragment
        if inst.target_article:
            if inst.target_paragraph:
                target = _find_paragraph(
                    frags, inst.target_article, inst.target_paragraph
                )
            else:
                target = _find_article(frags, inst.target_article)
        else:
            # No target article specified: apply to all fragments (rare)
            target = None

        if inst.target_article and not target:
            return ApplicationResult(
                instruction=inst, applied=False,
                reason=f"Article {inst.target_article!r} not found",
            )

        targets = [target] if target else frags

        applied_count = 0
        for frag in targets:
            if inst.find_text in frag.text:
                frag.text = frag.text.replace(inst.find_text, inst.replace_text, 1)
                frag.metadata["modified_by"] = work.id
                frag.metadata["modified_on"] = effective_date.isoformat()
                applied_count += 1

        if applied_count == 0:
            return ApplicationResult(
                instruction=inst, applied=False,
                reason=f"Text {inst.find_text!r} not found in target fragment(s)",
            )

        frag_id = target.id if target else None
        return ApplicationResult(
            instruction=inst, applied=True,
            reason=f"modified {applied_count} fragment(s)",
            fragment_id=frag_id,
        )

    # ── RENUMBER ─────────────────────────────────────────────────────────

    def _apply_renumber(
        self, inst: AmendmentInstruction, frags: List[Fragment],
        work: Work, expr: Expression, effective_date: date,
    ) -> ApplicationResult:
        target = _find_article(frags, inst.target_article or "")
        if not target:
            return ApplicationResult(
                instruction=inst, applied=False,
                reason=f"Article {inst.target_article!r} not found",
            )
        if not inst.new_number:
            return ApplicationResult(
                instruction=inst, applied=False,
                reason="RENUMBER instruction has no new_number",
            )

        old_number = target.number
        target.number = inst.new_number
        target.title = f"Artikel {inst.new_number}"
        target.metadata["renumbered_from"] = old_number
        target.metadata["renumbered_by"] = work.id

        return ApplicationResult(
            instruction=inst, applied=True,
            reason=f"renumbered art {old_number} → {inst.new_number}",
            fragment_id=target.id,
        )

    # ── New expression creation ────────────────────────────────────────────

    def _create_new_expression(
        self,
        work: Work,
        base_expr: Expression,
        effective_date: date,
    ) -> Expression:
        from ..core.identifiers import law_expression_uri

        expr_id = f"e-{work.official_id.lower()}-{effective_date.isoformat()}"
        return Expression(
            id=expr_id,
            uri=law_expression_uri(work.official_id, effective_date),
            work_id=work.id,
            work_uri=work.uri,
            version_date=effective_date,
            in_force=TemporalExtent(start=effective_date),
            title=base_expr.title,
            language=base_expr.language,
            status=DocumentStatus.IN_FORCE,
            previous_expression_id=base_expr.id,
            metadata={
                "consolidated_from": base_expr.id,
                "source": "consolidation_engine",
            },
        )

    # ── Amendment link management ──────────────────────────────────────────

    def _resolve_amendment_link(
        self,
        amendment_work_id: str,
        base_work_id: str,
        effective_date: date,
        staatsblad_ref: Optional[str],
    ) -> None:
        """Mark any existing AmendmentLink as resolved, or create one."""
        existing = self.store.get_amendment_links_for_amendment(amendment_work_id)
        for link in existing:
            if link.base_work_id == base_work_id or not link.base_work_id:
                link.base_work_id = base_work_id
                link.effective_date = effective_date
                link.resolved = True
                self.store.save_amendment_link(link)
                return

        # No existing link — create one
        link_id = hashlib.sha1(
            f"{amendment_work_id}:{base_work_id}".encode()
        ).hexdigest()[:16]
        self.store.save_amendment_link(AmendmentLink(
            id=link_id,
            amendment_work_id=amendment_work_id,
            base_work_id=base_work_id,
            base_work_ref=base_work_id,
            effective_date=effective_date,
            staatsblad_ref=staatsblad_ref,
            confidence=1.0,
            resolved=True,
        ))

    # ── Summary helpers ────────────────────────────────────────────────────

    @staticmethod
    def _build_summary(results: List[ApplicationResult]) -> str:
        counts: Dict[str, int] = {}
        for r in results:
            if r.applied:
                op = r.instruction.operation.value
                counts[op] = counts.get(op, 0) + 1
        parts = [f"{v}× {k}" for k, v in sorted(counts.items())]
        return "; ".join(parts) if parts else "no changes applied"
