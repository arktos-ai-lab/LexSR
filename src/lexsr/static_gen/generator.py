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
        # This is a placeholder - implement proper store query
        return []

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

        # Prepare context
        context = {
            "site_title": "Wetten van Suriname",
            "base_url": self.base_url,
            "work": work,
            "expression": expression,
            "fragments": hierarchy,
            "is_latest": is_latest,
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
        # Simplified hierarchical builder
        # In production, this would create a proper tree structure
        return {
            "articles": [f for f in fragments if f.fragment_type.value == "article"],
            "paragraphs": [f for f in fragments if f.fragment_type.value == "paragraph"],
        }

    def _generate_search_data(self):
        """Generate JSON search index for client-side search."""
        # This would build a search index from all fragments
        # For now, just a placeholder

        search_index = {
            "documents": [],
            "generated": date.today().isoformat(),
        }

        data_path = self.output_dir / "data" / "search-index.json"
        data_path.write_text(json.dumps(search_index, indent=2), encoding="utf-8")
        logger.info("Generated search index data")
