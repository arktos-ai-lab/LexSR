"""
Static site generator for Suriname legal documents.

Generates a complete static website with:
- Index pages (by jurisdiction, topic, date)
- Document pages (legislation, case law)
- Fragment pages (articles, paragraphs)
- Search interface (client-side)
- Amendment timeline views
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.models import Work, Expression, Fragment
from ..core.store import CanonicalStore
from ..core.versioning import TemporalIndex
from .templates import TemplateEngine

logger = logging.getLogger(__name__)


class StaticSiteGenerator:
    """
    Generate a static website from the canonical store.

    Output structure:
        site/
            index.html
            search/index.html
            works/
                arbeidswet-1963/
                    index.html
                    2024-01-15/
                        index.html
                        article/4/paragraph/2.html
            assets/
                css/style.css
                js/search.js
            data/
                search-index.json
    """

    def __init__(
        self,
        store: CanonicalStore,
        output_dir: str = "site",
        template_dir: Optional[str] = None,
        base_url: str = "https://wetten.suriname.legal",
    ):
        """
        Initialize static site generator.

        Args:
            store: Canonical store to read from
            output_dir: Directory to write generated site
            template_dir: Custom template directory (optional)
            base_url: Base URL for the site
        """
        self.store = store
        self.output_dir = Path(output_dir)
        self.base_url = base_url.rstrip("/")

        # Initialize template engine
        self.templates = TemplateEngine(template_dir)

        logger.info(f"Static site generator initialized. Output: {output_dir}")

    def generate(
        self,
        works: Optional[List[str]] = None,
        clean: bool = True,
    ) -> None:
        """
        Generate the complete static site.

        Args:
            works: Optional list of work IDs to generate (None = all)
            clean: Whether to clean output directory first
        """
        logger.info("Starting static site generation...")

        # Clean output directory
        if clean and self.output_dir.exists():
            logger.info(f"Cleaning output directory: {self.output_dir}")
            shutil.rmtree(self.output_dir)

        # Create directory structure
        self._create_directories()

        # Copy static assets
        self._copy_assets()

        # Get works to generate
        if works is None:
            # Get all works from store
            works = self._get_all_work_ids()

        logger.info(f"Generating {len(works)} works...")

        # Generate pages
        self._generate_index()
        self._generate_search()
        self._generate_works_index(works)

        for work_id in works:
            self._generate_work(work_id)

        # Generate search index data
        self._generate_search_data()

        logger.info(f"Site generation complete. Output: {self.output_dir}")

    def _create_directories(self):
        """Create output directory structure."""
        dirs = [
            self.output_dir,
            self.output_dir / "works",
            self.output_dir / "search",
            self.output_dir / "assets" / "css",
            self.output_dir / "assets" / "js",
            self.output_dir / "data",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def _copy_assets(self):
        """Copy static assets (CSS, JS, images)."""
        # For now, generate inline CSS and JS
        # In production, these would be separate files

        # Generate CSS
        css = self.templates.render_css()
        css_path = self.output_dir / "assets" / "css" / "style.css"
        css_path.write_text(css, encoding="utf-8")

        # Generate JS
        js = self.templates.render_js()
        js_path = self.output_dir / "assets" / "js" / "search.js"
        js_path.write_text(js, encoding="utf-8")

    def _get_all_work_ids(self) -> List[str]:
        """Get all work IDs from the store."""
        works = self.store.list_works(limit=100_000)
        return [w.id for w in works]

    def _generate_index(self):
        """Generate site index page."""
        html = self.templates.render_index({
            "site_title": "Wetten van Suriname",
            "base_url": self.base_url,
        })

        index_path = self.output_dir / "index.html"
        index_path.write_text(html, encoding="utf-8")
        logger.info("Generated index.html")

    def _generate_search(self):
        """Generate search interface."""
        html = self.templates.render_search({
            "site_title": "Wetten van Suriname",
            "base_url": self.base_url,
        })

        search_path = self.output_dir / "search" / "index.html"
        search_path.write_text(html, encoding="utf-8")
        logger.info("Generated search interface")

    def _generate_works_index(self, work_ids: List[str]):
        """Generate works index page listing all laws."""
        works_with_meta = []
        for work_id in work_ids:
            work = self.store.get_work(work_id)
            if work:
                works_with_meta.append({
                    "work": work,
                    "document_type": work.document_type or None,
                })

        # Sort by title
        works_with_meta.sort(key=lambda w: w["work"].title)

        # Group by document type for statistics
        type_counts = {}
        for item in works_with_meta:
            doc_type = item["document_type"] or "unknown"
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1

        html = self.templates.render_works_index({
            "site_title": "Wetten van Suriname",
            "base_url": self.base_url,
            "works": works_with_meta,
            "total_works": len(works_with_meta),
            "type_counts": type_counts,
        })

        works_path = self.output_dir / "works" / "index.html"
        works_path.write_text(html, encoding="utf-8")
        logger.info(f"Generated works index with {len(works_with_meta)} laws")

    def _generate_work(self, work_id: str):
        """Generate pages for a single work."""
        # Get work from store
        work = self.store.get_work(work_id)
        if not work:
            logger.warning(f"Work not found: {work_id}")
            return

        # Get all expressions
        expressions = self.store.get_expressions_for_work(work_id)

        # Generate work index (latest version)
        if expressions:
            latest = expressions[-1]
            self._generate_expression(work, latest, is_latest=True)

            # Generate all other versions
            for expr in expressions[:-1]:
                self._generate_expression(work, expr, is_latest=False)

    def _build_version_history(self, work_id: str) -> List[Dict[str, Any]]:
        """
        Build a version history list for the sidebar timeline.

        Each entry represents one expression (version) of the work.
        For the original expression there is typically no amendment link;
        for subsequent expressions we look up the amendment that caused it.

        Returns a list of dicts sorted chronologically (oldest first):
            {
                "version_date": "YYYY-MM-DD",
                "staatsblad_ref": str,       # empty string when unknown
                "amendment_title": str,      # empty string when unknown
                "amendment_id": str | None,  # work ID for linking
                "is_current": bool,
            }
        """
        expressions = self.store.get_expressions_for_work(work_id)
        if not expressions:
            return []

        # Index amendment links by effective_date for fast lookup.
        # Multiple amendments could share a date, so we keep a list and
        # use the first match.
        links_by_date: Dict[str, List] = {}
        for link in self.store.get_amendment_links_for_base(work_id):
            key = link.effective_date.isoformat() if link.effective_date else ""
            links_by_date.setdefault(key, []).append(link)

        latest_date = expressions[-1].version_date

        versions: List[Dict[str, Any]] = []
        for expr in expressions:
            vdate_str = expr.version_date.isoformat()

            # Try to match an amendment link by effective_date == version_date
            matched_links = links_by_date.get(vdate_str, [])
            if matched_links:
                link = matched_links[0]
                sb_ref = link.staatsblad_ref or ""
                amend_work = self.store.get_work(link.amendment_work_id)
                amend_title = amend_work.title if amend_work else ""
                amend_id = link.amendment_work_id
            else:
                sb_ref = ""
                amend_title = ""
                amend_id = None

            versions.append({
                "version_date": vdate_str,
                "staatsblad_ref": sb_ref,
                "amendment_title": amend_title,
                "amendment_id": amend_id,
                "is_current": expr.version_date == latest_date,
            })

        return versions

    def _generate_expression(
        self,
        work: Work,
        expression: Expression,
        is_latest: bool = True,
    ):
        """Generate pages for a single expression."""
        # Get fragments
        fragments = self.store.get_fragments_for_expression(expression.id)

        # Build fragment hierarchy
        hierarchy = self._build_hierarchy(fragments)

        # Get amendment metadata for this work
        amendment_data = self._get_amendment_metadata(work.id)

        # Build version history for the sidebar timeline
        versions = self._build_version_history(work.id)

        # Prepare context
        context = {
            "site_title": "Wetten van Suriname",
            "base_url": self.base_url,
            "work": work,
            "expression": expression,
            "fragments": hierarchy,
            "is_latest": is_latest,
            "document_type": amendment_data.get("document_type"),
            "amendments_to_this": amendment_data.get("amendments_to_this", []),
            "this_amends": amendment_data.get("this_amends", []),
            "versions": versions,
        }

        # Render template
        html = self.templates.render_expression(context)

        # Write to file
        if is_latest:
            # Latest version at /works/{work_id}/index.html
            path = self.output_dir / "works" / work.id / "index.html"
        else:
            # Versioned at /works/{work_id}/{version_date}/index.html
            version = expression.version_date.isoformat()
            path = self.output_dir / "works" / work.id / version / "index.html"

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")

        logger.info(f"Generated: {path}")

    def _build_hierarchy(self, fragments: List[Fragment]) -> Dict[str, Any]:
        """Build hierarchical structure from flat fragment list."""
        # Get articles and sort them properly
        articles = [f for f in fragments if f.fragment_type.value == "article"]

        # Try to sort by numeric article number, fallback to string sort
        def article_sort_key(article):
            try:
                return (0, int(article.number))
            except (ValueError, AttributeError):
                return (1, article.number or "")

        articles.sort(key=article_sort_key)

        return {
            "articles": articles,
            "paragraphs": [f for f in fragments if f.fragment_type.value == "paragraph"],
        }

    def _get_amendment_metadata(self, work_id: str) -> Dict[str, Any]:
        """Get amendment metadata for a work from the database."""
        result: Dict[str, Any] = {
            "document_type": None,
            "amendments_to_this": [],
            "this_amends": [],
        }

        # document_type lives on the Work object itself
        work = self.store.get_work(work_id)
        if work:
            result["document_type"] = work.document_type or None

        # Which wijzigingswetten target this base law?
        for link in self.store.get_amendment_links_for_base(work_id):
            amend_work = self.store.get_work(link.amendment_work_id)
            result["amendments_to_this"].append({
                "id": link.amendment_work_id,
                "title": amend_work.title if amend_work else link.amendment_work_id,
                "reference": link.base_work_ref,
                "effective_date": link.effective_date.isoformat() if link.effective_date else None,
            })

        # Which base law(s) does this wijzigingswet target?
        for link in self.store.get_amendment_links_for_amendment(work_id):
            base_work = self.store.get_work(link.base_work_id) if link.base_work_id else None
            result["this_amends"].append({
                "id": link.base_work_id,
                "title": base_work.title if base_work else link.base_work_ref,
                "reference": link.base_work_ref,
                "confidence": link.confidence,
            })

        return result

    def _generate_search_data(self):
        """Generate JSON search index for client-side search."""
        documents = []

        works = self.store.list_works(limit=100_000)
        for work in works:
            expressions = self.store.get_expressions_for_work(work.id)
            if not expressions:
                continue
            latest_expr = expressions[-1]
            fragments = self.store.get_fragments_for_expression(latest_expr.id)
            work_url = f"{self.base_url}/works/{work.id}/"
            for frag in fragments:
                if not frag.text or frag.text == "[Vervallen]":
                    continue
                doc: Dict[str, Any] = {
                    "id": frag.id,
                    "work_id": work.id,
                    "work_title": work.title,
                    "article": frag.number,
                    "title": frag.title or f"Artikel {frag.number}",
                    "text": frag.text[:500],   # cap for index size
                    "url": f"{work_url}#{frag.number}",
                }
                documents.append(doc)

        search_index = {
            "documents": documents,
            "generated": date.today().isoformat(),
        }

        data_path = self.output_dir / "data" / "search-index.json"
        data_path.write_text(json.dumps(search_index, ensure_ascii=False), encoding="utf-8")
        logger.info("Generated search index with %d fragment entries", len(documents))
