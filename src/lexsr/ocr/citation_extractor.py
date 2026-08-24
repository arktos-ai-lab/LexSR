"""
Temporal Citation extraction for OCR pipeline.

Extracts legal citations from OCR text and resolves them to specific VERSIONS.

Key features:
- Version-aware: Resolves citations to Expression URIs (specific versions)
- Temporal validity: Tracks when citations were added/removed
- Amendment detection: Identifies when articles changed
- Bidirectional linking: Both outgoing and incoming citations

Example:
    Arbeidswet 1963, Art 4 (version 2024-01-15) cites:
    → Grondwet 1987, Art 19 (version 2024-01-15)

    When Arbeidswet Art 4 was amended in 2024, the citation was added.
    Before 2024, it didn't cite Grondwet Art 19.

This bridges OCR → FRBR conversion with temporal citation resolution.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from ..core.resolver import CitationResolver, ResolvedReference
from ..core.models import Citation, CitationType, Fragment, TemporalExtent, Work
from ..core.title_matching import resolve_work_by_title

logger = logging.getLogger(__name__)


@dataclass
class ExtractedCitation:
    """
    A temporal citation extracted from OCR text.

    Tracks WHEN a citation was valid, not just that it exists.
    """
    source_fragment_uri: str  # Fragment containing the citation (versioned!)
    target_uri: Optional[str]  # Resolved target URI (versioned!)
    raw_text: str  # Raw citation text
    confidence: float  # Resolution confidence
    position: int  # Character position in source text
    citation_type: str  # "law_to_law", "case_to_law", etc.

    # TEMPORAL INFORMATION - Key for version-aware citations
    source_version_date: Optional[date] = None  # When source version was published
    target_version_date: Optional[date] = None  # Which version of target is cited
    valid_from: Optional[date] = None  # When citation became valid
    valid_to: Optional[date] = None    # When citation was removed (if amended)

    # Additional metadata
    amendment_info: Optional[str] = None  # Info about when citation was added


class CitationExtractor:
    """
    Extract and resolve citations from OCR-processed text.

    Integrates with:
    - OCR pipeline (gets fragment text)
    - Citation resolver (resolves references)
    - FRBR store (saves Citation objects)

    Usage:
        extractor = CitationExtractor(store)

        # Extract citations from fragments
        citations = extractor.extract_from_fragments(fragments)

        # Save to store
        for citation in citations:
            store.save_citation(citation)
    """

    def __init__(self, store=None):
        """
        Initialize citation extractor.

        Args:
            store: Optional CanonicalStore for resolving citations
        """
        self.store = store
        self.resolver = CitationResolver(store) if store else None
        self._works_cache: Optional[List[Work]] = None

    def _cached_works(self) -> List[Work]:
        """All works, fetched once and reused across many to_citation() calls."""
        if self._works_cache is None:
            self._works_cache = self.store.list_works(limit=10_000) if self.store else []
        return self._works_cache

    def extract_from_fragment(
        self,
        fragment: Fragment,
        source_version_date: Optional[date] = None,
    ) -> List[ExtractedCitation]:
        """
        Extract TEMPORAL citations from a single fragment.

        Args:
            fragment: Fragment to extract from
            source_version_date: Version date of the source document

        Returns:
            List of ExtractedCitation objects with temporal info
        """
        if not self.resolver:
            logger.warning("No resolver available - cannot extract citations")
            return []

        citations = []

        try:
            # Resolve references in fragment text
            resolved_refs = self.resolver.resolve_text(fragment.text)

            for ref in resolved_refs:
                if ref.status.value == "resolved":
                    # Resolve target to specific version
                    target_uri, target_version = self._resolve_to_version(
                        ref.uri, source_version_date
                    )

                    citation = ExtractedCitation(
                        source_fragment_uri=fragment.uri,
                        target_uri=target_uri,
                        raw_text=ref.raw_text,
                        confidence=ref.confidence,
                        position=ref.char_start,
                        citation_type=self._determine_citation_type(fragment, ref),

                        # TEMPORAL INFORMATION
                        source_version_date=source_version_date,
                        target_version_date=target_version,
                        valid_from=source_version_date,  # Citation valid from source version
                        valid_to=None,  # Valid until amended (detect in future versions)
                    )
                    citations.append(citation)

            logger.debug(f"Extracted {len(citations)} temporal citations from {fragment.uri}")

        except Exception as e:
            logger.error(f"Citation extraction failed for {fragment.uri}: {e}")

        return citations

    def _resolve_to_version(
        self,
        work_uri: str,
        as_of_date: Optional[date],
    ) -> Tuple[str, Optional[date]]:
        """
        Resolve a work URI to a specific version (Expression URI).

        Returns:
            (expression_uri, version_date) tuple
        """
        if not self.store or not as_of_date:
            return work_uri, None

        try:
            work = self.store.get_work_by_uri(work_uri)
            if not work:
                return work_uri, None
            expr = self.store.get_expression_at_date(work.id, as_of_date)
            if expr:
                return expr.uri, expr.version_date
            return work_uri, as_of_date
        except Exception as e:
            logger.warning("Version resolution failed for %s: %s", work_uri, e)
            return work_uri, None

    def to_citation(self, ec: "ExtractedCitation") -> Optional[Citation]:
        """
        Convert an ExtractedCitation to a Citation store model.

        Resolves fragment/work IDs from URIs via the store.
        Returns None if the source fragment cannot be found.
        """
        if not self.store:
            return None

        # Resolve source fragment
        src_frag = self.store.get_fragment_by_uri(ec.source_fragment_uri)
        if not src_frag:
            logger.debug("Source fragment not found in store: %s", ec.source_fragment_uri)
            return None

        # Resolve target (fragment → expression → work, in that order)
        target_work_id: Optional[str] = None
        target_fragment_id: Optional[str] = None
        if ec.target_uri:
            tgt_frag = self.store.get_fragment_by_uri(ec.target_uri)
            if tgt_frag:
                target_fragment_id = tgt_frag.id
                target_work_id = tgt_frag.work_id
            else:
                tgt_expr = self.store.get_expression_by_uri(ec.target_uri)
                if tgt_expr:
                    target_work_id = tgt_expr.work_id
                else:
                    tgt_work = self.store.get_work_by_uri(ec.target_uri)
                    if tgt_work:
                        target_work_id = tgt_work.id

            # The resolver's abbreviation registry produces idealized
            # canonical slugs (e.g. "grondwet-1987") that routinely don't
            # match the filename-derived work IDs real scraped/OCR'd
            # documents get. Fall back to fuzzy title matching — the same
            # approach amendment base-law resolution already relies on —
            # rather than silently dropping a citation whose law we
            # actually have, just under a different ID. Restricted to law-
            # scheme targets: gazette/ECLI references aren't titled Works,
            # so fuzzy-matching them against work titles would be noise.
            if not target_work_id and "/law/" in ec.target_uri:
                law_name = ec.raw_text
                fallback = resolve_work_by_title(law_name, self._cached_works())
                if fallback:
                    target_work_id = fallback.id

        # Map string citation_type to enum
        try:
            ctype = CitationType(ec.citation_type)
        except ValueError:
            ctype = CitationType.UNKNOWN

        # Stable ID derived from the citation's identity
        raw_id = f"{ec.source_fragment_uri}|{ec.target_uri or ''}|{ec.citation_type}"
        cit_id = "c-" + hashlib.sha1(raw_id.encode()).hexdigest()[:20]

        return Citation(
            id=cit_id,
            citation_type=ctype,
            source_work_id=src_frag.work_id,
            source_fragment_id=src_frag.id,
            source_version_date=ec.source_version_date,
            target_work_id=target_work_id,
            target_fragment_id=target_fragment_id,
            target_version_date=ec.target_version_date,
            raw_text=ec.raw_text,
            confidence=ec.confidence,
            valid_from=ec.valid_from,
            valid_to=ec.valid_to,
        )

    def save_to_store(self, citations: "List[ExtractedCitation]") -> int:
        """
        Persist a list of ExtractedCitations as Citation records in the store.

        Returns the number of citations saved.
        """
        if not self.store:
            logger.warning("No store configured — citations not persisted")
            return 0
        saved = 0
        for ec in citations:
            cit = self.to_citation(ec)
            if cit:
                try:
                    self.store.save_citation(cit)
                    saved += 1
                except Exception as e:
                    logger.warning("Failed to save citation %s: %s", cit.id, e)
        logger.info("Saved %d/%d citations to store", saved, len(citations))
        return saved

    def extract_from_fragments(
        self,
        fragments: List[Fragment],
        source_version_date: Optional[date] = None,
    ) -> List[ExtractedCitation]:
        """
        Extract citations from multiple fragments.

        Args:
            fragments: List of fragments
            source_version_date: Version date shared by all fragments (Expression date)

        Returns:
            List of all extracted citations
        """
        all_citations = []

        for fragment in fragments:
            citations = self.extract_from_fragment(fragment, source_version_date)
            all_citations.extend(citations)

        logger.info(
            "Extracted %d total citations from %d fragments",
            len(all_citations), len(fragments),
        )
        return all_citations

    def _determine_citation_type(
        self,
        source_fragment: Fragment,
        resolved_ref: ResolvedReference,
    ) -> str:
        """Determine the type of citation based on source and target."""
        # Case-law fragments use /id/caselaw/... (this codebase's actual
        # scheme, see ingestion/caselaw_pipeline.py); /ecli/ never appears
        # here even though it's a recognized URIScheme, since no ECLI-based
        # case-law source has been wired up.
        is_case_target = "/ecli/" in resolved_ref.uri or "/caselaw/" in resolved_ref.uri
        is_case_source = "/ecli/" in source_fragment.uri or "/caselaw/" in source_fragment.uri

        if is_case_target and not is_case_source:
            return "law_to_case"
        elif "/law/" in source_fragment.uri and "/law/" in resolved_ref.uri:
            return "law_to_law"
        elif is_case_source and "/law/" in resolved_ref.uri:
            return "case_to_law"
        elif is_case_source and is_case_target:
            return "case_to_case"
        else:
            return "unknown"

    def create_citation_graph(
        self,
        citations: List[ExtractedCitation],
    ) -> Dict[str, List[str]]:
        """
        Create a citation graph from extracted citations.

        Args:
            citations: List of citations

        Returns:
            Dict mapping source URIs to lists of target URIs
        """
        graph = {}

        for citation in citations:
            if citation.source_fragment_uri not in graph:
                graph[citation.source_fragment_uri] = []

            if citation.target_uri:
                graph[citation.source_fragment_uri].append(citation.target_uri)

        return graph

    def find_cited_by(
        self,
        target_uri: str,
        citations: List[ExtractedCitation],
    ) -> List[str]:
        """
        Find all fragments that cite a target URI.

        Args:
            target_uri: URI to find citations to
            citations: List of all citations

        Returns:
            List of source URIs that cite the target
        """
        citing = []

        for citation in citations:
            if citation.target_uri == target_uri:
                citing.append(citation.source_fragment_uri)

        return citing


def extract_and_link_citations(
    fragments: List[Fragment],
    store=None,
) -> List[ExtractedCitation]:
    """
    Convenience function to extract citations from fragments.

    Args:
        fragments: Fragments to process
        store: Optional store for resolution

    Returns:
        List of extracted citations
    """
    extractor = CitationExtractor(store)
    return extractor.extract_from_fragments(fragments)
