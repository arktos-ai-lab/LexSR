"""
API request/response schemas.

Plain dataclasses for zero-dependency operation.
When Pydantic is available, these can be used as BaseModel bases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class WorkResponse:
    """API response for a Work."""
    id: str
    uri: str
    source_type: str
    official_id: str
    title: str
    short_title: Optional[str] = None
    document_type: str = ""
    status: str = "unknown"
    date_enacted: Optional[str] = None
    date_first_in_force: Optional[str] = None

    @classmethod
    def from_work(cls, work) -> WorkResponse:
        return cls(
            id=work.id,
            uri=work.uri,
            source_type=work.source_type.value,
            official_id=work.official_id,
            title=work.title,
            short_title=work.short_title,
            document_type=work.document_type,
            status=work.status.value if work.status else "unknown",
            date_enacted=work.date_enacted.isoformat() if work.date_enacted else None,
            date_first_in_force=work.date_first_in_force.isoformat() if work.date_first_in_force else None,
        )


@dataclass
class ExpressionResponse:
    """API response for an Expression."""
    id: str
    uri: str
    work_id: str
    version_date: str
    title: Optional[str] = None
    status: str = "unknown"
    in_force_start: Optional[str] = None
    in_force_end: Optional[str] = None

    @classmethod
    def from_expression(cls, expr) -> ExpressionResponse:
        return cls(
            id=expr.id,
            uri=expr.uri,
            work_id=expr.work_id,
            version_date=expr.version_date.isoformat(),
            title=expr.title,
            status=expr.status.value if expr.status else "unknown",
            in_force_start=expr.in_force.start.isoformat() if expr.in_force and expr.in_force.start else None,
            in_force_end=expr.in_force.end.isoformat() if expr.in_force and expr.in_force.end else None,
        )


@dataclass
class FragmentResponse:
    """API response for a Fragment."""
    id: str
    uri: str
    expression_id: str
    fragment_type: str
    number: str = ""
    title: Optional[str] = None
    text: str = ""
    heading_path: List[str] = field(default_factory=list)

    @classmethod
    def from_fragment(cls, frag) -> FragmentResponse:
        return cls(
            id=frag.id,
            uri=frag.uri,
            expression_id=frag.expression_id,
            fragment_type=frag.fragment_type.value,
            number=frag.number,
            title=frag.title,
            text=frag.text,
            heading_path=frag.heading_path,
        )


@dataclass
class ResolveRequest:
    """Request to resolve citations in text."""
    text: str
    version_date: Optional[str] = None
    source_document_id: Optional[str] = None


@dataclass
class ResolveResponse:
    """Response from citation resolution."""
    references: List[Dict[str, Any]] = field(default_factory=list)
    total: int = 0
    resolved: int = 0
    partial: int = 0
    unresolved: int = 0


@dataclass
class SearchRequest:
    """Request to search fragments."""
    query: str
    limit: int = 50
    fragment_type: Optional[str] = None


@dataclass
class SearchResponse:
    """Response from fragment search."""
    results: List[FragmentResponse] = field(default_factory=list)
    total: int = 0
    query: str = ""


@dataclass
class HealthResponse:
    """Health check response."""
    status: str = "ok"
    version: str = ""
    store_stats: Dict[str, Any] = field(default_factory=dict)
