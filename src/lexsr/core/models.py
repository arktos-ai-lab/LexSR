"""
FRBR-based data model for legal documents.

Implements the four-level FRBR hierarchy adapted for legal texts:
  Work        -> the abstract legal act (what lawyers refer to)
  Expression  -> the text as it existed at a point in time
  Manifestation -> a published format (XML, HTML, PDF)
  Fragment    -> an addressable part (article, paragraph, section)

Every object carries provenance (source URL, retrieval timestamp, checksums)
so derived products can always be traced back to raw bytes.

Jurisdiction-agnostic: works with Suriname, Dutch, EU, or any legal system.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DocumentStatus(Enum):
    """Lifecycle status of a legal work."""
    DRAFT = "draft"
    IN_FORCE = "in_force"
    REPEALED = "repealed"
    EXPIRED = "expired"
    PENDING = "pending"          # published but not yet in force
    PARTIALLY_IN_FORCE = "partially_in_force"
    UNKNOWN = "unknown"


class SourceType(Enum):
    """Canonical source system identifiers."""
    # Generic document types
    LEGISLATION = "legislation"          # Primary legislation (laws, acts)
    DECREE = "decree"                    # Executive decrees, AMvBs
    GAZETTE = "gazette"                  # Official gazette publications
    CASE_LAW = "case_law"               # Court decisions
    REGULATION = "regulation"            # Subsidiary regulations
    TREATY = "treaty"                    # International treaties
    PARLIAMENTARY = "parliamentary"      # Parliamentary documents/debates

    # Source format types
    PDF_SCAN = "pdf_scan"               # Scanned PDF (requires OCR)
    PDF_DIGITAL = "pdf_digital"         # Born-digital PDF (text extractable)
    XML_SOURCE = "xml_source"           # Structured XML source
    HTML_SOURCE = "html_source"         # Web-scraped HTML

    # Suriname-specific sources
    DNA_SR = "dna_sr"                   # De Nationale Assemblée (parliament)
    SB_GAZETTE = "sb_gazette"           # Staatsblad van Suriname
    GB_GAZETTE = "gb_gazette"           # Gouvernementsblad (historical)

    # EU/International sources
    EURLEX = "eurlex"                   # EUR-Lex (EU legislation)
    EU_CASELAW = "eu_caselaw"           # European Court of Justice
    ECLI = "ecli"                       # Case law via ECLI identifier
    CELEX = "celex"                     # EU CELEX identifiers

    # Institutional
    LINKED_DATA = "linked_data"         # Government linked data

    OTHER = "other"


class ManifestationType(Enum):
    """Format of a published manifestation."""
    XML = "xml"
    HTML = "html"
    PDF = "pdf"
    RDF = "rdf"
    JSON = "json"
    PLAIN_TEXT = "text"


class AnchorType(Enum):
    """Strategy used to locate a fragment within a manifestation."""
    STRUCTURAL = "structural"    # XPath / structural path (best)
    TEXT_HASH = "text_hash"      # hash of normalized snippet (fallback)
    OFFSET = "offset"            # character offsets (fragile, last resort)


class FragmentType(Enum):
    """Types of addressable fragments in legal texts (English canonical names)."""
    # Legislation structure
    BOOK = "book"
    TITLE = "title"
    CHAPTER = "chapter"
    SECTION = "section"
    PARAGRAPH_GROUP = "paragraph_group"
    ARTICLE = "article"
    PARAGRAPH = "paragraph"          # sub-article paragraph (lid)
    SUB = "sub"                      # lettered sub-item (a, b, c)
    ANNEX = "annex"

    # Case law structure
    CONSIDERATION = "consideration"  # rechtsoverweging / r.o.
    FACTS = "facts"
    OPINION = "opinion"
    DECISION = "decision"
    DISSENT = "dissent"

    # Parliamentary structure
    AGENDA_ITEM = "agenda_item"
    SPEAKER_TURN = "speaker_turn"
    MOTION = "motion"
    AMENDMENT = "amendment"

    # Generic
    SECTION_GENERIC = "section_generic"
    PREAMBLE = "preamble"
    RECITAL = "recital"              # EU recitals


# Aliases for Dutch terminology -> English FragmentType
# Used for backward compatibility and Dutch-language document parsing
FRAGMENT_ALIASES: Dict[str, FragmentType] = {
    "boek": FragmentType.BOOK,
    "titel": FragmentType.TITLE,
    "hoofdstuk": FragmentType.CHAPTER,
    "afdeling": FragmentType.SECTION,
    "paragraaf": FragmentType.PARAGRAPH_GROUP,
    "artikel": FragmentType.ARTICLE,
    "lid": FragmentType.PARAGRAPH,
    "sub": FragmentType.SUB,
    "bijlage": FragmentType.ANNEX,
    "ro": FragmentType.CONSIDERATION,
    "feiten": FragmentType.FACTS,
    "conclusie": FragmentType.OPINION,
    "beslissing": FragmentType.DECISION,
    "dissent": FragmentType.DISSENT,
    "agendapunt": FragmentType.AGENDA_ITEM,
    "spreekbeurt": FragmentType.SPEAKER_TURN,
    "motie": FragmentType.MOTION,
    "amendement": FragmentType.AMENDMENT,
    "sectie": FragmentType.SECTION_GENERIC,
    "preambule": FragmentType.PREAMBLE,
    "overweging": FragmentType.RECITAL,
}


def resolve_fragment_type(name: str) -> FragmentType:
    """Resolve a fragment type name, checking aliases first."""
    if name in FRAGMENT_ALIASES:
        return FRAGMENT_ALIASES[name]
    return FragmentType(name)


# ---------------------------------------------------------------------------
# Core FRBR classes
# ---------------------------------------------------------------------------

@dataclass
class TemporalExtent:
    """A time interval during which something is/was valid or in force."""
    start: Optional[date] = None
    end: Optional[date] = None       # None = still in force / open-ended

    def contains(self, query_date: date) -> bool:
        """Check whether *query_date* falls within this extent."""
        if self.start and query_date < self.start:
            return False
        if self.end and query_date > self.end:
            return False
        return True

    def is_open(self) -> bool:
        return self.end is None

    def __repr__(self) -> str:
        s = self.start.isoformat() if self.start else "..."
        e = self.end.isoformat() if self.end else "..."
        return f"[{s} → {e}]"


@dataclass
class FragmentAnchor:
    """
    Locator that ties a Fragment to a specific position inside a Manifestation.

    Two strategies, used together for resilience:
      1. structural_path: XPath or structural address (preferred)
      2. text_hash: SHA-256 of normalized text (fallback when structure shifts)
    """
    anchor_type: AnchorType
    structural_path: Optional[str] = None
    text_hash: Optional[str] = None
    text_preview: Optional[str] = None
    char_offset_start: Optional[int] = None
    char_offset_end: Optional[int] = None
    heading_context: Optional[str] = None

    @staticmethod
    def compute_text_hash(text: str) -> str:
        """SHA-256 of whitespace-normalized, lowercased text."""
        normalized = re.sub(r"\s+", " ", text.strip().lower())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @classmethod
    def from_structural(cls, path: str, text: str = "",
                        heading: str = "") -> FragmentAnchor:
        """Create a structural anchor with an optional text-hash fallback."""
        text_hash = cls.compute_text_hash(text) if text else None
        preview = text[:120].strip() if text else None
        return cls(
            anchor_type=AnchorType.STRUCTURAL,
            structural_path=path,
            text_hash=text_hash,
            text_preview=preview,
            heading_context=heading or None,
        )

    @classmethod
    def from_text(cls, text: str, heading: str = "") -> FragmentAnchor:
        """Create a text-hash anchor (when no structural path is available)."""
        return cls(
            anchor_type=AnchorType.TEXT_HASH,
            text_hash=cls.compute_text_hash(text),
            text_preview=text[:120].strip(),
            heading_context=heading or None,
        )


@dataclass
class Work:
    """
    The abstract legal act -- the thing lawyers refer to.

    Examples:
      - "Arbeidswet 1963" (Suriname labour law)
      - A court decision with ECLI identifier
      - EU Regulation 2016/679 (GDPR)
    """
    # --- Identity ---
    id: str
    uri: str
    source_type: SourceType
    official_id: str

    # --- Descriptive ---
    title: str
    short_title: Optional[str] = None
    document_type: str = ""
    jurisdiction: str = "SR"
    language: str = "nl"
    subject_areas: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)

    # --- Lifecycle ---
    status: DocumentStatus = DocumentStatus.UNKNOWN
    date_enacted: Optional[date] = None
    date_first_in_force: Optional[date] = None

    # --- Provenance ---
    source_url: Optional[str] = None
    source_api: Optional[str] = None
    retrieved_at: Optional[datetime] = None

    # --- Relations (stored as Work IDs/URIs) ---
    replaces: List[str] = field(default_factory=list)
    replaced_by: List[str] = field(default_factory=list)
    implements: List[str] = field(default_factory=list)
    implemented_by: List[str] = field(default_factory=list)

    # --- Metadata bag ---
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.uri:
            raise ValueError("Work must have a canonical URI")


@dataclass
class Expression:
    """
    A specific textual version of a Work -- the text as it existed at a point in time.

    For legislation this is a consolidated version.
    For case law there is typically one expression per work.
    """
    # --- Identity ---
    id: str
    uri: str
    work_id: str
    work_uri: str

    # --- Temporal ---
    version_date: date
    in_force: TemporalExtent = field(default_factory=TemporalExtent)

    # --- Descriptive ---
    title: Optional[str] = None
    language: str = "nl"
    status: DocumentStatus = DocumentStatus.UNKNOWN

    # --- Provenance ---
    source_url: Optional[str] = None
    retrieved_at: Optional[datetime] = None
    checksum: Optional[str] = None

    # --- Navigation ---
    previous_expression_id: Optional[str] = None
    next_expression_id: Optional[str] = None

    # --- Content (optional; may be in Manifestation instead) ---
    full_text: Optional[str] = None

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Manifestation:
    """
    A published format of an Expression -- the actual bytes retrieved.

    Examples: the XML source, the HTML from a portal, the scanned PDF.
    Raw bytes are stored immutably in Bronze storage; this object points to them.
    """
    # --- Identity ---
    id: str
    uri: str
    expression_id: str
    expression_uri: str

    # --- Format ---
    format: ManifestationType
    media_type: str = ""

    # --- Raw storage ---
    storage_path: Optional[str] = None
    checksum_sha256: Optional[str] = None
    byte_size: Optional[int] = None

    # --- Provenance ---
    source_url: Optional[str] = None
    retrieved_at: Optional[datetime] = None
    http_headers: Dict[str, str] = field(default_factory=dict)

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Fragment:
    """
    An addressable part of an Expression: article, paragraph, section, etc.

    Fragments are the atomic unit of citation, linking, and retrieval.
    Every fragment has:
      - a canonical URI
      - one or more anchors into manifestations
      - its own text content
      - heading hierarchy for context
    """
    # --- Identity ---
    id: str
    uri: str
    expression_id: str
    expression_uri: str
    work_id: str

    # --- Structure ---
    fragment_type: FragmentType
    number: str = ""
    title: Optional[str] = None
    parent_fragment_id: Optional[str] = None
    position: int = 0
    depth: int = 0

    # --- Content ---
    text: str = ""
    heading_path: List[str] = field(default_factory=list)

    # --- Anchors ---
    anchors: List[FragmentAnchor] = field(default_factory=list)

    # --- Provenance ---
    extraction_method: str = "structural"  # "structural", "regex", "ocr", "ml"
    confidence: float = 1.0
    extracted_at: Optional[datetime] = None

    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def anchor_text_hash(self) -> Optional[str]:
        """Return the text-hash anchor if available."""
        for a in self.anchors:
            if a.text_hash:
                return a.text_hash
        if self.text:
            return FragmentAnchor.compute_text_hash(self.text)
        return None


# ---------------------------------------------------------------------------
# Citation graph
# ---------------------------------------------------------------------------

class CitationType(Enum):
    """Direction and nature of a citation between legal documents."""
    LAW_TO_LAW = "law_to_law"       # law article cites another law/article
    LAW_TO_CASE = "law_to_case"     # law cites a court decision (rare)
    CASE_TO_LAW = "case_to_law"     # court decision cites a law/article
    CASE_TO_CASE = "case_to_case"   # court decision cites another decision
    UNKNOWN = "unknown"


@dataclass
class Citation:
    """
    A directed citation from one fragment (or work) to another.

    Temporal: citations are version-aware.  A citation in Arbeidswet 1963
    art. 4 as of 2024-01-15 points to the Grondwet 1987 art. 19 version
    that was in force on that date.

    Resolved vs. unresolved:
      - source is always resolved (we know which document it came from)
      - target may be unresolved if the cited work is not yet in the store
    """
    id: str
    citation_type: CitationType

    # --- Source (always resolved) ---
    source_work_id: str
    source_fragment_id: Optional[str] = None   # None = document-level
    source_version_date: Optional[date] = None  # Expression version that contains this

    # --- Target (may be unresolved) ---
    target_work_id: Optional[str] = None        # None = not yet resolved
    target_fragment_id: Optional[str] = None    # None = only work-level resolved
    target_version_date: Optional[date] = None  # version of target being cited

    # --- Raw evidence ---
    raw_text: str = ""                           # exact text that was cited
    confidence: float = 1.0                      # extraction confidence

    # --- Temporal validity ---
    # Citation is valid from the version it first appeared until the version
    # in which it was amended away (None = still valid).
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None

    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Amendment links
# ---------------------------------------------------------------------------

@dataclass
class AmendmentLink:
    """
    Structural link: a wijzigingswet (amendment law) targets a base law.

    This is a higher-level relationship than a Citation — it records that
    one Work *modifies* another Work, independent of which specific articles
    are involved (those are captured by AmendmentInstructions in the
    consolidation module).
    """
    id: str
    amendment_work_id: str        # the wijzigingswet
    base_work_id: Optional[str]   # the law being amended (None if unresolved)
    base_work_ref: str            # raw reference text ("Arbeidswet 1963")
    effective_date: Optional[date] = None   # when the amendment takes effect
    staatsblad_ref: Optional[str] = None    # "S.B. 1975 no. 10"
    confidence: float = 1.0
    resolved: bool = False        # True once base_work_id is filled in
    metadata: Dict[str, Any] = field(default_factory=dict)
