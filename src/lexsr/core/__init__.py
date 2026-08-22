"""
Core module for the Legal Knowledge Fabric.

Provides the foundational FRBR data model, canonical URI system,
temporal versioning, persistent storage, citation resolver, and
link integrity checking for Dutch legal documents.

This module is the backbone of the system - all other components
(ingestion, evaluation, API, improvement) build on these primitives.
"""

__version__ = "0.3.0"

from .models import (
    AmendmentLink,
    AnchorType,
    Citation,
    CitationType,
    DocumentStatus,
    Expression,
    Fragment,
    FragmentAnchor,
    FragmentType,
    Manifestation,
    ManifestationType,
    SourceType,
    TemporalExtent,
    Work,
)

from .identifiers import (
    LegalURI,
    URIScheme,
    FragmentPath,
    parse_uri,
    build_uri,
    normalize_uri,
    AbbreviationRegistry,
    resolve_abbreviation,
)

from .versioning import (
    VersionChain,
    VersionDiff,
    TemporalIndex,
)

from .resolver import (
    CitationResolver,
    ReferenceParser,
    ResolvedReference,
    ParsedReference,
    ReferenceType,
    ResolutionStatus,
)

from .integrity import (
    LinkIntegrityChecker,
    IntegrityReport,
    IntegrityIssue,
)

__all__ = [
    # FRBR models
    "Work",
    "Expression",
    "Manifestation",
    "Fragment",
    "FragmentAnchor",
    "TemporalExtent",
    "DocumentStatus",
    "SourceType",
    "ManifestationType",
    "AnchorType",
    "FragmentType",
    # Citation graph
    "Citation",
    "CitationType",
    # Amendment links
    "AmendmentLink",
    # URI system
    "LegalURI",
    "URIScheme",
    "FragmentPath",
    "parse_uri",
    "build_uri",
    "normalize_uri",
    "AbbreviationRegistry",
    "resolve_abbreviation",
    # Versioning
    "VersionChain",
    "VersionDiff",
    "TemporalIndex",
    # Resolver
    "CitationResolver",
    "ReferenceParser",
    "ResolvedReference",
    "ParsedReference",
    "ReferenceType",
    "ResolutionStatus",
    # Integrity
    "LinkIntegrityChecker",
    "IntegrityReport",
    "IntegrityIssue",
]
