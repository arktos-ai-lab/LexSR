"""
Annotation system for legal commentary and knowledge base articles.

Supports:
- Expert commentary on legislation and case law
- Academic articles
- Practitioner notes
- Versioned annotations (track changes over time)
- Multi-author contributions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class AnnotationType(Enum):
    """Types of annotations."""
    COMMENTARY = "commentary"           # Expert legal commentary
    CASE_NOTE = "case_note"            # Analysis of court decision
    ARTICLE = "article"                 # Scholarly article
    PRACTITIONER_NOTE = "practitioner"  # Practical guidance
    EDITORIAL_NOTE = "editorial"        # Editorial explanation
    HISTORICAL_NOTE = "historical"      # Historical context
    AMENDMENT_NOTE = "amendment"        # Explanation of amendment
    CROSS_REFERENCE = "cross_ref"      # Link to related provisions


class AnnotationStatus(Enum):
    """Publication status of an annotation."""
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    PUBLISHED = "published"
    ARCHIVED = "archived"


@dataclass
class Author:
    """Author of an annotation or article."""
    id: str
    name: str
    affiliation: Optional[str] = None
    credentials: Optional[str] = None
    email: Optional[str] = None
    orcid: Optional[str] = None
    bio: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Annotation:
    """
    An annotation attached to a legal fragment.

    Annotations can be:
    - Commentary on specific articles
    - Case notes on court decisions
    - Cross-references to related provisions
    - Historical context
    - Practical guidance
    """
    id: str
    annotation_type: AnnotationType
    status: AnnotationStatus = AnnotationStatus.DRAFT

    # Target (what is being annotated)
    target_uri: str = ""
    target_type: str = ""  # fragment, work, expression, decision

    # Content
    title: str = ""
    summary: str = ""
    content: str = ""
    content_format: str = "markdown"  # markdown, html, plain

    # Authorship
    authors: List[str] = field(default_factory=list)
    primary_author: Optional[str] = None

    # Publication
    published_date: Optional[datetime] = None
    updated_date: Optional[datetime] = None
    version: int = 1

    # Classification
    tags: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)

    # Related content
    related_provisions: List[str] = field(default_factory=list)
    related_cases: List[str] = field(default_factory=list)
    related_annotations: List[str] = field(default_factory=list)
    citations: List[str] = field(default_factory=list)

    # Metadata
    language: str = "nl"
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Article:
    """
    A knowledge base article (long-form content).

    Articles are longer than annotations and can cover:
    - Thematic analysis of legislation
    - Comparative legal studies
    - Practical guides (e.g., "How to start a business in Suriname")
    - Scholarly research
    """
    id: str
    title: str
    slug: str

    # Content
    summary: str = ""
    content: str = ""
    content_format: str = "markdown"

    # Authorship
    authors: List[str] = field(default_factory=list)
    contributors: List[str] = field(default_factory=list)

    # Publication
    status: AnnotationStatus = AnnotationStatus.DRAFT
    published_date: Optional[datetime] = None
    updated_date: Optional[datetime] = None
    version: int = 1

    # Classification
    category: str = ""
    tags: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)

    # Related content
    related_provisions: List[str] = field(default_factory=list)
    related_cases: List[str] = field(default_factory=list)
    related_articles: List[str] = field(default_factory=list)
    citations: List[str] = field(default_factory=list)

    # SEO
    meta_description: str = ""
    meta_keywords: List[str] = field(default_factory=list)

    # Metadata
    language: str = "nl"
    reading_time_minutes: Optional[int] = None
    view_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnnotationVersion:
    """
    A historical version of an annotation.

    Tracks changes to annotations over time.
    """
    id: str
    annotation_id: str
    version: int
    content: str
    author: str
    change_summary: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CommentThread:
    """
    Discussion thread attached to an annotation or article.

    Allows community discussion and peer review.
    """
    id: str
    target_id: str
    target_type: str  # annotation, article
    title: str = ""
    comments: List[Comment] = field(default_factory=list)
    is_resolved: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Comment:
    """A single comment in a discussion thread."""
    id: str
    author: str
    content: str
    parent_comment_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    upvotes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
