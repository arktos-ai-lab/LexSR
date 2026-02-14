"""
API route handlers.

Implements the REST endpoints using the core modules.
Works with or without FastAPI — when FastAPI is not available,
provides a simple JSON-over-HTTP handler using stdlib.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import date
from http.server import BaseHTTPRequestHandler
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from ..core.resolver import CitationResolver, ResolutionStatus
from ..core.store import CanonicalStore
from .schemas import (
    ExpressionResponse,
    FragmentResponse,
    HealthResponse,
    ResolveResponse,
    SearchResponse,
    WorkResponse,
)

logger = logging.getLogger(__name__)


def register_routes(app: Any, store: CanonicalStore, resolver: CitationResolver) -> None:
    """
    Register REST API routes on a FastAPI app.

    If FastAPI is not available, use LegalRequestHandler instead.
    """
    try:
        from fastapi import FastAPI, HTTPException, Query
        from fastapi.responses import JSONResponse
    except ImportError:
        logger.warning("FastAPI not available, routes not registered")
        return

    @app.get("/health")
    def health():
        stats = store.stats()
        return asdict(HealthResponse(
            status="ok",
            version="0.4.0",
            store_stats=stats,
        ))

    @app.get("/works/{work_id}")
    def get_work(work_id: str):
        work = store.get_work(work_id)
        if not work:
            raise HTTPException(404, f"Work not found: {work_id}")
        return asdict(WorkResponse.from_work(work))

    @app.get("/works")
    def list_works(source_type: Optional[str] = None, limit: int = 100):
        from ..core.models import SourceType
        st = SourceType(source_type) if source_type else None
        works = store.list_works(source_type=st, limit=limit)
        return [asdict(WorkResponse.from_work(w)) for w in works]

    @app.get("/works/by-uri")
    def get_work_by_uri(uri: str):
        work = store.get_work_by_uri(uri)
        if not work:
            raise HTTPException(404, f"Work not found: {uri}")
        return asdict(WorkResponse.from_work(work))

    @app.get("/expressions/{expression_id}")
    def get_expression(expression_id: str):
        expr = store.get_expression(expression_id)
        if not expr:
            raise HTTPException(404, f"Expression not found: {expression_id}")
        return asdict(ExpressionResponse.from_expression(expr))

    @app.get("/expressions/at-date")
    def get_expression_at_date(work_id: str, query_date: str):
        d = date.fromisoformat(query_date)
        expr = store.get_expression_at_date(work_id, d)
        if not expr:
            raise HTTPException(404, f"No expression found for {work_id} at {query_date}")
        return asdict(ExpressionResponse.from_expression(expr))

    @app.get("/fragments/{fragment_id}")
    def get_fragment(fragment_id: str):
        frag = store.get_fragment(fragment_id)
        if not frag:
            raise HTTPException(404, f"Fragment not found: {fragment_id}")
        return asdict(FragmentResponse.from_fragment(frag))

    @app.get("/fragments/by-uri")
    def get_fragment_by_uri(uri: str):
        frag = store.get_fragment_by_uri(uri)
        if not frag:
            raise HTTPException(404, f"Fragment not found: {uri}")
        return asdict(FragmentResponse.from_fragment(frag))

    @app.post("/resolve")
    def resolve_text(body: dict):
        text = body.get("text", "")
        vdate_str = body.get("version_date")
        vdate = date.fromisoformat(vdate_str) if vdate_str else None
        source_doc = body.get("source_document_id")

        results = resolver.resolve_text(text, source_document_id=source_doc, version_date=vdate)

        refs = []
        resolved_count = 0
        partial_count = 0
        unresolved_count = 0
        for r in results:
            refs.append({
                "raw_text": r.raw_text,
                "ref_type": r.ref_type.value,
                "status": r.status.value,
                "uri": r.uri,
                "work_uri": r.work_uri,
                "confidence": r.confidence,
            })
            if r.status == ResolutionStatus.RESOLVED:
                resolved_count += 1
            elif r.status == ResolutionStatus.PARTIAL:
                partial_count += 1
            else:
                unresolved_count += 1

        return asdict(ResolveResponse(
            references=refs,
            total=len(refs),
            resolved=resolved_count,
            partial=partial_count,
            unresolved=unresolved_count,
        ))

    @app.get("/search")
    def search_fragments(query: str, limit: int = 50):
        frags = store.search_fragments_by_text(query, limit=limit)
        return asdict(SearchResponse(
            results=[asdict(FragmentResponse.from_fragment(f)) for f in frags],
            total=len(frags),
            query=query,
        ))


class LegalRequestHandler(BaseHTTPRequestHandler):
    """
    Minimal stdlib HTTP handler for when FastAPI is not available.

    Supports GET /health, GET /works, POST /resolve.
    """

    store: Optional[CanonicalStore] = None
    resolver: Optional[CitationResolver] = None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        if path == "/health":
            stats = self.store.stats() if self.store else {}
            self._json_response(200, {
                "status": "ok",
                "version": "0.4.0",
                "store_stats": stats,
            })

        elif path == "/works" and self.store:
            limit = int(params.get("limit", ["100"])[0])
            works = self.store.list_works(limit=limit)
            self._json_response(200, [
                asdict(WorkResponse.from_work(w)) for w in works
            ])

        elif path.startswith("/search") and self.store:
            query = params.get("query", [""])[0]
            limit = int(params.get("limit", ["50"])[0])
            frags = self.store.search_fragments_by_text(query, limit=limit)
            self._json_response(200, {
                "results": [asdict(FragmentResponse.from_fragment(f)) for f in frags],
                "total": len(frags),
                "query": query,
            })

        else:
            self._json_response(404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/resolve" and self.resolver:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length)) if content_length else {}
            text = body.get("text", "")
            vdate_str = body.get("version_date")
            vdate = date.fromisoformat(vdate_str) if vdate_str else None

            results = self.resolver.resolve_text(text, version_date=vdate)
            refs = [{
                "raw_text": r.raw_text,
                "ref_type": r.ref_type.value,
                "status": r.status.value,
                "uri": r.uri,
                "confidence": r.confidence,
            } for r in results]

            self._json_response(200, {"references": refs, "total": len(refs)})
        else:
            self._json_response(404, {"error": "Not found"})

    def _json_response(self, status: int, data: Any):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        logger.info(format, *args)
