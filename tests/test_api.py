"""
Tests for the API layer (Sprint 5).

Covers: schemas, LegalAPI, LegalRequestHandler, create_app.
FastAPI route tests are skipped if FastAPI is not installed.

Run with: python -m pytest tests/test_api.py -v
"""

from dataclasses import asdict
from datetime import date

import pytest

from lexsr.api.schemas import (
    ExpressionResponse,
    FragmentResponse,
    HealthResponse,
    ResolveRequest,
    ResolveResponse,
    SearchRequest,
    SearchResponse,
    WorkResponse,
)
from lexsr.api.app import LegalAPI, create_app
from lexsr.core.models import (
    DocumentStatus,
    Expression,
    Fragment,
    FragmentType,
    SourceType,
    TemporalExtent,
    Work,
)
from lexsr.core.store import CanonicalStore
from lexsr.core.resolver import CitationResolver


# ===================================================================
# Schema Tests
# ===================================================================

class TestWorkResponse:
    def test_from_work(self):
        work = Work(
            id="w-test",
            uri="/id/law/burgerlijk-wetboek",
            source_type=SourceType.LEGISLATION,
            official_id="burgerlijk-wetboek",
            title="Burgerlijk Wetboek",
            short_title="BW",
            document_type="wet",
            status=DocumentStatus.IN_FORCE,
        )
        resp = WorkResponse.from_work(work)
        assert resp.id == "w-test"
        assert resp.uri == "/id/law/burgerlijk-wetboek"
        assert resp.source_type == "legislation"
        assert resp.official_id == "burgerlijk-wetboek"
        assert resp.title == "Burgerlijk Wetboek"
        assert resp.short_title == "BW"
        assert resp.status == "in_force"

    def test_asdict(self):
        resp = WorkResponse(
            id="w1", uri="/id/law/arbeidswet-1963", source_type="legislation",
            official_id="arbeidswet-1963", title="Arbeidswet 1963",
        )
        d = asdict(resp)
        assert d["id"] == "w1"
        assert d["uri"] == "/id/law/arbeidswet-1963"


class TestExpressionResponse:
    def test_from_expression(self):
        expr = Expression(
            id="e-test",
            uri="/id/law/burgerlijk-wetboek/2024-01-15",
            work_id="w-test",
            work_uri="/id/law/burgerlijk-wetboek",
            version_date=date(2024, 1, 15),
            in_force=TemporalExtent(start=date(2024, 1, 15)),
            status=DocumentStatus.IN_FORCE,
        )
        resp = ExpressionResponse.from_expression(expr)
        assert resp.id == "e-test"
        assert resp.version_date == "2024-01-15"
        assert resp.in_force_start == "2024-01-15"
        assert resp.in_force_end is None


class TestFragmentResponse:
    def test_from_fragment(self):
        frag = Fragment(
            id="f-test",
            uri="/id/law/burgerlijk-wetboek/2024-01-15/article/1",
            expression_id="e-test",
            expression_uri="/id/law/burgerlijk-wetboek/2024-01-15",
            work_id="w-test",
            fragment_type=FragmentType.ARTICLE,
            number="1",
            title="Article 1",
            text="Text of article 1.",
        )
        resp = FragmentResponse.from_fragment(frag)
        assert resp.id == "f-test"
        assert resp.fragment_type == "article"
        assert resp.number == "1"
        assert resp.text == "Text of article 1."


class TestOtherSchemas:
    def test_resolve_request(self):
        req = ResolveRequest(text="article 1 BW", version_date="2024-01-15")
        assert req.text == "article 1 BW"

    def test_resolve_response(self):
        resp = ResolveResponse(references=[{"ref": "test"}], total=1, resolved=1)
        assert resp.total == 1

    def test_search_request(self):
        req = SearchRequest(query="onrechtmatige daad", limit=10)
        assert req.limit == 10

    def test_search_response(self):
        resp = SearchResponse(results=[], total=0, query="test")
        assert resp.query == "test"

    def test_health_response(self):
        resp = HealthResponse(status="ok", version="0.4.0")
        assert resp.status == "ok"


# ===================================================================
# App Factory
# ===================================================================

class TestCreateApp:
    def test_create_app_returns_something(self, tmp_path):
        db_path = str(tmp_path / "api_test.db")
        app = create_app(db_path=db_path)
        # Should return either FastAPI app or LegalAPI
        assert app is not None

    def test_legal_api_class(self, tmp_path):
        store = CanonicalStore(str(tmp_path / "api_store.db"))
        resolver = CitationResolver(store=store, default_date=date(2024, 1, 15))
        api = LegalAPI(store=store, resolver=resolver)
        assert api.store is store
        assert api.resolver is resolver
        store.close()

    def test_create_app_with_store(self, tmp_path):
        store = CanonicalStore(str(tmp_path / "api_store.db"))
        app = create_app(store=store)
        assert app is not None
        store.close()


# ===================================================================
# Stdlib Handler (integration-ish test)
# ===================================================================

class TestLegalRequestHandler:
    """Test the stdlib request handler can be configured."""

    def test_handler_class_attributes(self):
        from lexsr.api.routes import LegalRequestHandler
        # Verify the class has the expected class-level attributes
        assert hasattr(LegalRequestHandler, 'store')
        assert hasattr(LegalRequestHandler, 'resolver')

    def test_handler_set_store(self, tmp_path):
        from lexsr.api.routes import LegalRequestHandler
        store = CanonicalStore(str(tmp_path / "handler_test.db"))
        LegalRequestHandler.store = store
        assert LegalRequestHandler.store is store
        # Reset
        LegalRequestHandler.store = None
        store.close()
