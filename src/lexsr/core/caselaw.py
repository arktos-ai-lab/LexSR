"""
Case law (rechtspraak) data models.

Extends the FRBR model for court decisions with:
- ECLI identifiers
- Court hierarchies
- Consideration (r.o.) fragments
- Citation links to legislation
- Judicial annotations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from .models import Work, Expression, Fragment, SourceType, DocumentStatus


class CourtLevel(Enum):
    """Hierarchy of courts in Suriname."""
    SUPREME_COURT = "supreme_court"          # Hoge Raad
    COURT_OF_JUSTICE = "court_of_justice"    # Hof van Justitie
    DISTRICT_COURT = "district_court"        # Kantongerecht
    ADMINISTRATIVE_COURT = "administrative"   # Administrative law
    CONSTITUTIONAL_COURT = "constitutional"   # Constitutional review
    OTHER = "other"


class CaseType(Enum):
    """Types of legal cases."""
    CIVIL = "civil"
    CRIMINAL = "criminal"
    ADMINISTRATIVE = "administrative"
    CONSTITUTIONAL = "constitutional"
    TAX = "tax"
    LABOR = "labor"
    OTHER = "other"


class JudgmentType(Enum):
    """Types of judicial decisions."""
    FINAL_JUDGMENT = "final_judgment"
    INTERLOCUTORY = "interlocutory"
    PRELIMINARY_RELIEF = "preliminary_relief"
    APPEAL = "appeal"
    CASSATION = "cassation"
    ADVISORY_OPINION = "advisory_opinion"


@dataclass
class Court:
    """
    A court that issues decisions.

    Attributes:
        id: Unique court identifier
        name: Official court name
        level: Court level in hierarchy
        jurisdiction: Geographic jurisdiction
        specialized: Whether this is a specialized court
    """
    id: str
    name: str
    level: CourtLevel
    jurisdiction: str = "SR"
    specialized: bool = False
    established: Optional[date] = None
    dissolved: Optional[date] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CourtDecision(Work):
    """
    A court decision (extends Work for FRBR compatibility).

    Attributes:
        ecli: European Case Law Identifier
        court: Court that issued the decision
        case_type: Type of case (civil, criminal, etc.)
        judgment_type: Type of judgment
        case_number: Internal court case number
        decision_date: Date of decision
        publication_date: Date published
        parties: List of party names (anonymized if needed)
        judges: List of judge names
        subject_matter: Subject classification
        procedural_history: Previous decisions in same case
    """
    ecli: str = ""
    court_id: str = ""
    case_type: CaseType = CaseType.OTHER
    judgment_type: JudgmentType = JudgmentType.FINAL_JUDGMENT
    case_number: str = ""
    decision_date: Optional[date] = None
    publication_date: Optional[date] = None
    parties: List[str] = field(default_factory=list)
    judges: List[str] = field(default_factory=list)
    subject_matter: List[str] = field(default_factory=list)
    procedural_history: List[str] = field(default_factory=list)

    def __post_init__(self):
        # Override source_type for case law
        if not self.source_type or self.source_type != SourceType.CASE_LAW:
            object.__setattr__(self, "source_type", SourceType.CASE_LAW)

        super().__post_init__()


@dataclass
class Consideration(Fragment):
    """
    A rechtsoverweging (r.o.) - legal consideration in a judgment.

    Court decisions are structured as:
    - Facts
    - Legal considerations (r.o. 1, r.o. 2, etc.)
    - Decision

    Each consideration is a Fragment with special properties.
    """
    consideration_number: str = ""
    is_decisive: bool = False
    cites_legislation: List[str] = field(default_factory=list)
    cites_case_law: List[str] = field(default_factory=list)
    legal_principle: Optional[str] = None

    def __post_init__(self):
        # Set fragment_type to CONSIDERATION
        from .models import FragmentType
        object.__setattr__(self, "fragment_type", FragmentType.CONSIDERATION)
        # Consideration number becomes the fragment number
        if self.consideration_number and not self.number:
            object.__setattr__(self, "number", self.consideration_number)


@dataclass
class JudicialAnnotation:
    """
    Expert annotation/commentary on a court decision.

    Allows legal experts to provide:
    - Analysis of the decision
    - Criticism or support
    - Comparison with other cases
    - Practical implications
    """
    id: str
    decision_id: str
    decision_uri: str
    author: str
    author_affiliation: Optional[str] = None
    title: str = ""
    summary: str = ""
    full_text: str = ""
    annotation_type: str = "commentary"  # commentary, critique, case_note
    publication: Optional[str] = None
    publication_date: Optional[date] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)
    related_cases: List[str] = field(default_factory=list)
    related_legislation: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseCitation:
    """
    A citation relationship between cases or between case and legislation.

    Types of citation relationships:
    - followed: This case follows the precedent
    - distinguished: This case distinguishes itself from precedent
    - overruled: This case overrules a previous case
    - applied: This case applies legislation
    - interpreted: This case interprets legislation
    - cited: General citation without specific relationship
    """
    id: str
    source_uri: str
    target_uri: str
    citation_type: str
    context: str = ""
    source_fragment_id: Optional[str] = None
    confidence: float = 1.0
    extracted_by: str = "manual"
    extracted_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
