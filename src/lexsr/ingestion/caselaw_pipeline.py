"""
Case-law ingestion pipeline: turns a scraped rechtspraak.sr decision into
FRBR-compatible Work/Fragment rows plus citation links, using the existing
core data model and citation resolver (no schema changes — case-specific
fields live in `metadata`, exactly like every other source type).

Decisions are stored as Work rows with source_type=CASE_LAW; considerations
(numbered paragraphs, "2.1", "2.2", ...) as Fragment rows with
fragment_type=CONSIDERATION; citations (case -> legislation, case -> case)
as rows in the existing generic `citations` table.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

from ..core.models import (
    Work, Expression, Fragment, FragmentType, SourceType, DocumentStatus,
    Citation, CitationType, TemporalExtent,
)
from .scrapers.base import ScrapedDocument

logger = logging.getLogger(__name__)

# Considerations are numbered "N.N" (section.paragraph), e.g. "2.1", "4.7".
_CONSIDERATION_RE = re.compile(r"(?:^|\n)(\d{1,2}\.\d{1,2})\s+(.*?)(?=\n\d{1,2}\.\d{1,2}\s|\Z)", re.S)

# Self-citations to other rechtspraak.sr decisions, e.g. "SRU-HvJ-2019-3".
_CASE_CITATION_RE = re.compile(r"\bSRU-[A-Za-z]{1,4}-\d{1,4}(?:-\d{1,4})?\b", re.IGNORECASE)


@dataclass
class CaseLawResult:
    work: Optional[Work] = None
    expression: Optional[Expression] = None
    fragments: List[Fragment] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)
    success: bool = True
    errors: List[str] = field(default_factory=list)


def _slugify(sru_id: str) -> str:
    slug = sru_id.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug


class CaseLawPipeline:
    """
    Converts scraped rechtspraak.sr decisions into stored FRBR objects.

    Citations to legislation are NOT extracted here — after fragments are
    saved, run them through the existing `CitationExtractor` (the same one
    `lexsr link-citations` uses), which already knows how to resolve legal
    references against the canonical store. This pipeline only extracts
    case-to-case citations (SRU-id self-references), which nothing else
    handles.
    """

    def process_document(self, doc: ScrapedDocument) -> CaseLawResult:
        result = CaseLawResult()

        try:
            meta = doc.metadata or {}
            sru_id = meta.get("sru_id") or doc.title
            full_text = meta.get("full_text", "")
            if not full_text.strip():
                result.success = False
                result.errors.append("No decision text extracted")
                return result

            work_id = f"caselaw-{_slugify(sru_id)}"
            decision_date = _parse_iso_date(meta.get("decision_date"))
            publication_date = _parse_iso_date(meta.get("publication_date"))

            work = Work(
                id=work_id,
                uri=f"/id/caselaw/{_slugify(sru_id)}",
                source_type=SourceType.CASE_LAW,
                official_id=sru_id,
                title=meta.get("case_number") or sru_id,
                document_type="rechterlijke uitspraak",
                jurisdiction="SR",
                status=DocumentStatus.IN_FORCE,
                date_enacted=decision_date,
                source_url=doc.url,
                retrieved_at=datetime.combine(doc.scraped_at or date.today(), datetime.min.time()),
                metadata={
                    "sru_id": sru_id,
                    "court": meta.get("court", ""),
                    "case_number": meta.get("case_number", ""),
                    "legal_area": meta.get("legal_area", ""),
                    "abstract": meta.get("abstract", ""),
                    "decision_date": meta.get("decision_date"),
                    "publication_date": meta.get("publication_date"),
                },
            )
            result.work = work

            version_date = decision_date or publication_date or date.today()
            expression = Expression(
                id=work_id,
                uri=work.uri,
                work_id=work_id,
                work_uri=work.uri,
                version_date=version_date,
                in_force=TemporalExtent(start=version_date),
                title=work.title,
                status=DocumentStatus.IN_FORCE,
                source_url=doc.url,
            )
            result.expression = expression

            fragments = self._build_fragments(work_id, work.uri, full_text)

            if not fragments:
                # No numbered considerations detected; keep the whole
                # decision as a single fragment so the text isn't lost.
                fragments = [Fragment(
                    id=f"{work_id}-full",
                    uri=f"{work.uri}/text",
                    expression_id=work_id,
                    expression_uri=work.uri,
                    work_id=work_id,
                    fragment_type=FragmentType.CONSIDERATION,
                    number="1",
                    text=full_text,
                )]

            result.fragments = fragments
            for fragment in fragments:
                result.citations.extend(self._extract_case_citations(work, fragment))

        except Exception as exc:
            logger.error(f"Case-law pipeline failed for {doc.url}: {exc}", exc_info=True)
            result.success = False
            result.errors.append(str(exc))

        return result

    @staticmethod
    def _build_fragments(work_id: str, work_uri: str, full_text: str) -> List[Fragment]:
        fragments = []
        seen: dict = {}
        for match in _CONSIDERATION_RE.finditer(full_text):
            number, text = match.group(1), match.group(2).strip()
            if not text:
                continue
            # A decision can restart its numbering (e.g. a second "2.1" under a
            # later heading); suffix repeats so they don't overwrite each other.
            seen[number] = seen.get(number, 0) + 1
            key = number if seen[number] == 1 else f"{number}-{seen[number]}"
            fragments.append(Fragment(
                id=f"{work_id}-ro{key.replace('.', '-')}",
                uri=f"{work_uri}/consideration/{key}",
                expression_id=work_id,
                expression_uri=work_uri,
                work_id=work_id,
                fragment_type=FragmentType.CONSIDERATION,
                number=number,
                text=text,
            ))
        return fragments

    @staticmethod
    def _extract_case_citations(work: Work, fragment: Fragment) -> List[Citation]:
        """Self-citations to other decisions (SRU-XXX-YYYY-N mentions)."""
        citations: List[Citation] = []

        for m in _CASE_CITATION_RE.finditer(fragment.text):
            raw = m.group(0)
            target_work_id = f"caselaw-{_slugify(raw)}"
            if target_work_id == work.id:
                continue  # a decision citing its own SRU id (header, etc.)
            citations.append(Citation(
                id=_citation_id(fragment.id, target_work_id, "case_to_case"),
                citation_type=CitationType.CASE_TO_CASE,
                source_work_id=work.id,
                source_fragment_id=fragment.id,
                target_work_id=target_work_id,
                raw_text=raw,
                confidence=0.85,
            ))

        return citations


def _parse_iso_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _citation_id(source_fragment_id: str, target: str, citation_type: str) -> str:
    return hashlib.sha1(f"{citation_type}:{source_fragment_id}:{target}".encode()).hexdigest()[:16]
