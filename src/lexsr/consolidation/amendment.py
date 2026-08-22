"""
AmendmentInstruction — the atomic unit of the consolidation pipeline.

A single instruction describes exactly one change that a wijzigingswet
makes to a specific fragment of a base law:

  REPLACE  -- the entire article / paragraph is replaced by new text
  INSERT   -- a new article / paragraph is inserted at a given position
  REPEAL   -- the article / paragraph is removed ("vervalt")
  MODIFY   -- a find-and-replace is applied within existing text
  RENUMBER -- an article gets a new number (rare; used after inserts)

Instructions are produced by AmendmentParser and consumed by
ConsolidationEngine, which applies them to the CanonicalStore.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class OperationType(Enum):
    REPLACE  = "replace"   # artikel X wordt vervangen door: ...
    INSERT   = "insert"    # na artikel X wordt artikel Xa ingevoegd
    REPEAL   = "repeal"    # artikel X vervalt
    MODIFY   = "modify"    # in artikel X wordt 'A' vervangen door 'B'
    RENUMBER = "renumber"  # artikel X wordt vernummerd tot artikel Y


@dataclass
class AmendmentInstruction:
    """
    One atomic change from a wijzigingswet.

    Attributes
    ----------
    operation:
        What kind of change this is.
    target_work_ref:
        Raw reference to the base law being modified (e.g. "Arbeidswet 1963").
        Resolved to target_work_id by ConsolidationEngine.
    target_work_id:
        Resolved CanonicalStore work ID. None until resolved.
    target_article:
        The article number being modified (e.g. "5", "12a").
        None for document-level operations.
    target_paragraph:
        The paragraph (lid) number within the article (e.g. "2"). None for
        whole-article operations.
    target_sub:
        The sub-item letter within the paragraph (e.g. "a"). None if not
        targeting a specific sub-item.

    For INSERT:
    -----------
    position_after:
        Article number after which the new article is inserted.
    new_article_number:
        The number of the newly inserted article (e.g. "7a").

    For REPLACE / INSERT:
    ---------------------
    new_text:
        The full replacement or new text (plain text, post-OCR).

    For MODIFY:
    -----------
    find_text:
        Exact string to find in the existing fragment text.
    replace_text:
        String to substitute in its place.

    For RENUMBER:
    -------------
    new_number:
        The new article number.

    Provenance:
    -----------
    confidence:
        0–1 extraction confidence. Instructions with confidence < 0.7 are
        flagged for human review before the engine applies them.
    source_text:
        The raw instruction block text from the amendment document.
    source_char_start / source_char_end:
        Character offsets within the amendment text (for traceability).
    """
    operation: OperationType

    # --- Target ---------------------------------------------------------------
    target_work_ref: str                    # raw reference, e.g. "Arbeidswet 1963"
    target_work_id: Optional[str] = None    # filled in by engine after lookup
    target_article: Optional[str] = None   # article number, e.g. "5"
    target_paragraph: Optional[str] = None # lid number, e.g. "2"
    target_sub: Optional[str] = None       # sub-item letter, e.g. "a"

    # --- INSERT specifics -----------------------------------------------------
    position_after: Optional[str] = None   # insert after this article nr
    new_article_number: Optional[str] = None

    # --- New text (REPLACE / INSERT) -----------------------------------------
    new_text: Optional[str] = None

    # --- MODIFY find/replace --------------------------------------------------
    find_text: Optional[str] = None
    replace_text: Optional[str] = None

    # --- RENUMBER -------------------------------------------------------------
    new_number: Optional[str] = None

    # --- Provenance -----------------------------------------------------------
    confidence: float = 1.0
    source_text: str = ""
    source_char_start: int = 0
    source_char_end: int = 0

    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_reviewable(self) -> bool:
        """True when confidence is below threshold and human review is advised."""
        return self.confidence < 0.70

    def __repr__(self) -> str:
        target = self.target_article or "?"
        if self.target_paragraph:
            target += f" lid {self.target_paragraph}"
        return (
            f"<AmendmentInstruction {self.operation.value} "
            f"art.{target} of '{self.target_work_ref}' "
            f"conf={self.confidence:.2f}>"
        )


@dataclass
class ParsedAmendment:
    """
    Result of parsing one wijzigingswet document.

    Contains all instructions extracted from the document plus
    metadata about the amendment itself.
    """
    # Source document
    amendment_work_ref: str          # raw title / reference of the amendment
    staatsblad_ref: Optional[str]    # S.B. YYYY no. NNN of the amendment
    effective_date_raw: Optional[str]

    # Extracted instructions, in document order
    instructions: List[AmendmentInstruction] = field(default_factory=list)

    # Parsing quality
    parse_method: str = "regex"       # "regex", "llm", "combined"
    errors: List[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return any(i.is_reviewable() for i in self.instructions)

    @property
    def by_operation(self) -> Dict[str, List[AmendmentInstruction]]:
        result: Dict[str, List[AmendmentInstruction]] = {}
        for inst in self.instructions:
            result.setdefault(inst.operation.value, []).append(inst)
        return result
