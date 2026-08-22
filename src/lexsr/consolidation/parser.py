"""
AmendmentParser — extract AmendmentInstructions from wijzigingswet text.

A wijzigingswet typically has this structure:

  [Title / Staatsblad reference]
  [Preamble: "De Nationale Assemblee ... Heeft besloten:"]

  Artikel 1                          ← amendment's own Artikel 1
    De <WetNaam> wordt als volgt gewijzigd:
    A. Artikel 5 wordt vervangen door:
       "Artikel 5. ..."
    B. In artikel 12 lid 2 wordt 'één jaar' vervangen door 'twee jaar'.
    C. Na artikel 15 wordt artikel 15a ingevoegd, luidende:
       "Artikel 15a. ..."
    D. Artikel 44 vervalt.

  Artikel 2                          ← may target a second base law
    De <WetNaam2> wordt als volgt gewijzigd:
    ...

  Artikel 3                          ← in-force date
    Deze wet treedt in werking op 1 januari 1976.

Strategy
--------
Pass 1 — Regex (always):
  • Split the body into amendment-article sections (Artikel 1, Artikel 2 …)
  • Within each section find the target law and labelled instruction blocks
  • Classify each block: REPEAL / REPLACE / INSERT / MODIFY
  • Extract find/replace texts and new_text payloads heuristically
  • Simple single-modification documents (no labelled blocks) are handled too

Pass 2 — LLM via local Qwen (when use_llm=True and confidence is low):
  • Send the full instruction body to Qwen once
  • Parse the JSON array of instructions
  • Merge: LLM overrides regex for blocks where LLM confidence is higher
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .amendment import AmendmentInstruction, OperationType, ParsedAmendment
from .llm_client import call_llm, resolve_api_key

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

LOW_CONFIDENCE_THRESHOLD = 0.70   # blocks below this trigger LLM review
LLM_TIMEOUT = 25
CONTEXT_CHARS = 4_000             # chars sent to LLM per amendment section

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# ── Top-level structure ────────────────────────────────────────────────────

# Amendment's own article boundaries ("Artikel 1", "Artikel 2", "ARTIKEL I" …)
# Handles: lowercase/uppercase "Artikel", all-caps "ARTIKEL",
# numeric article numbers, and Roman numerals (I, II, III, IV …).
_OWN_ARTICLE = re.compile(
    r'^(?:[Aa]rtikel|ARTIKEL)\s+([IVXivx]+|\d+)\s*[.\n]',
    re.M,
)

# Document-type endings shared across all law-name patterns
# "belasting" included because many Surinamese tax laws end in it (Inkomstenbelasting etc.)
_DOC_TYPE_ENDINGS = (
    r'(?:wet|besluit|wetboek|code|ordonnantie|regeling|decreet|verordening|beschikking|belasting)'
)

# "De <WetNaam> (<SB ref>) wordt als volgt gewijzigd:" — section intro
_SECTION_INTRO = re.compile(
    r'(?:[Dd]e|[Hh]et)\s+'
    r'([A-Z][A-Za-zÀ-ÿ\s\-\.]+?'              # law name, capitalised start
    + _DOC_TYPE_ENDINGS + r'(?:\s+\d{4})?)'
    r'(?:\s*\([^)]*\))?'                        # optional (S.B. ...) in parens
    r'\s+wordt\s+als\s+volgt\s+gewijzigd',
    re.I,
)

# Direct single modification without labelled blocks:
# "Artikel X van de <WetNaam> wordt …"
_SINGLE_MOD_INTRO = re.compile(
    r'[Aa]rtikel\s+(\d+\w*)(?:\s+lid\s+(\d+\w?))?\s+van\s+(?:[Dd]e\s+|[Hh]et\s+)?'
    r'([A-Z][A-Za-zÀ-ÿ\s\-\.]+?' + _DOC_TYPE_ENDINGS + r'(?:\s+\d{4})?)\b',
)

# Preamble / title pattern: "tot/houdende [nadere] wijziging van [de/het] [«]X[»]"
# Two branches:
#   group 1 — guillemet/curly-quoted name  «Besluit Rustdagen 1971»
#   group 2 — unquoted name ending in a doc-type keyword
_PREAMBLE_TARGET = re.compile(
    r'(?:tot|houdende)\s+(?:nadere\s+)?wijziging\s+van\s+(?:de\s+|het\s+)?'
    r'(?:'
        r'[\u00ab\u201c\u2018"]'         # opening guillemet / curly quote
        r'([^\u00bb\u201d\u2019"]+)'     # group 1: anything between quotes
        r'[\u00bb\u201d\u2019"]'         # closing quote
    r'|'
        r'([A-Z][A-Za-zÀ-ÿ\s\-\.]+?'   # group 2: unquoted, doc-type ending
        + _DOC_TYPE_ENDINGS + r'(?:\s+\d{4})?)'
    r')'
    r'(?:\s*\([^)]*\))?',                # optional (S.B. ...) in parens
    re.I,
)

# ── Instruction block delimiters ───────────────────────────────────────────

# Labelled block start: "A. ", "1. ", "I. ", "(a) " at start of line
_BLOCK_LABEL = re.compile(
    r'^(?P<label>[A-Z]|[IVX]+|\d+)\.\s+|^\((?P<plabel>[a-zA-Z\d]+)\)\s+',
    re.M,
)

# ── Operation detection ────────────────────────────────────────────────────

# REPEAL — single article
_REPEAL_SINGLE = re.compile(
    r'[Aa]rtikel\s+(\d+\w*)\s+vervalt\b',
    re.I,
)
# REPEAL — multiple articles ("De artikelen 44 en 45 vervallen")
_REPEAL_MULTI = re.compile(
    r'[Dd]e\s+artikelen\s+'
    r'(\d+\w*(?:\s*(?:,\s*|\s+en\s+|\s+tot\s+en\s+met\s+)\d+\w*)*)'
    r'\s+vervallen\b',
    re.I,
)

# REPLACE — "Artikel X wordt vervangen door:" / "wordt gelezen als:"
_REPLACE_FULL = re.compile(
    r'[Aa]rtikel\s+(\d+\w*)(?:\s+lid\s+(\d+\w?))?\s+'
    r'(?:wordt\s+vervangen\s+door|wordt\s+gelezen\s+als)\s*:?',
    re.I,
)
# REPLACE — "de tekst van artikel X luidt als volgt:"
_REPLACE_TEXT = re.compile(
    r'[Dd]e\s+tekst\s+van\s+[Aa]rtikel\s+(\d+\w*)(?:\s+lid\s+(\d+\w?))?\s+'
    r'luidt\s+(?:als\s+volgt|voortaan)\s*:?',
    re.I,
)
# REPLACE — "Artikel X komt te luiden:" (common Surinamese variant)
_REPLACE_KOMT = re.compile(
    r'[Aa]rtikel\s+(\d+\w*)(?:\s+lid\s+(\d+\w?))?\s+komt\s+te\s+luiden\s*:?',
    re.I,
)
# REPLACE — "Lid X komt te luiden [als volgt]:" (paragraph-level replacement)
_LID_KOMT_LUIDEN = re.compile(
    r'[Ll]id\s+(\d+\w*)\s+komt\s+te\s+luiden(?:\s+als\s+volgt)?\s*:?',
    re.I,
)

# INSERT — "Na artikel X wordt (een nieuw) artikel Xa ingevoegd"
_INSERT_SINGLE = re.compile(
    r'[Nn]a\s+[Aa]rtikel\s+(\d+\w*)\s+'
    r'wordt\s+(?:een\s+)?(?:nieuw\s+)?[Aa]rtikel\s+(\d+\w*)\s+ingevoegd\b',
    re.I,
)
# INSERT — "Na artikel X worden de volgende artikelen ingevoegd:"
_INSERT_MULTI = re.compile(
    r'[Nn]a\s+[Aa]rtikel\s+(\d+\w*)\s+'
    r'worden\s+(?:de\s+)?(?:volgende\s+)?artikelen\s+ingevoegd\b',
    re.I,
)
# INSERT — "wordt ingevoegd een nieuw artikel X, luidende:"
_INSERT_NEW_AFTER = re.compile(
    r'wordt\s+ingevoegd\s+(?:een\s+)?(?:nieuw\s+)?[Aa]rtikel\s+(\d+\w*)\s*,?\s*luidende\s*:?',
    re.I,
)
# INSERT — "Na artikel X komt een nieuw artikel Y luidende [als volgt]:"
# Variant of INSERT using "komt ... luidende" instead of "wordt ... ingevoegd".
_INSERT_KOMT_LUIDENDE = re.compile(
    r'[Nn]a\s+[Aa]rtikel\s+(\d+\w*)\s+komt\s+(?:een\s+)?(?:nieuw\s+)?[Aa]rtikel\s+(\d+\w*)'
    r'\s+luidende\s+(?:als\s+volgt\s+)?:?',
    re.I,
)

# REPLACE — "Lid X wordt vervangen door:" (paragraph-level replacement)
_LID_WORDT_VERVANGEN = re.compile(
    r'[Ll]id\s+(\d+\w*)\s+wordt\s+vervangen\s+door\s*:?',
    re.I,
)
# REPEAL — "Lid X wordt geschrapt [onder vernummering van ...]"
_LID_WORDT_GESCHRAPT = re.compile(
    r'[Ll]id\s+(\d+\w*)\s+wordt\s+geschrapt\b',
    re.I,
)

# INSERT — "Na lid X wordt een nieuw lid Y [ingevoegd/toegevoegd]"
# Covers paragraph-level insertions within an article.
_INSERT_AFTER_LID = re.compile(
    r'[Nn]a\s+lid\s+(\d+\w*)\s+wordt\s+(?:een\s+)?(?:nieuw\s+)?lid\s+(\d+\w*)\s+'
    r'(?:ingevoegd|toegevoegd)\b',
    re.I,
)
# INSERT — "Na lid X worden [N] nieuwe leden [ingevoegd/toegevoegd], luidende:"
# Plural form — multiple new paragraphs after a given paragraph.
_INSERT_MULTI_LEDEN = re.compile(
    r'[Nn]a\s+lid\s+(\d+\w*)\s+worden\s+(?:\w+\s+)?(?:nieuwe\s+)?leden\s+'
    r'(?:ingevoegd|toegevoegd)\b',
    re.I,
)

# MODIFY — find-replace within text (double quotes or OCR curly quotes)
# Curly/OCR variants: \u201c…\u201d, \u2018…\u2019, \u201e…\u201c, ‚…‛
_Q = r'["\u201c\u201d\u2018\u2019\u201e\u201b\u00ab\u00bb\u2039\u203a]'  # any quote char
_MODIFY_DQUOTE = re.compile(
    r'(?:[Ii]n\s+[Aa]rtikel\s+(\d+\w*)(?:\s+lid\s+(\d+\w?))?'
    r'(?:\s+(?:sub|onderdeel|onder)\s+([a-z]))?\s+)?'
    r'wordt\s+(?:de\s+)?(?:zinsnede|het\s+woord|de\s+woorden|de\s+aanduiding)\s+'
    r'"([^"]+)"\s+vervangen\s+door\s+"([^"]+)"',
    re.I,
)
# MODIFY — single quotes
_MODIFY_SQUOTE = re.compile(
    r"(?:[Ii]n\s+[Aa]rtikel\s+(\d+\w*)(?:\s+lid\s+(\d+\w?))?"
    r"(?:\s+(?:sub|onderdeel|onder)\s+([a-z]))?\s+)?"
    r"wordt\s+'([^']+)'\s+vervangen\s+door\s+'([^']+)'",
    re.I,
)
# MODIFY — OCR curly-quote variants (e.g. ‚text' of ,text')
_MODIFY_CURLY = re.compile(
    r"(?:[Ii]n\s+[Aa]rtikel\s+(\d+\w*)(?:\s+lid\s+(\d+\w?))?"
    r"(?:\s+(?:sub|onderdeel|onder)\s+([a-z]))?\s+)?"
    r"wordt\s+(?:de\s+)?(?:zinsnede|het\s+woord|de\s+woorden|de\s+aanduiding)\s+"
    r"[,\u201e\u2018\u00ab]([^\u201d\u2019\u00bb,\u201c\u201f]{1,120})['\u2019\u201d\u00bb]\s+"
    r"vervangen\s+door\s+"
    r"[,\u201e\u2018\u00ab]([^\u201d\u2019\u00bb,\u201c\u201f]{1,120})['\u2019\u201d\u00bb]",
    re.I,
)
# MODIFY — "worden de woorden X vervangen door Y" (no quotes, short strings)
_MODIFY_WORDS = re.compile(
    r'[Ii]n\s+[Aa]rtikel\s+(\d+\w*)(?:\s+lid\s+(\d+\w?))?'
    r'(?:\s+(?:sub|onderdeel)\s+([a-z]))?\s+'
    r'worden?\s+de\s+woorden?\s+"([^"]+)"\s+vervangen\s+door\s+"([^"]+)"',
    re.I,
)
# MODIFY — "In [artikel X,] lid Y, wordt de volzin/zinsnede '...' vervangen door:"
# The closing quote is optional (OCR sometimes omits it).
# Terminator "vervangen door" / "gewijzigd in" ends the find_text capture.
_MODIFY_VOLZIN = re.compile(
    r'(?:[Ii]n\s+[Aa]rtikel\s+(\d+\w*)[,\s]+)?'
    r'(?:[Ii]n\s+)?[Ll]id\s+(\d+\w*)[,\s]+'
    r'wordt\s+de\s+(?:volzin|zinsnede|periode)\s+'
    r'["\u201c\u2018\u00ab\u201e,]'
    r'(.+?)'                                  # lazy: find_text up to terminator
    r'["\u201d\u2019\u00bb]?\s*'             # optional closing quote
    r'(?:vervangen\s+door|gewijzigd\s+in)\s*:?',
    re.I | re.S,
)
# MODIFY — "In artikel X[, lid Y], wordt de zinsnede '...' vervangen door:"
# The closing quote is optional (OCR sometimes omits it).
_MODIFY_ZINSNEDE = re.compile(
    r'[Ii]n\s+[Aa]rtikel\s+(\d+\w*)(?:[,\s]+lid\s+(\d+\w?))?[,\s]+'
    r'wordt\s+de\s+(?:zinsnede|volzin|periode)\s+'
    r'["\u201c\u2018\u00ab\u201e]'
    r'(.+?)'                                  # lazy: find_text
    r'["\u201d\u2019\u00bb]?\s*'             # optional closing quote
    r'(?:vervangen\s+door|gewijzigd\s+in)\s*:',
    re.I | re.S,
)
# MODIFY — "In lid X [de/wordt de] zinsnede '...' vervangen door:" (no article ref)
_MODIFY_ZINSNEDE_LID = re.compile(
    r'(?:[Ii]n\s+)?[Ll]id\s+(\d+\w*)[,\s]+'
    r'(?:wordt\s+)?de\s+(?:zinsnede|volzin|periode)\s+'
    r'["\u201c\u2018\u00ab\u201e]'
    r'(.+?)'                                  # lazy: find_text
    r'["\u201d\u2019\u00bb]?\s*'             # optional closing quote
    r'(?:vervangen\s+door|gewijzigd\s+in)\s*:?',
    re.I | re.S,
)
# MODIFY — "het woord '...' [wordt] geschrapt" (deletion)
_WORDT_GESCHRAPT = re.compile(
    r'(?:[Ii]n\s+[Aa]rtikel\s+(\d+\w*)(?:[,\s]+lid\s+(\d+\w?))?\s+)?'
    r'(?:wordt\s+)?het\s+woord\s+'
    r'["\u201c\u2018\u00ab,]([^"\u201d\u2019\u00bb,]{1,80})["\u201d\u2019\u00bb]\s+'
    r'geschrapt\b',
    re.I,
)

# ── Insert-in-place patterns ───────────────────────────────────────────────

# "In artikel X[, lid Y], wordt [na '…'] ingevoegd ['…']"
# e.g. "In artikel 37, lid 2, wordt na ,opgave gedaan' ingevoegd ,aan de Raad…'"
_INSERT_IN_ARTICLE = re.compile(
    r'[Ii]n\s+[Aa]rtikel\s+(\d+\w*)'
    r'(?:[,\s]+lid\s+(\d+\w?))?'
    r'(?:[,\s]+(?:sub|onderdeel|onder)\s+([a-z]))?'
    r'[,\s]+wordt(?:\s+na\s+.{0,120?})?\s+ingevoegd\b',
    re.I | re.S,
)

# "Aan artikel X[, lid Y], wordt [een] [lid/punt/sub/zin] [N/letter] toegevoegd[, luidende]"
# e.g. "Aan artikel 40, lid 1, wordt een punt e toegevoegd, luidende als volgt:"
_ADD_TO_ARTICLE = re.compile(
    r'[Aa]an\s+[Aa]rtikel\s+(\d+\w*)'
    r'(?:[,\s]+lid\s+(\d+\w?))?'
    r'[,\s]+wordt\s+(?:een\s+)?(?:nieuw\s+)?'
    r'(?:punt|lid|sub|onderdeel|zin|zinsnede|alinea|artikel)\s+([a-z\d]+)\s+'
    r'toegevoegd\b',
    re.I,
)

# "Artikel X[, lid Y] wordt gewijzigd als volgt:" (full article rework)
_ARTICLE_GEWIJZIGD = re.compile(
    r'[Aa]rtikel\s+(\d+\w*)(?:[,\s]+lid\s+(\d+\w?))?\s+'
    r'wordt\s+(?:als\s+volgt\s+)?gewijzigd\s*:?',
    re.I,
)

# ── Non-legal block filter ─────────────────────────────────────────────────

# Blocks with no legal keywords are signature/date fragments — skip them.
_LEGAL_KEYWORDS = re.compile(
    r'\b(?:artikel|lid|wordt|vervalt|ingevoegd|toegevoegd|vervangen|'
    r'gelezen|gewijzigd|geschrapt|opgeheven|vernummerd|ingevoerd|'
    r'luidt|luidende|wijziging|wijzigt)\b',
    re.I,
)

# Publication-notice header: "WET/STAATSBESLUIT/DECREET van DD maand YYYY, houdende ..."
# These appear at the bottom of OCR'd pages (the title header of the next law).
_PUB_NOTICE_HDR = re.compile(
    r'\b(?:WET|STAATSBESLUIT|DECREET)\s+van\s+\d{1,2}',
    re.I,
)

# Strong instruction verbs — present means the block has real operative content.
_STRONG_INSTRUCTION = re.compile(
    r'\b(?:wordt\s+vervangen\s+door|vervalt\b|ingevoegd\b|toegevoegd\b|'
    r'komt\s+te\s+luiden|wordt\s+(?:als\s+volgt\s+)?gewijzigd|wordt\s+geschrapt|'
    r'luidt\s+als\s+volgt|wordt\s+vernummerd)\b',
    re.I,
)

# Signature block marker.
_SIGNATURE_BLOCK = re.compile(
    r'\bGegeven\s+te\s+Paramaribo\b|\bUitgegeven\s+te\s+Paramaribo\b',
    re.I,
)

# ── Global referral replacement ────────────────────────────────────────────

# "Waar verwezen wordt naar X wordt vervangen door Y [en waar ...]"
_REPLACE_REFERRAL = re.compile(
    r'[Ww]aar\s+verwezen\s+wordt\s+naar\s+(.{5,120}?)\s+wordt\s+vervangen\s+door\s+'
    r'(.{5,200}?)(?=\s+en\s+waar|\s*[.;]|\s*$)',
    re.I | re.S,
)

# ── New text extraction ────────────────────────────────────────────────────

# Text quoted with " … " (may span lines)
_QUOTED_BLOCK = re.compile(r'"([\s\S]+?)"(?=\s*(?:[A-Z]\.|\d+\.|$|\Z))', re.M)

# OCR curly-quoted block: ‚…' or ,…' or «…»
_QUOTED_CURLY = re.compile(
    r'[,\u201e\u2018\u00ab]'
    r'([\s\S]{10,}?)'
    r'[\'.\u2019\u201d\u00bb]'
    r'(?=\s*(?:[A-Z]\.|\d+\.|$|\Z))',
    re.M,
)

# "luidende:" followed by content
_LUIDENDE = re.compile(r'luidende\s*:\s*([\s\S]+)', re.I)

# ── Metadata ──────────────────────────────────────────────────────────────

_SB_REF = re.compile(
    r'(?:S\.?\s*B\.?|Staatsblad|Stb\.?)\s+(\d{4})\s*(?:,|no\.?|nr\.?)\s*(\d+)',
    re.I,
)
_EFFECTIVE_DATE = re.compile(
    r'(?:'
    r'treedt\s+in\s+werking'                        # "treedt in werking op ..."
    r'|treden\s+in\s+werking'                        # "treden in werking op ..."
    r'|in\s+werking\s+(?:ge)?treden?'               # "in werking treden/getreden"
    r'|van\s+kracht\s+(?:geworden?|word(?:en|t))'   # "van kracht worden/geworden"
    r')'
    r'\s+(?:op\s+|per\s+|met\s+ingang\s+van\s+)?'
    r'(\d{1,2}\s+(?:januari|februari|maart|april|mei|juni|juli|augustus|'
    r'september|oktober|november|december)\s+\d{4})',
    re.I,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm_article(number: str) -> str:
    """Normalize an article number: strip leading zeros, lowercase."""
    return number.strip().lstrip("0").lower() or number.strip().lower()


def _extract_new_text(block_text: str) -> Optional[str]:
    """
    Pull the new article/paragraph text from an instruction block.

    Tries (in order):
    1. Straight-quoted block  "Artikel X. ..."
    2. Curly/OCR-quoted block  ‚Artikel X. …'
    3. Content after "luidende:"
    4. Everything after the first colon on the first line
    """
    # 1. Straight-quoted block
    m = _QUOTED_BLOCK.search(block_text)
    if m:
        return m.group(1).strip()

    # 2. Curly/OCR-quoted block
    m = _QUOTED_CURLY.search(block_text)
    if m:
        return m.group(1).strip()

    # 3. "luidende:" pattern
    m = _LUIDENDE.search(block_text)
    if m:
        return m.group(1).strip()

    # 4. After first colon
    colon_pos = block_text.find(":")
    if colon_pos != -1:
        remainder = block_text[colon_pos + 1:].strip()
        if len(remainder) > 20:
            return remainder

    return None


def _split_blocks(section_text: str) -> List[Tuple[str, str]]:
    """
    Split a section into (label, block_text) pairs.

    If no labelled blocks are found, return [("", section_text)] so the
    caller treats the whole section as one instruction.
    """
    matches = list(_BLOCK_LABEL.finditer(section_text))
    if not matches:
        return [("", section_text)]

    blocks = []
    for i, m in enumerate(matches):
        label = m.group("label") or m.group("plabel") or ""
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section_text)
        blocks.append((label, section_text[start:end].strip()))
    return blocks


def _parse_block(
    block_text: str,
    target_work_ref: str,
    char_offset: int = 0,
) -> List[AmendmentInstruction]:
    """
    Parse a single labelled block into one or more AmendmentInstructions.

    Returns a list because INSERT_MULTI can produce multiple instructions.
    """
    instructions: List[AmendmentInstruction] = []

    # ── REPEAL (single) ───────────────────────────────────────────────────
    for m in _REPEAL_SINGLE.finditer(block_text):
        instructions.append(AmendmentInstruction(
            operation=OperationType.REPEAL,
            target_work_ref=target_work_ref,
            target_article=_norm_article(m.group(1)),
            confidence=0.95,
            source_text=block_text,
            source_char_start=char_offset + m.start(),
            source_char_end=char_offset + m.end(),
        ))

    # ── REPEAL (multiple) ─────────────────────────────────────────────────
    for m in _REPEAL_MULTI.finditer(block_text):
        raw_list = m.group(1)
        # Parse "44 en 45" / "12, 13 en 14" / "12 tot en met 15"
        if "tot en met" in raw_list.lower():
            parts = re.split(r'\s+tot\s+en\s+met\s+', raw_list, flags=re.I)
            if len(parts) == 2:
                try:
                    # Numeric range only; alphanumeric ranges not supported
                    start_n = int(re.search(r'\d+', parts[0]).group())
                    end_n   = int(re.search(r'\d+', parts[1]).group())
                    article_nums = [str(n) for n in range(start_n, end_n + 1)]
                except (AttributeError, ValueError):
                    article_nums = [raw_list]
            else:
                article_nums = [raw_list]
        else:
            article_nums = [
                _norm_article(p.strip())
                for p in re.split(r'[,\s]+(?:en\s+)?', raw_list)
                if re.search(r'\d', p)
            ]

        for nr in article_nums:
            instructions.append(AmendmentInstruction(
                operation=OperationType.REPEAL,
                target_work_ref=target_work_ref,
                target_article=nr,
                confidence=0.90,
                source_text=block_text,
                source_char_start=char_offset + m.start(),
                source_char_end=char_offset + m.end(),
            ))

    if instructions:
        return instructions

    # ── REPLACE ──────────────────────────────────────────────────────────
    for pat in (_REPLACE_FULL, _REPLACE_TEXT, _REPLACE_KOMT):
        m = pat.search(block_text)
        if m:
            article = _norm_article(m.group(1))
            paragraph = m.group(2) if m.lastindex and m.lastindex >= 2 else None
            new_text = _extract_new_text(block_text[m.end():])
            conf = 0.85 if new_text else 0.50
            instructions.append(AmendmentInstruction(
                operation=OperationType.REPLACE,
                target_work_ref=target_work_ref,
                target_article=article,
                target_paragraph=paragraph,
                new_text=new_text,
                confidence=conf,
                source_text=block_text,
                source_char_start=char_offset,
                source_char_end=char_offset + len(block_text),
            ))
            return instructions

    # ── REPLACE — "Lid X komt te luiden [als volgt]:" ────────────────────
    for pat in (_LID_KOMT_LUIDEN, _LID_WORDT_VERVANGEN):
        m = pat.search(block_text)
        if m:
            paragraph = m.group(1)
            new_text = _extract_new_text(block_text[m.end():])
            instructions.append(AmendmentInstruction(
                operation=OperationType.REPLACE,
                target_work_ref=target_work_ref,
                target_paragraph=paragraph,
                new_text=new_text,
                confidence=0.80 if new_text else 0.55,
                source_text=block_text,
                source_char_start=char_offset,
                source_char_end=char_offset + len(block_text),
            ))
            return instructions

    # ── REPEAL — "Lid X wordt geschrapt" ─────────────────────────────────
    for m in _LID_WORDT_GESCHRAPT.finditer(block_text):
        instructions.append(AmendmentInstruction(
            operation=OperationType.REPEAL,
            target_work_ref=target_work_ref,
            target_paragraph=m.group(1),
            confidence=0.90,
            source_text=block_text,
            source_char_start=char_offset + m.start(),
            source_char_end=char_offset + m.end(),
        ))
    if instructions:
        return instructions

    # ── INSERT — "Na artikel X komt een nieuw artikel Y luidende:" ───────
    m = _INSERT_KOMT_LUIDENDE.search(block_text)
    if m:
        after  = _norm_article(m.group(1))
        new_nr = _norm_article(m.group(2))
        new_text = _extract_new_text(block_text[m.end():])
        instructions.append(AmendmentInstruction(
            operation=OperationType.INSERT,
            target_work_ref=target_work_ref,
            position_after=after,
            new_article_number=new_nr,
            new_text=new_text,
            confidence=0.85 if new_text else 0.55,
            source_text=block_text,
            source_char_start=char_offset,
            source_char_end=char_offset + len(block_text),
        ))
        return instructions

    # ── INSERT (single new article) ───────────────────────────────────────
    m = _INSERT_SINGLE.search(block_text)
    if m:
        after = _norm_article(m.group(1))
        new_nr = _norm_article(m.group(2))
        remainder = block_text[m.end():]
        new_text = _extract_new_text(remainder)
        conf = 0.85 if new_text else 0.55
        instructions.append(AmendmentInstruction(
            operation=OperationType.INSERT,
            target_work_ref=target_work_ref,
            position_after=after,
            new_article_number=new_nr,
            new_text=new_text,
            confidence=conf,
            source_text=block_text,
            source_char_start=char_offset,
            source_char_end=char_offset + len(block_text),
        ))
        return instructions

    # ── INSERT (new paragraph within article) ────────────────────────────
    # "Na lid X wordt een nieuw lid Y ingevoegd"
    m = _INSERT_AFTER_LID.search(block_text)
    if m:
        after_lid = m.group(1)
        new_lid   = m.group(2)
        new_text  = _extract_new_text(block_text[m.end():]) or _extract_new_text(block_text)
        instructions.append(AmendmentInstruction(
            operation=OperationType.INSERT,
            target_work_ref=target_work_ref,
            target_paragraph=new_lid,
            position_after=after_lid,
            new_text=new_text,
            confidence=0.80 if new_text else 0.55,
            source_text=block_text,
            source_char_start=char_offset,
            source_char_end=char_offset + len(block_text),
        ))
        return instructions

    # ── INSERT (multiple new paragraphs) — "Na lid X worden N leden toegevoegd"
    m = _INSERT_MULTI_LEDEN.search(block_text)
    if m:
        after_lid = m.group(1)
        new_text  = _extract_new_text(block_text[m.end():]) or _extract_new_text(block_text)
        instructions.append(AmendmentInstruction(
            operation=OperationType.INSERT,
            target_work_ref=target_work_ref,
            position_after=after_lid,
            new_text=new_text,
            confidence=0.70 if new_text else 0.45,
            source_text=block_text,
            source_char_start=char_offset,
            source_char_end=char_offset + len(block_text),
        ))
        return instructions

    # ── INSERT (multiple articles after a single "na artikel X") ─────────
    m = _INSERT_MULTI.search(block_text)
    if m:
        after = _norm_article(m.group(1))
        remainder = block_text[m.end():]
        # Find each inserted article by its heading "Artikel Xa."
        sub_articles = list(re.finditer(
            r'(?:"|\n)\s*[Aa]rtikel\s+(\d+\w*)\s*[.\n]',
            remainder,
        ))
        if sub_articles:
            for i, sa in enumerate(sub_articles):
                new_nr = _norm_article(sa.group(1))
                end = sub_articles[i + 1].start() if i + 1 < len(sub_articles) else len(remainder)
                new_text = remainder[sa.end():end].strip().strip('"').strip()
                instructions.append(AmendmentInstruction(
                    operation=OperationType.INSERT,
                    target_work_ref=target_work_ref,
                    position_after=after if i == 0 else sub_articles[i - 1].group(1),
                    new_article_number=new_nr,
                    new_text=new_text or None,
                    confidence=0.75,
                    source_text=block_text,
                    source_char_start=char_offset,
                    source_char_end=char_offset + len(block_text),
                ))
        else:
            # Can't split sub-articles — lower confidence, LLM will fix
            instructions.append(AmendmentInstruction(
                operation=OperationType.INSERT,
                target_work_ref=target_work_ref,
                position_after=after,
                new_text=_extract_new_text(remainder),
                confidence=0.45,
                source_text=block_text,
                source_char_start=char_offset,
                source_char_end=char_offset + len(block_text),
            ))
        return instructions

    # ── REPLACE — "Artikel X wordt gewijzigd als volgt:" ─────────────────
    m = _ARTICLE_GEWIJZIGD.search(block_text)
    if m:
        article   = _norm_article(m.group(1))
        paragraph = m.group(2) if m.lastindex and m.lastindex >= 2 else None
        new_text  = _extract_new_text(block_text[m.end():])
        instructions.append(AmendmentInstruction(
            operation=OperationType.REPLACE,
            target_work_ref=target_work_ref,
            target_article=article,
            target_paragraph=paragraph,
            new_text=new_text,
            confidence=0.80 if new_text else 0.55,
            source_text=block_text,
            source_char_start=char_offset,
            source_char_end=char_offset + len(block_text),
        ))
        return instructions

    # ── INSERT IN PLACE — "In artikel X[, lid Y], wordt … ingevoegd …" ──
    m = _INSERT_IN_ARTICLE.search(block_text)
    if m:
        article   = _norm_article(m.group(1))
        paragraph = m.group(2) if m.lastindex and m.lastindex >= 2 else None
        sub       = m.group(3) if m.lastindex and m.lastindex >= 3 else None
        new_text  = _extract_new_text(block_text[m.end():]) or _extract_new_text(block_text)
        instructions.append(AmendmentInstruction(
            operation=OperationType.INSERT,
            target_work_ref=target_work_ref,
            target_article=article,
            target_paragraph=paragraph,
            target_sub=sub,
            new_text=new_text,
            confidence=0.80 if new_text else 0.55,
            source_text=block_text,
            source_char_start=char_offset,
            source_char_end=char_offset + len(block_text),
        ))
        return instructions

    # ── ADD TO END — "Aan artikel X[, lid Y], wordt … toegevoegd …" ─────
    m = _ADD_TO_ARTICLE.search(block_text)
    if m:
        article      = _norm_article(m.group(1))
        paragraph    = m.group(2) if m.lastindex and m.lastindex >= 2 else None
        new_item_nr  = m.group(3) if m.lastindex and m.lastindex >= 3 else None
        new_text     = _extract_new_text(block_text[m.end():]) or _extract_new_text(block_text)
        instructions.append(AmendmentInstruction(
            operation=OperationType.INSERT,
            target_work_ref=target_work_ref,
            target_article=article,
            target_paragraph=paragraph,
            new_article_number=new_item_nr,
            new_text=new_text,
            confidence=0.80 if new_text else 0.55,
            source_text=block_text,
            source_char_start=char_offset,
            source_char_end=char_offset + len(block_text),
        ))
        return instructions

    # ── MODIFY (find/replace) ─────────────────────────────────────────────
    for pat in (_MODIFY_DQUOTE, _MODIFY_SQUOTE, _MODIFY_CURLY, _MODIFY_WORDS):
        m = pat.search(block_text)
        if m:
            grps = m.groups()
            article   = _norm_article(grps[0]) if grps[0] else None
            paragraph = grps[1] if len(grps) > 1 and grps[1] else None
            sub       = grps[2] if len(grps) > 2 and grps[2] else None
            find_t    = grps[3] if len(grps) > 3 else None
            repl_t    = grps[4] if len(grps) > 4 else None
            instructions.append(AmendmentInstruction(
                operation=OperationType.MODIFY,
                target_work_ref=target_work_ref,
                target_article=article,
                target_paragraph=paragraph,
                target_sub=sub,
                find_text=find_t,
                replace_text=repl_t,
                confidence=0.90 if (find_t and repl_t) else 0.50,
                source_text=block_text,
                source_char_start=char_offset,
                source_char_end=char_offset + len(block_text),
            ))
            return instructions

    # ── MODIFY — zinsnede/volzin substitution ──────────────────────────────
    # Tries article-level first, then paragraph-level.
    for pat, art_grp, par_grp, find_grp in (
        (_MODIFY_ZINSNEDE,      1, 2, 3),   # "In artikel X[, lid Y]"
        (_MODIFY_VOLZIN,        1, 2, 3),   # "In [artikel X,] lid Y"
        (_MODIFY_ZINSNEDE_LID,  None, 1, 2), # "In lid Y"
    ):
        m = pat.search(block_text)
        if m:
            article   = _norm_article(m.group(art_grp)) if art_grp and m.group(art_grp) else None
            paragraph = m.group(par_grp) if par_grp and m.group(par_grp) else None
            find_t    = m.group(find_grp).strip() if m.group(find_grp) else None
            repl_t    = _extract_new_text(block_text[m.end():])
            instructions.append(AmendmentInstruction(
                operation=OperationType.MODIFY,
                target_work_ref=target_work_ref,
                target_article=article,
                target_paragraph=paragraph,
                find_text=find_t,
                replace_text=repl_t,
                confidence=0.80 if (find_t and repl_t) else 0.55,
                source_text=block_text,
                source_char_start=char_offset,
                source_char_end=char_offset + len(block_text),
            ))
            return instructions

    # ── MODIFY — word deletion ("het woord '...' geschrapt") ──────────────
    m = _WORDT_GESCHRAPT.search(block_text)
    if m:
        article   = _norm_article(m.group(1)) if m.group(1) else None
        paragraph = m.group(2) if m.group(2) else None
        find_t    = m.group(3).strip() if m.group(3) else None
        instructions.append(AmendmentInstruction(
            operation=OperationType.MODIFY,
            target_work_ref=target_work_ref,
            target_article=article,
            target_paragraph=paragraph,
            find_text=find_t,
            replace_text="",   # deletion — replace with empty
            confidence=0.85 if find_t else 0.55,
            source_text=block_text,
            source_char_start=char_offset,
            source_char_end=char_offset + len(block_text),
        ))
        return instructions

    # ── Global referral replacement ───────────────────────────────────────
    # "Waar verwezen wordt naar X wordt vervangen door Y"
    referral_insts = []
    for m in _REPLACE_REFERRAL.finditer(block_text):
        referral_insts.append(AmendmentInstruction(
            operation=OperationType.MODIFY,
            target_work_ref=target_work_ref,
            find_text=m.group(1).strip(),
            replace_text=m.group(2).strip(),
            confidence=0.75,
            source_text=block_text,
            source_char_start=char_offset + m.start(),
            source_char_end=char_offset + m.end(),
            metadata={"scope": "global_referral"},
        ))
    if referral_insts:
        return referral_insts

    # ── Non-legal block filter ─────────────────────────────────────────────
    # If the block contains no legal keywords at all (e.g. it is a signature,
    # date line, or page header captured by the block label regex), do not
    # emit a fallback instruction — return empty so the caller doesn't count it.
    if not _LEGAL_KEYWORDS.search(block_text):
        return []

    # ── Publication-notice filter ──────────────────────────────────────────
    # Blocks that consist of a signature section + OCR publication-header artefact
    # (e.g. "WET van 12 januari 1990, houdende wijziging van...") should not
    # produce fallback instructions — the "wijziging" keyword in the title is
    # not an operative instruction.
    if _PUB_NOTICE_HDR.search(block_text) and not _STRONG_INSTRUCTION.search(block_text):
        return []

    # ── Fallback: could not classify ─────────────────────────────────────
    instructions.append(AmendmentInstruction(
        operation=OperationType.MODIFY,  # safest default
        target_work_ref=target_work_ref,
        confidence=0.20,
        source_text=block_text,
        source_char_start=char_offset,
        source_char_end=char_offset + len(block_text),
        metadata={"parse_error": "could not classify block"},
    ))
    return instructions


# ---------------------------------------------------------------------------
# LLM pass
# ---------------------------------------------------------------------------

_LLM_PARSER_PROMPT = """\
Parse ALL amendment instructions from this Surinamese/Dutch legal text.

Text:
---
{text}
---

Respond with JSON only (no markdown):
{{
  "target_law": "<law name>",
  "instructions": [
    {{
      "operation": "replace" | "insert" | "repeal" | "modify",
      "target_article": "<number or null>",
      "target_paragraph": "<number or null>",
      "target_sub": "<letter or null>",
      "position_after": "<number or null>",
      "new_article_number": "<number or null>",
      "new_text": "<full replacement text or null>",
      "find_text": "<text to find or null>",
      "replace_text": "<replacement text or null>",
      "confidence": <float>,
      "source_text": "<the instruction sentence>"
    }}
  ]
}}
"""


def _llm_parse_section(
    section_text: str,
    target_law: str,
    llm_url: str,
    model: str,
    temperature: float,
    api_key: Optional[str] = None,
) -> Optional[List[AmendmentInstruction]]:
    """Call the configured LLM once for a section; return instructions or None on failure."""
    excerpt = section_text[:CONTEXT_CHARS]
    prompt = _LLM_PARSER_PROMPT.format(text=excerpt)

    raw = call_llm(
        prompt=prompt,
        llm_url=llm_url,
        model=model,
        temperature=temperature,
        max_tokens=2048,
        api_key=api_key,
        timeout=LLM_TIMEOUT,
    )
    if raw is None:
        return None

    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.M)
    raw = re.sub(r'\s*```\s*$', '', raw, flags=re.M)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', raw, re.S)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None

    instructions = []
    for item in data.get("instructions") or []:
        try:
            op = OperationType(item.get("operation", "modify"))
        except ValueError:
            op = OperationType.MODIFY

        instructions.append(AmendmentInstruction(
            operation=op,
            target_work_ref=data.get("target_law", target_law),
            target_article=item.get("target_article") or None,
            target_paragraph=item.get("target_paragraph") or None,
            target_sub=item.get("target_sub") or None,
            position_after=item.get("position_after") or None,
            new_article_number=item.get("new_article_number") or None,
            new_text=item.get("new_text") or None,
            find_text=item.get("find_text") or None,
            replace_text=item.get("replace_text") or None,
            confidence=float(item.get("confidence", 0.70)),
            source_text=item.get("source_text", ""),
            metadata={"source": "llm"},
        ))

    return instructions if instructions else None


# ---------------------------------------------------------------------------
# Merge regex + LLM results
# ---------------------------------------------------------------------------

def _merge_instructions(
    regex_insts: List[AmendmentInstruction],
    llm_insts: List[AmendmentInstruction],
) -> List[AmendmentInstruction]:
    """
    Merge regex and LLM instruction lists.

    For each regex instruction:
    - If LLM produced a matching instruction (same operation + article),
      use whichever has higher confidence and fill in missing fields.
    - If only LLM found an instruction (regex missed it), add it.
    - Keep regex instructions not matched by LLM.
    """
    result = list(regex_insts)
    matched_llm = set()

    for i, reg in enumerate(result):
        for j, llm in enumerate(llm_insts):
            if j in matched_llm:
                continue
            if (reg.operation == llm.operation
                    and reg.target_article == llm.target_article
                    and reg.target_paragraph == llm.target_paragraph):
                matched_llm.add(j)
                if llm.confidence > reg.confidence:
                    # LLM wins — fill in its new_text / find/replace
                    result[i] = AmendmentInstruction(
                        operation=reg.operation,
                        target_work_ref=reg.target_work_ref,
                        target_article=reg.target_article,
                        target_paragraph=reg.target_paragraph,
                        target_sub=reg.target_sub or llm.target_sub,
                        position_after=reg.position_after or llm.position_after,
                        new_article_number=reg.new_article_number or llm.new_article_number,
                        new_text=llm.new_text or reg.new_text,
                        find_text=llm.find_text or reg.find_text,
                        replace_text=llm.replace_text or reg.replace_text,
                        confidence=llm.confidence,
                        source_text=reg.source_text,
                        source_char_start=reg.source_char_start,
                        source_char_end=reg.source_char_end,
                        metadata={**reg.metadata, "llm_enhanced": True},
                    )
                else:
                    # Regex wins but fill in missing new_text from LLM
                    if not reg.new_text and llm.new_text:
                        result[i] = AmendmentInstruction(
                            **{**reg.__dict__,
                               "new_text": llm.new_text,
                               "metadata": {**reg.metadata, "new_text_from_llm": True}},
                        )
                break

    # Add LLM-only instructions
    for j, llm in enumerate(llm_insts):
        if j not in matched_llm:
            result.append(llm)

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class AmendmentParser:
    """
    Parse a wijzigingswet text into a list of AmendmentInstructions.

    Parameters
    ----------
    llm_url:
        Completions endpoint. Either the local vLLM completions endpoint
        (default) or an OpenAI-compatible chat endpoint such as
        "https://openrouter.ai/api/v1/chat/completions" (detected by the
        "chat/completions" suffix).
    model:
        Model name (Qwen/Qwen2.5-Coder-7B-Instruct by default; e.g.
        "stealth/ox-alpha" for OpenRouter).
    temperature:
        Low temperature for deterministic extraction (default 0.1).
    use_llm:
        Set to False to disable LLM entirely (useful for testing / offline).
    api_key:
        Bearer token for hosted endpoints (e.g. OpenRouter). Falls back to
        the OPENROUTER_API_KEY environment variable, then to a .env file in
        the repo root. Not needed for the local vLLM endpoint.
    """

    def __init__(
        self,
        llm_url: str = "http://localhost:8000/v1/completions",
        model: str = "Qwen/Qwen2.5-Coder-7B-Instruct",
        temperature: float = 0.1,
        use_llm: bool = True,
        api_key: Optional[str] = None,
    ) -> None:
        self.llm_url = llm_url
        self.model = model
        self.temperature = temperature
        self.use_llm = use_llm
        self.api_key = resolve_api_key(api_key)

    # ── Internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _extract_doc_target(title: str, preamble: str) -> str:
        """
        Extract the target law name from the document title or opening preamble.

        Used as a document-level fallback when no section intro ("De X wordt
        als volgt gewijzigd:") is present in a section.
        """
        import re as _re

        def _has_doc_type(s: str) -> bool:
            """Return True if s contains a doc-type keyword as a standalone word OR suffix."""
            # Allow doc type at end of compound word ("Onteigeningswet", "Arbeidswet")
            # by checking only the right boundary: followed by space, digit, or end-of-string.
            return bool(_re.search(_DOC_TYPE_ENDINGS + r'(?=\s|\d|$)', s, _re.I))

        def _norm(s: str) -> str:
            return " ".join(s.split())

        # Try preamble first — often contains "houdende wijziging van de X"
        m = _PREAMBLE_TARGET.search(preamble)
        if m:
            return _norm(m.group(1) or m.group(2) or "")

        # Try the title — strip leading gazette refs then look for wijziging pattern
        # \d+\w* handles suffixed issue numbers like "13a"
        clean = _re.sub(
            r'^(?:S\.?\s*B\.?|G\.?\s*B\.?|SB|GB|BTWS\s*B\.?)\s+\d{4}\s+(?:No\.?\s*)?\d+\w*\s+',
            '', title, flags=_re.I,
        ).strip()

        # "houdende [nadere] wijziging van [de/het] X"
        m = _PREAMBLE_TARGET.search(clean)
        if m:
            return _norm(m.group(1) or m.group(2) or "")

        # "wijziging van [de/het] X" (unquoted, doc-type ending)
        m = _re.search(
            r'\bwijziging\s+van\s+(?:de\s+|het\s+)?'
            r'([A-Z][A-Za-zÀ-ÿ\s\-\.]+?' + _DOC_TYPE_ENDINGS + r'(?:\s+\d{4})?)\b',
            clean, _re.I,
        )
        if m:
            return _norm(m.group(1))

        # "[nadere] Wijziging[en] X" at start of cleaned title (case-insensitive)
        # Note: (?:en)? matches the optional "en" plural suffix, NOT mandatory 'e' + optional 'n'
        m = _re.match(r'^(?:nadere\s+)?[Ww]ijziging(?:en)?\s+(.+)', clean, _re.I)
        if m:
            candidate = _norm(m.group(1)).rstrip('.,;(')
            # Strip trailing gazette refs that crept in ("Wet X S B 2023 no 45")
            candidate = _re.sub(
                r'\s+(?:S\.?\s*B\.?|G\.?\s*B\.?|SB|GB)\s+\d{4}.*$', '', candidate, flags=_re.I
            ).strip()
            if _has_doc_type(candidate):
                return candidate

        # "LawName [year] wijziging ..." — law name precedes wijziging keyword
        m = _re.match(
            r'^([A-Z][A-Za-zÀ-ÿ\s\-\.]+?' + _DOC_TYPE_ENDINGS + r'(?:\s+\d{4})?)\s+wijziging\b',
            clean, _re.I,
        )
        if m:
            return _norm(m.group(1))

        # Generic last resort: everything before "(nadere) wijziging", cleaned of
        # preamble noise ("houdende", trailing prepositions).
        m = _re.match(r'^(.+?)\s+(?:nadere\s+)?wijziging\b', clean, _re.I)
        if m:
            candidate = _norm(m.group(1))
            # Remove trailing preamble fragments that aren't part of a law name
            candidate = _re.sub(
                r'\s+(?:houdende|van\s+de|van\s+het|van|en)\s*$', '', candidate, _re.I
            ).strip().rstrip('.,;(')
            if _has_doc_type(candidate) and 4 < len(candidate) < 80:
                return candidate

        return ""

    # ── Public entry point ─────────────────────────────────────────────────

    def parse(
        self,
        text: str,
        title: str = "",
        staatsblad_ref: Optional[str] = None,
        effective_date_raw: Optional[str] = None,
        base_work_ref: str = "",
    ) -> ParsedAmendment:
        """
        Parse a complete wijzigingswet text.

        Parameters
        ----------
        text:
            Full document text (post-OCR).
        title:
            Optional document title. Helps identify the amendment itself.
        staatsblad_ref:
            Staatsblad reference of the amendment (from classifier).
        effective_date_raw:
            In-force date string (from classifier, or extracted here).
        base_work_ref:
            Known base-law work ID or reference from the amendment_links table.
            Used as final fallback when ``_extract_doc_target`` returns nothing.

        Returns
        -------
        ParsedAmendment with all extracted instructions.
        """
        # Extract effective date if not provided by classifier
        if not effective_date_raw:
            m = _EFFECTIVE_DATE.search(text)
            effective_date_raw = m.group(1) if m else None

        # Extract own SB ref if not provided
        if not staatsblad_ref:
            m = _SB_REF.search(title + "\n" + text[:500])
            if m:
                staatsblad_ref = f"S.B. {m.group(1)} no. {m.group(2)}"

        # Extract a document-level target law from title + opening preamble.
        # Fall back to the caller-supplied base_work_ref when extraction fails.
        doc_target_ref = self._extract_doc_target(title, text[:2000]) or base_work_ref

        # Split text into amendment sections (Artikel 1, Artikel 2 …)
        sections = self._split_into_sections(text)

        all_instructions: List[AmendmentInstruction] = []
        errors: List[str] = []
        used_llm = False

        for sec_idx, (own_article_nr, section_text) in enumerate(sections):
            # Skip the last section if it only has the in-force date
            if _EFFECTIVE_DATE.search(section_text) and not _SECTION_INTRO.search(section_text):
                continue

            target_ref, instructions = self._parse_section(
                section_text, own_article_nr, sec_idx,
                doc_target_ref=doc_target_ref,
            )

            # LLM pass when any instruction has low confidence
            low_conf = [i for i in instructions if i.confidence < LOW_CONFIDENCE_THRESHOLD]
            if self.use_llm and low_conf:
                used_llm = True
                llm_insts = _llm_parse_section(
                    section_text, target_ref,
                    self.llm_url, self.model, self.temperature, self.api_key,
                )
                if llm_insts:
                    instructions = _merge_instructions(instructions, llm_insts)
                    logger.debug(
                        "Section %d: merged %d regex + %d LLM → %d total",
                        sec_idx, len(instructions), len(llm_insts),
                        len(_merge_instructions(instructions, llm_insts)),
                    )

            all_instructions.extend(instructions)

        return ParsedAmendment(
            amendment_work_ref=title or "",
            staatsblad_ref=staatsblad_ref,
            effective_date_raw=effective_date_raw,
            instructions=all_instructions,
            parse_method="combined" if used_llm else "regex",
            errors=errors,
        )

    def _split_into_sections(self, text: str) -> List[Tuple[str, str]]:
        """
        Split the document into amendment sections by "Artikel N" boundaries.

        Each section is the text of one amendment article (Artikel 1, Artikel 2 …).
        Sections that don't contain an instruction intro (e.g. preamble, in-force
        date article) are still returned; the caller skips non-instruction sections.

        Returns list of (article_number_str, section_text).
        """
        # Remove the explanatory memo section (Memorie / Nota van Toelichting).
        # When fragment positions are all 0 the memo may appear mid-text rather
        # than at the very end; operative articles that follow it must be kept.
        _MEMO_BOUNDARY = re.compile(
            r'\n\s*(?:NOTA|MEMORIE)\s+VAN\s+TOELICHTING\b', re.I
        )
        m_memo = _MEMO_BOUNDARY.search(text)
        if m_memo:
            before = text[:m_memo.start()]
            after  = text[m_memo.start():]
            # Resume after the memo at the next "Artikel N" boundary
            resume = _OWN_ARTICLE.search(after)
            if resume:
                text = before + "\n\n" + after[resume.start():]
            else:
                text = before

        boundaries = list(_OWN_ARTICLE.finditer(text))
        if not boundaries:
            return [("1", text)]

        sections = []
        for i, m in enumerate(boundaries):
            nr = m.group(1)
            start = m.end()
            end = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(text)
            sections.append((nr, text[start:end].strip()))

        return sections

    def _parse_section(
        self,
        section_text: str,
        own_article_nr: str,
        sec_idx: int,
        doc_target_ref: str = "",
    ) -> Tuple[str, List[AmendmentInstruction]]:
        """
        Parse one amendment section into (target_law_ref, instructions).

        Handles both multi-block sections (A. B. C. …) and single-modification
        sections (direct "Artikel X van de WetNaam wordt …").
        """
        # Detect target law from section intro
        target_ref = ""
        m = _SECTION_INTRO.search(section_text)
        if m:
            target_ref = " ".join(m.group(1).split())
            # Instruction text starts after the intro line
            section_body = section_text[m.end():].strip()
        else:
            # May be a direct single-modification; also try preamble pattern
            m = _PREAMBLE_TARGET.search(section_text)
            if m:
                raw = (m.group(1) or m.group(2) or "")
                target_ref = " ".join(raw.split())
            section_body = section_text

        # Split into labelled blocks
        blocks = _split_blocks(section_body)

        instructions: List[AmendmentInstruction] = []

        for label, block_text in blocks:
            if not block_text.strip():
                continue

            # Try to extract target_ref from block if not in section header
            if not target_ref:
                m2 = _SINGLE_MOD_INTRO.search(block_text)
                if m2:
                    target_ref = " ".join(m2.group(3).split())

            block_instructions = _parse_block(
                block_text,
                target_ref or doc_target_ref or f"[section {own_article_nr}]",
                char_offset=0,
            )
            instructions.extend(block_instructions)

        # ── Inline replacement fallback ────────────────────────────────────
        # Some Surinamese amendments present each modified article as a bare
        # section (no "Artikel X wordt vervangen door:" header) — the section
        # text IS the new article text.  Detect this when:
        #   • No instructions extracted yet
        #   • We know the target law (doc_target_ref)
        #   • The section's own article number is numeric (I/II are not articles)
        #   • The section text is substantive (>80 chars)
        #   • No strong instruction verb is present (otherwise it's a missed match)
        #   • No signature block or publication-notice header (those are noise)
        real_found = [i for i in instructions
                      if i.metadata.get("parse_error") is None]
        if (not real_found
                and doc_target_ref
                and re.match(r'^\d+$', own_article_nr)
                and 80 < len(section_body.strip()) < 2500
                and not _STRONG_INSTRUCTION.search(section_body)
                and not _EFFECTIVE_DATE.search(section_body)
                and not _SIGNATURE_BLOCK.search(section_body)
                and not _PUB_NOTICE_HDR.search(section_body)):
            instructions.append(AmendmentInstruction(
                operation=OperationType.REPLACE,
                target_work_ref=doc_target_ref,
                target_article=own_article_nr,
                new_text=section_body.strip(),
                confidence=0.40,   # low: inferred, not explicitly stated
                source_text=section_body,
                source_char_start=0,
                source_char_end=len(section_body),
                metadata={"inferred": "inline_replacement"},
            ))

        return target_ref, instructions
