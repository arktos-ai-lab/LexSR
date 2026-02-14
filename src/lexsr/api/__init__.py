"""
REST API serving layer for the Legal Knowledge Fabric.

Provides developer-friendly endpoints for:
  - Document retrieval (Works, Expressions, Fragments)
  - Citation resolution
  - Temporal queries ("what was valid on date X?")
  - Link integrity reports
  - Search (text search across fragments)

Sprint 5: REST mandatory per PLAN.md. Uses FastAPI when available,
falls back to a lightweight stdlib server for zero-dependency usage.
"""

from .app import create_app, LexNLAPI
from .routes import register_routes
from .schemas import (
    WorkResponse,
    ExpressionResponse,
    FragmentResponse,
    ResolveRequest,
    ResolveResponse,
    SearchRequest,
    SearchResponse,
    HealthResponse,
)

__all__ = [
    "create_app",
    "LexNLAPI",
    "register_routes",
    "WorkResponse",
    "ExpressionResponse",
    "FragmentResponse",
    "ResolveRequest",
    "ResolveResponse",
    "SearchRequest",
    "SearchResponse",
    "HealthResponse",
]
