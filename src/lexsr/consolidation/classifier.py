"""
Document classifier for Surinamese and Dutch legal texts.

Classifies an ingested document as one of:
  BASE_LAW   -- standalone wet, staatsblad publication (primary legislation)
  AMENDMENT  -- wijzigingswet that modifies one or more existing laws
  DECREE     -- uitvoeringsbesluit, ministerieel besluit, beschikking
  CASE_LAW   -- court decision (vonnis, arrest, beschikking HvJ)
  REGULATION -- nadere regels, uitvoeringsregeling, ministeriële regeling
  UNKNOWN    -- insufficient signal

Two-pass strategy
-----------------
Pass 1 — Regex scoring (fast, deterministic)
  Each pattern fires a positive or negative score toward a document type.
  If any type reaches confidence >= REGEX_CONFIDENT_THRESHOLD it is returned
  immediately.  This handles the majority of well-formatted documents.

Pass 2 — LLM via local Qwen API (fallback for ambiguous cases)
  Sends the first CONTEXT_CHARS characters to the local vLLM endpoint and
  parses a JSON response.  The two results are then combined: the LLM can
  override regex when it has higher confidence, otherwise regex wins.

For amendments, both passes also extract:
  - The target law(s) being amended (as AmendmentTarget objects)
  - The effective date (raw text)
  - The Staatsblad reference of the amendment itself

Usage
-----
    classifier = DocumentClassifier()
    result = classifier.classify(text, title="Wet van 21 juli 1975 S.B. 1975 no. 10")
    if result.document_type == DocumentType.AMENDMENT:
        for target in result.amendment_targets:
            print(target.raw_ref, target.staatsblad_ref)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .llm_client import call_llm, resolve_api_key

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGEX_CONFIDENT_THRESHOLD = 0.85   # skip LLM when regex is this confident
CONTEXT_CHARS = 3_000              # chars sent to LLM
LLM_TIMEOUT = 20                   # seconds before giving up on LLM call

# Score weights: each matching signal adds this much to a type's score
_W_STRONG = 0.35
_W_MEDIUM = 0.20
_W_WEAK   = 0.08


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class DocumentType(Enum):
    BASE_LAW   = "base_law"
    AMENDMENT  = "amendment"
    DECREE     = "decree"
    CASE_LAW   = "case_law"
    REGULATION = "regulation"
    UNKNOWN    = "unknown"


@dataclass
class AmendmentTarget:
    """A law that is targeted/modified by an amendment document."""
    raw_ref: str                          # e.g. "de Arbeidswet 1963"
    staatsblad_ref: Optional[str] = None  # e.g. "S.B. 1963 no. 52"
    confidence: float = 1.0


@dataclass
class ClassificationResult:
    document_type: DocumentType
    confidence: float
    method: str                            # "regex", "llm", "combined"

    # Populated for AMENDMENT documents
    amendment_targets: List[AmendmentTarget] = field(default_factory=list)
    effective_date_raw: Optional[str] = None   # raw string, e.g. "1 januari 1975"
    staatsblad_ref: Optional[str] = None       # SB ref of the amendment itself

    reasoning: str = ""
    raw_signals: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
# All patterns are case-insensitive unless otherwise noted.

# ---- Amendment signals ---------------------------------------------------

# Titles or preambles explicitly announcing a wijziging
_AMEND_TITLE_STRONG = [
    re.compile(r'\bhoudende\s+wijziging\s+van\b', re.I),
    re.compile(r'\bwijzigingswet\b', re.I),
    re.compile(r'\btot\s+wijziging\s+van\b', re.I),
    re.compile(r'\bwijziging\s+van\s+(?:de\s+|het\s+)?[A-Z]', re.I),
]

# Body patterns that appear *inside* an amendment
_AMEND_BODY_STRONG = [
    re.compile(r'\bwordt\s+als\s+volgt\s+gewijzigd\b', re.I),
    re.compile(r'\bworden\s+(?:de\s+volgende\s+)?wijzigingen\s+aangebracht\b', re.I),
    re.compile(r'\bna\s+artikel\s+\d+\w*\s+wordt\s+(?:een\s+)?(?:nieuw\s+)?artikel\s+\d+\w*\s+ingevoegd\b', re.I),
    re.compile(r'\bde\s+artikelen\s+\d+\w*(?:\s+(?:tot\s+en\s+met|en)\s+\d+\w*)?\s+vervallen\b', re.I),
]

_AMEND_BODY_MEDIUM = [
    re.compile(r'\bwordt\s+(?:als\s+volgt\s+)?gewijzigd\b', re.I),
    re.compile(r'\bin\s+artikel\s+\d+\w*(?:\s+lid\s+\d+)?\s+van\s+de\b', re.I),
    re.compile(r'\bartikel\s+\d+\w*\s+vervalt\b', re.I),
    re.compile(r'\bvervangen\s+door\b', re.I),
    re.compile(r'\bworden\s+de\s+woorden\b', re.I),      # "worden de woorden X vervangen"
    re.compile(r'\bwordt\s+(?:de\s+zinsnede|de\s+aanhef|het\s+woord)\b', re.I),
]

# ---- Base law signals ----------------------------------------------------

_BASE_STRONG = [
    re.compile(r'^\s*Wet\s+van\s+\d', re.M),             # "Wet van 21 juli 1963"
    re.compile(r'\bde\s+nationale\s+assemblee\b', re.I),  # Suriname parliament
    re.compile(r'\bstaten\s+van\s+suriname\b', re.I),     # historical legislature
]

_BASE_MEDIUM = [
    re.compile(r'^\s*HOOFDSTUK\s+I\b', re.M | re.I),
    re.compile(r'^\s*Artikel\s+1\b', re.M),
    re.compile(r'\balgemene\s+bepalingen\b', re.I),
    re.compile(r'\bde\s+president\s+van\s+de\s+republiek\s+suriname\b', re.I),
    re.compile(r'\bgelet\s+op\b', re.I),                  # "gelet op" in preambles
    re.compile(r'\bheeft\s+besloten\b', re.I),
]

_BASE_WEAK = [
    re.compile(r'\bpreambule\b|\boverwegende\b', re.I),
]

# ---- Court case signals --------------------------------------------------

_CASE_STRONG = [
    re.compile(r'\bECLI:[A-Z]{2}:[A-Z]{1,8}:\d{4}:[A-Za-z0-9.]+\b'),
    re.compile(r'\bin\s+naam\s+van\s+de\s+(?:republiek|koningin|koning)\b', re.I),
    re.compile(r'\bhof\s+van\s+justitie\b', re.I),
    re.compile(r'\bhoge\s+raad\b', re.I),
]

_CASE_MEDIUM = [
    re.compile(r'\bvonnis\b', re.I),
    re.compile(r'\barrest\b', re.I),
    re.compile(r'\buitspraak\b', re.I),
    re.compile(r'\brolnummer\b|\bzaaknummer\b', re.I),
    re.compile(r'\brechtbank\b|\btribunaal\b|\bkantongerecht\b', re.I),
    re.compile(r'\beiser(?:es)?\b|\bgedaagde(?:n)?\b|\bverzoeker\b', re.I),
    re.compile(r'\bappellant\b|\bgeïntimeerde\b', re.I),
    re.compile(r'\boverweging(?:en)?\b.*\brecht\b', re.I),
]

_CASE_WEAK = [
    re.compile(r'\bpartijen\b', re.I),
    re.compile(r'\bprocedure\b', re.I),
]

# ---- Decree signals ------------------------------------------------------

_DECREE_STRONG = [
    re.compile(r'\bministerieel\s+besluit\b', re.I),
    re.compile(r'\buitvoeringsbesluit\b', re.I),
    re.compile(r'\blandsbesluit\b', re.I),
    re.compile(r'\bpresidentieel\s+besluit\b', re.I),
    re.compile(r'\bbesluit\s+van\s+de\s+president\b', re.I),
]

_DECREE_MEDIUM = [
    re.compile(r'\bbesluit\s+van\s+\d', re.I),          # "Besluit van 5 maart..."
    re.compile(r'\bbeschikking\s+van\s+de\s+minister\b', re.I),
]

# ---- Regulation signals --------------------------------------------------

_REGUL_STRONG = [
    re.compile(r'\bministeriële\s+regeling\b', re.I),
    re.compile(r'\buitvoeringsregeling\b', re.I),
    re.compile(r'\bnadere\s+regels\b', re.I),
    re.compile(r'\bregeling\s+van\s+de\s+minister\b', re.I),
]

# ---- Negative signals (things that indicate NOT amendment) ---------------

_NOT_AMENDMENT = [
    re.compile(r'\bECLI:[A-Z]{2}', re.I),               # court docs cannot be amendments
    re.compile(r'\bvonnis\b|\baarrest\b', re.I),
]

# ---- Amendment target extraction ----------------------------------------

# Extracts "de Arbeidswet 1963", "het Wetboek van Strafrecht" etc.
# after keywords that introduce the amended law
_TARGET_LAW_RE = re.compile(
    r'(?:'
    r'wijziging\s+van|'
    r'tot\s+wijziging\s+van|'
    r'houdende\s+wijziging\s+van|'
    r'van\s+de\s+(?=wet|het\s+wetboek)|'
    r'gewijzigd\s+(?:de|het)|'
    r'in\s+werking\s+treding\s+van\s+de\s+wijziging'
    r')\s+'
    r'(?:de\s+|het\s+)?'
    r'('
    r'[A-Z][A-Za-zÀ-ÿ\s\-]+'       # law name (capital start)
    r'(?:wet|besluit|wetboek|regeling|code|ordonnantie)'  # must end on legal word
    r'(?:\s+\d{4})?'                 # optional year
    r')',
    re.I,
)

# Also match "van <LawName YYYY>" in title line
_TARGET_TITLE_RE = re.compile(
    r'(?:van|betreffende)\s+'
    r'(?:de\s+|het\s+)?'
    r'([A-Z][A-Za-zÀ-ÿ\s\-]+(?:wet|besluit|wetboek|regeling|code|ordonnantie)(?:\s+\d{4})?)',
    re.I,
)

# Staatsblad ref of the amendment itself (to attach to the result)
_OWN_SB_RE = re.compile(
    r'(?:S\.?\s*B\.?|Staatsblad|Stb\.?)\s+(\d{4})\s*(?:,|no\.?|nr\.?)\s*(\d+)',
    re.I,
)

# Staatsblad ref associated with a named target law (for target resolution)
_TARGET_SB_RE = re.compile(
    r'\((?:S\.?\s*B\.?|Staatsblad|Stb\.?)\s+(\d{4})\s*(?:,|no\.?|nr\.?)\s*(\d+)\)',
    re.I,
)

# Effective date patterns
_EFFECTIVE_DATE_RE = re.compile(
    r'(?:in\s+werking\s+(?:ge)?treden?|van\s+kracht\s+(?:geworden?|word(?:en|t)))'
    r'\s+(?:op\s+|per\s+)?'
    r'(\d{1,2}\s+(?:januari|februari|maart|april|mei|juni|juli|augustus|'
    r'september|oktober|november|december)\s+\d{4})',
    re.I,
)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _score(text: str, patterns: List[re.Pattern], weight: float) -> Tuple[float, List[str]]:
    """Return cumulative score and list of matched pattern strings."""
    total = 0.0
    hits: List[str] = []
    for pat in patterns:
        if pat.search(text):
            total += weight
            hits.append(pat.pattern[:60])
    return total, hits


def _cap(score: float) -> float:
    """Keep score in [0, 1]."""
    return min(1.0, max(0.0, score))


# ---------------------------------------------------------------------------
# Amendment target extraction
# ---------------------------------------------------------------------------

def _extract_amendment_targets(text: str, title: str = "") -> List[AmendmentTarget]:
    """
    Extract all laws being amended from title + body text.

    Deduplicates by normalized law reference.
    """
    combined = (title + "\n" + text[:5_000]).strip()
    targets: Dict[str, AmendmentTarget] = {}

    for m in _TARGET_LAW_RE.finditer(combined):
        raw = m.group(1).strip().rstrip("., ")
        key = re.sub(r'\s+', ' ', raw.lower())
        if key not in targets:
            targets[key] = AmendmentTarget(raw_ref=raw, confidence=0.80)

    # Also try title-line pattern (slightly lower confidence)
    for m in _TARGET_TITLE_RE.finditer(title):
        raw = m.group(1).strip().rstrip("., ")
        key = re.sub(r'\s+', ' ', raw.lower())
        if key not in targets:
            targets[key] = AmendmentTarget(raw_ref=raw, confidence=0.65)

    # Try to pair each target with an SB reference that appears nearby
    for target in targets.values():
        pattern = re.escape(target.raw_ref[:20])
        vicinity = re.search(pattern, combined, re.I)
        if vicinity:
            window = combined[vicinity.start(): vicinity.start() + 200]
            sb = _TARGET_SB_RE.search(window)
            if sb:
                target.staatsblad_ref = f"S.B. {sb.group(1)} no. {sb.group(2)}"

    return list(targets.values())


def _extract_own_sb(text: str, title: str = "") -> Optional[str]:
    """Extract the Staatsblad reference of the document itself."""
    for src in (title, text[:1_000]):
        m = _OWN_SB_RE.search(src)
        if m:
            return f"S.B. {m.group(1)} no. {m.group(2)}"
    return None


def _extract_effective_date(text: str) -> Optional[str]:
    """Extract the raw effective date string if stated."""
    m = _EFFECTIVE_DATE_RE.search(text[:5_000])
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Regex classifier
# ---------------------------------------------------------------------------

def _regex_classify(text: str, title: str = "") -> ClassificationResult:
    """
    Score the document against all pattern groups.

    Returns the highest-scoring type and its confidence, plus extracted
    amendment metadata when applicable.
    """
    combined = (title + "\n" + text[:8_000]).strip()

    scores: Dict[DocumentType, float] = {t: 0.0 for t in DocumentType}
    signals: Dict[str, List[str]] = {t.value: [] for t in DocumentType}

    # ---- Amendment ----------------------------------------------------------
    s, hits = _score(combined, _AMEND_TITLE_STRONG, _W_STRONG)
    scores[DocumentType.AMENDMENT] += s
    signals["amendment"] += hits

    s, hits = _score(combined, _AMEND_BODY_STRONG, _W_STRONG)
    scores[DocumentType.AMENDMENT] += s
    signals["amendment"] += hits

    s, hits = _score(combined, _AMEND_BODY_MEDIUM, _W_MEDIUM)
    scores[DocumentType.AMENDMENT] += s
    signals["amendment"] += hits

    # Negative: court documents cannot be amendments
    for pat in _NOT_AMENDMENT:
        if pat.search(combined):
            scores[DocumentType.AMENDMENT] -= _W_STRONG

    # ---- Base law -----------------------------------------------------------
    s, hits = _score(combined, _BASE_STRONG, _W_STRONG)
    scores[DocumentType.BASE_LAW] += s
    signals["base_law"] += hits

    s, hits = _score(combined, _BASE_MEDIUM, _W_MEDIUM)
    scores[DocumentType.BASE_LAW] += s
    signals["base_law"] += hits

    s, hits = _score(combined, _BASE_WEAK, _W_WEAK)
    scores[DocumentType.BASE_LAW] += s
    signals["base_law"] += hits

    # ---- Court case ---------------------------------------------------------
    s, hits = _score(combined, _CASE_STRONG, _W_STRONG)
    scores[DocumentType.CASE_LAW] += s
    signals["case_law"] += hits

    s, hits = _score(combined, _CASE_MEDIUM, _W_MEDIUM)
    scores[DocumentType.CASE_LAW] += s
    signals["case_law"] += hits

    s, hits = _score(combined, _CASE_WEAK, _W_WEAK)
    scores[DocumentType.CASE_LAW] += s
    signals["case_law"] += hits

    # ---- Decree -------------------------------------------------------------
    s, hits = _score(combined, _DECREE_STRONG, _W_STRONG)
    scores[DocumentType.DECREE] += s
    signals["decree"] += hits

    s, hits = _score(combined, _DECREE_MEDIUM, _W_MEDIUM)
    scores[DocumentType.DECREE] += s
    signals["decree"] += hits

    # ---- Regulation ---------------------------------------------------------
    s, hits = _score(combined, _REGUL_STRONG, _W_STRONG)
    scores[DocumentType.REGULATION] += s
    signals["regulation"] += hits

    # ---- Pick winner --------------------------------------------------------
    # Exclude UNKNOWN from the max, fall back to it only if nothing scored
    typed_scores = {k: v for k, v in scores.items() if k != DocumentType.UNKNOWN}
    best_type = max(typed_scores, key=lambda t: typed_scores[t])
    best_score = _cap(typed_scores[best_type])

    if best_score < 0.10:
        best_type = DocumentType.UNKNOWN
        best_score = 0.0

    # ---- Extract amendment metadata -----------------------------------------
    targets: List[AmendmentTarget] = []
    effective_date: Optional[str] = None
    own_sb: Optional[str] = None

    if best_type == DocumentType.AMENDMENT or scores[DocumentType.AMENDMENT] > 0.15:
        targets = _extract_amendment_targets(text, title)
        effective_date = _extract_effective_date(text)
        own_sb = _extract_own_sb(text, title)

    all_scores = {t.value: round(v, 3) for t, v in scores.items()}
    return ClassificationResult(
        document_type=best_type,
        confidence=best_score,
        method="regex",
        amendment_targets=targets,
        effective_date_raw=effective_date,
        staatsblad_ref=own_sb,
        reasoning=f"Top signals for {best_type.value}: {signals.get(best_type.value, [])}",
        raw_signals={"scores": all_scores, "hits": signals},
    )


# ---------------------------------------------------------------------------
# LLM classifier
# ---------------------------------------------------------------------------

_LLM_PROMPT_TEMPLATE = """\
You are analyzing a Surinamese or Dutch legal document. Classify the document type.

Document excerpt ({n_chars} chars):
---
{text}
---

Respond with JSON only — no markdown, no other text:
{{
  "document_type": "base_law" | "amendment" | "decree" | "case_law" | "regulation" | "unknown",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one sentence>",
  "amendment_targets": [
    {{"raw_ref": "<law name>", "staatsblad_ref": "<S.B. YYYY no. NNN or null>"}}
  ],
  "effective_date_raw": "<date string or null>",
  "staatsblad_ref": "<S.B. YYYY no. NNN of THIS document, or null>"
}}

Rules:
- amendment_targets only for document_type "amendment"; else use []
- All keys must be present even if null
"""


def _llm_classify(
    text: str,
    title: str,
    llm_url: str,
    model: str,
    temperature: float,
    api_key: Optional[str] = None,
) -> Optional[ClassificationResult]:
    """
    Call the configured LLM endpoint (local Qwen/vLLM or an OpenAI-compatible
    chat endpoint such as OpenRouter) and parse the JSON response.

    Returns None on any network/parse failure so the caller can fall
    back gracefully.
    """
    excerpt = (title + "\n\n" + text)[:CONTEXT_CHARS]
    prompt = _LLM_PROMPT_TEMPLATE.format(text=excerpt, n_chars=len(excerpt))

    # Reasoning models (e.g. OpenRouter's stealth/ox-alpha) spend part of the
    # token budget on hidden reasoning before emitting the JSON answer; too
    # low a cap returns empty content (finish_reason="length") every time.
    raw_text = call_llm(
        prompt=prompt,
        llm_url=llm_url,
        model=model,
        temperature=temperature,
        max_tokens=1500,
        api_key=api_key,
        timeout=LLM_TIMEOUT,
    )
    if raw_text is None:
        return None

    # Strip any accidental markdown fences
    raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text, flags=re.M)
    raw_text = re.sub(r'\s*```\s*$', '', raw_text, flags=re.M)

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        # Try to salvage by finding the first {...} block
        m = re.search(r'\{.*\}', raw_text, re.S)
        if m:
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                logger.warning("LLM returned unparseable JSON: %r", raw_text[:200])
                return None
        else:
            logger.warning("LLM returned no JSON block: %r", raw_text[:200])
            return None

    try:
        doc_type = DocumentType(data.get("document_type", "unknown"))
    except ValueError:
        doc_type = DocumentType.UNKNOWN

    confidence = float(data.get("confidence", 0.5))

    targets: List[AmendmentTarget] = []
    for t in data.get("amendment_targets") or []:
        if isinstance(t, dict) and t.get("raw_ref"):
            targets.append(AmendmentTarget(
                raw_ref=t["raw_ref"],
                staatsblad_ref=t.get("staatsblad_ref") or None,
                confidence=confidence,
            ))

    effective = data.get("effective_date_raw")
    own_sb = data.get("staatsblad_ref")

    return ClassificationResult(
        document_type=doc_type,
        confidence=_cap(confidence),
        method="llm",
        amendment_targets=targets,
        effective_date_raw=effective if effective and effective != "null" else None,
        staatsblad_ref=own_sb if own_sb and own_sb != "null" else None,
        reasoning=data.get("reasoning", ""),
        raw_signals={"llm_response": data},
    )


# ---------------------------------------------------------------------------
# Combination logic
# ---------------------------------------------------------------------------

def _combine(
    regex: ClassificationResult,
    llm: ClassificationResult,
) -> ClassificationResult:
    """
    Merge regex and LLM results.

    Strategy:
    - If they agree on type: use higher confidence, merge amendment data
    - If they disagree: use whichever has higher confidence, but cap it
      at 0.75 to signal the uncertainty
    """
    if regex.document_type == llm.document_type:
        # Agreement — take best confidence and union amendment targets
        confidence = max(regex.confidence, llm.confidence)
        all_targets = {t.raw_ref.lower(): t for t in regex.amendment_targets}
        for t in llm.amendment_targets:
            key = t.raw_ref.lower()
            if key not in all_targets:
                all_targets[key] = t
        targets = list(all_targets.values())

        return ClassificationResult(
            document_type=regex.document_type,
            confidence=confidence,
            method="combined",
            amendment_targets=targets,
            effective_date_raw=llm.effective_date_raw or regex.effective_date_raw,
            staatsblad_ref=llm.staatsblad_ref or regex.staatsblad_ref,
            reasoning=f"regex+llm agree: {llm.reasoning}",
            raw_signals={**regex.raw_signals, **llm.raw_signals},
        )

    # Disagreement — pick higher confidence but mark uncertainty
    if llm.confidence >= regex.confidence:
        winner, loser = llm, regex
    else:
        winner, loser = regex, llm

    return ClassificationResult(
        document_type=winner.document_type,
        confidence=min(winner.confidence, 0.75),   # cap: we're not sure
        method="combined",
        amendment_targets=winner.amendment_targets,
        effective_date_raw=winner.effective_date_raw,
        staatsblad_ref=winner.staatsblad_ref,
        reasoning=(
            f"CONFLICT: regex={regex.document_type.value}({regex.confidence:.2f}) "
            f"llm={llm.document_type.value}({llm.confidence:.2f}). "
            f"Using {winner.method}. "
            f"LLM: {llm.reasoning}"
        ),
        raw_signals={**regex.raw_signals, **llm.raw_signals},
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class DocumentClassifier:
    """
    Classify legal documents and extract amendment metadata.

    Parameters
    ----------
    llm_url:
        Full URL of the completions endpoint. Either the local vLLM
        completions endpoint (default: http://localhost:8000/v1/completions)
        or an OpenAI-compatible chat endpoint such as
        "https://openrouter.ai/api/v1/chat/completions" (detected by the
        "chat/completions" suffix).
    model:
        Model name expected by the endpoint, e.g. "Qwen/Qwen2.5-Coder-7B-Instruct"
        for local vLLM or "stealth/ox-alpha" for OpenRouter.
    temperature:
        Sampling temperature for LLM calls.
    use_llm:
        If False, always use regex only (useful for testing or offline mode).
    confident_threshold:
        Regex confidence above which the LLM pass is skipped.
    api_key:
        Bearer token for hosted endpoints (e.g. OpenRouter). Falls back to
        the OPENROUTER_API_KEY environment variable, then to a .env file in
        the repo root. Not needed for the local vLLM endpoint.
    """

    def __init__(
        self,
        llm_url: str = "http://localhost:8000/v1/completions",
        model: str = "Qwen/Qwen2.5-Coder-7B-Instruct",
        temperature: float = 0.2,
        use_llm: bool = True,
        confident_threshold: float = REGEX_CONFIDENT_THRESHOLD,
        api_key: Optional[str] = None,
    ) -> None:
        self.llm_url = llm_url
        self.model = model
        self.temperature = temperature
        self.use_llm = use_llm
        self.confident_threshold = confident_threshold
        self.api_key = resolve_api_key(api_key)

    def classify(
        self,
        text: str,
        title: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        """
        Classify a document and return a ClassificationResult.

        Parameters
        ----------
        text:
            Full document text (plain text, post-OCR).
        title:
            Optional document title. When provided it is prepended to the
            scoring window, which significantly improves accuracy for
            well-titled documents.
        metadata:
            Optional extra metadata (unused currently, reserved for future
            signal injection, e.g. scraper source or file name).

        Returns
        -------
        ClassificationResult with document_type, confidence, and — for
        amendments — amendment_targets, effective_date_raw, and
        staatsblad_ref.
        """
        regex_result = _regex_classify(text, title)

        logger.debug(
            "Regex: type=%s conf=%.2f",
            regex_result.document_type.value,
            regex_result.confidence,
        )

        # High-confidence regex → skip LLM
        if not self.use_llm or regex_result.confidence >= self.confident_threshold:
            regex_result.method = "regex"
            return regex_result

        # LLM pass
        llm_result = _llm_classify(
            text, title, self.llm_url, self.model, self.temperature, self.api_key
        )

        if llm_result is None:
            logger.warning("LLM unavailable — using regex result")
            return regex_result

        logger.debug(
            "LLM:   type=%s conf=%.2f",
            llm_result.document_type.value,
            llm_result.confidence,
        )

        return _combine(regex_result, llm_result)

    def classify_batch(
        self,
        documents: List[Dict[str, str]],
    ) -> List[ClassificationResult]:
        """
        Classify multiple documents.

        Each dict in `documents` should have at least a "text" key, and
        optionally a "title" key.

        Returns results in the same order as input.
        """
        results = []
        for i, doc in enumerate(documents):
            text = doc.get("text", "")
            title = doc.get("title", "")
            try:
                result = self.classify(text, title)
                results.append(result)
            except Exception as exc:
                logger.error("Classification failed for doc %d: %s", i, exc)
                results.append(ClassificationResult(
                    document_type=DocumentType.UNKNOWN,
                    confidence=0.0,
                    method="error",
                    reasoning=str(exc),
                ))
        return results
