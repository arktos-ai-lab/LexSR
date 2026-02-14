"""
Application factory for the LexSR REST API.

Creates and configures the API server with the canonical store and resolver.
"""

from __future__ import annotations

import logging
from http.server import HTTPServer
from typing import Optional

from ..core.resolver import CitationResolver
from ..core.store import CanonicalStore

logger = logging.getLogger(__name__)


class LegalAPI:
    """
    Main API class that wraps the store and resolver.

    Can run with FastAPI (recommended) or stdlib HTTPServer (zero-dependency).
    """

    def __init__(
        self,
        store: CanonicalStore,
        resolver: Optional[CitationResolver] = None,
    ):
        self.store = store
        self.resolver = resolver or CitationResolver(store=store)

    def run_stdlib(self, host: str = "127.0.0.1", port: int = 8000) -> None:
        """Run using stdlib HTTPServer (no dependencies needed)."""
        from .routes import LegalRequestHandler

        LegalRequestHandler.store = self.store
        LegalRequestHandler.resolver = self.resolver

        server = HTTPServer((host, port), LegalRequestHandler)
        logger.info("LexSR API running on http://%s:%d (stdlib)", host, port)
        print(f"LexSR API running on http://{host}:{port}")
        server.serve_forever()


def create_app(
    db_path: str = "data/canonical.db",
    store: Optional[CanonicalStore] = None,
    resolver: Optional[CitationResolver] = None,
):
    """
    Create a FastAPI application.

    Falls back to returning a LegalAPI instance if FastAPI is not available.
    """
    _store = store or CanonicalStore(db_path)
    _resolver = resolver or CitationResolver(store=_store)

    try:
        from fastapi import FastAPI
        from .routes import register_routes

        app = FastAPI(
            title="LexSR - Suriname Legal Knowledge Fabric",
            version="0.4.0",
            description="REST API for Suriname legal documents, citations, and temporal queries",
        )
        register_routes(app, _store, _resolver)
        return app

    except ImportError:
        logger.info("FastAPI not available, using LegalAPI with stdlib server")
        return LegalAPI(store=_store, resolver=_resolver)
