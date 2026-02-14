"""
Jinja2 templates for static site generation.

Templates styled after wetten.overheid.nl with:
- Clean typography
- Clear hierarchy
- Mobile-responsive
- Accessible (WCAG 2.1 AA)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class TemplateEngine:
    """
    Template engine for static site generation.

    Uses Jinja2 for templating with built-in templates
    styled after wetten.overheid.nl.
    """

    def __init__(self, template_dir: Optional[str] = None):
        """
        Initialize template engine.

        Args:
            template_dir: Optional custom template directory
        """
        self.template_dir = Path(template_dir) if template_dir else None

        try:
            from jinja2 import Environment, FileSystemLoader, BaseLoader

            self._env_cls = Environment
            self._file_loader = FileSystemLoader
            self._base_loader = BaseLoader

        except ImportError:
            raise ImportError(
                "Static site generation requires jinja2. "
                "Install with: pip install jinja2"
            )

        # Initialize Jinja2 environment
        if self.template_dir and self.template_dir.exists():
            loader = self._file_loader(str(self.template_dir))
        else:
            # Use built-in templates
            loader = self._DictLoader(self._get_builtin_templates())

        self.env = self._env_cls(loader=loader, autoescape=True)

    class _DictLoader:
        """Simple dict-based template loader for built-in templates."""
        def __init__(self, templates: Dict[str, str]):
            self.templates = templates

        def get_source(self, environment, template):
            if template not in self.templates:
                raise Exception(f"Template not found: {template}")
            source = self.templates[template]
            return source, None, lambda: True

    def _get_builtin_templates(self) -> Dict[str, str]:
        """Return built-in templates as a dictionary."""
        return {
            "base.html": BASE_TEMPLATE,
            "index.html": INDEX_TEMPLATE,
            "search.html": SEARCH_TEMPLATE,
            "expression.html": EXPRESSION_TEMPLATE,
            "fragment.html": FRAGMENT_TEMPLATE,
        }

    def render_index(self, context: Dict[str, Any]) -> str:
        """Render index page."""
        template = self.env.get_template("index.html")
        return template.render(**context)

    def render_search(self, context: Dict[str, Any]) -> str:
        """Render search page."""
        template = self.env.get_template("search.html")
        return template.render(**context)

    def render_expression(self, context: Dict[str, Any]) -> str:
        """Render expression (law version) page."""
        template = self.env.get_template("expression.html")
        return template.render(**context)

    def render_css(self) -> str:
        """Render CSS stylesheet."""
        return CSS_TEMPLATE

    def render_js(self) -> str:
        """Render JavaScript."""
        return JS_TEMPLATE


# ============================================================================
# Built-in Templates (wetten.overheid.nl style)
# ============================================================================

BASE_TEMPLATE = """<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}{{ site_title }}{% endblock %}</title>
    <meta name="description" content="{% block description %}Officiële publicatie van de wetten van Suriname{% endblock %}">
    <link rel="stylesheet" href="{{ base_url }}/assets/css/style.css">
    {% block extra_head %}{% endblock %}
</head>
<body>
    <header class="site-header">
        <div class="container">
            <h1 class="site-title"><a href="{{ base_url }}/">{{ site_title }}</a></h1>
            <nav class="main-nav">
                <a href="{{ base_url }}/">Home</a>
                <a href="{{ base_url }}/search/">Zoeken</a>
                <a href="{{ base_url }}/works/">Wetten</a>
            </nav>
        </div>
    </header>

    <main class="site-main">
        <div class="container">
            {% block content %}{% endblock %}
        </div>
    </main>

    <footer class="site-footer">
        <div class="container">
            <p>© {{ "now"|replace("now", "2026") }} Wetten van Suriname |
               <a href="{{ base_url }}/about/">Over deze site</a> |
               <a href="https://github.com/your-org/wetten-van-suriname">Open Source</a>
            </p>
        </div>
    </footer>

    <script src="{{ base_url }}/assets/js/search.js"></script>
    {% block extra_scripts %}{% endblock %}
</body>
</html>
"""

INDEX_TEMPLATE = """{% extends "base.html" %}

{% block content %}
<div class="home-hero">
    <h2>Wetten van de Republiek Suriname</h2>
    <p class="lead">
        Doorzoek de wetgeving van Suriname met geavanceerde zoekfunctionaliteit.
        Inclusief actuele consolidaties, wijzigingsgeschiedenis en tijdreizen.
    </p>

    <div class="search-box">
        <form action="{{ base_url }}/search/" method="get">
            <input type="search" name="q" placeholder="Zoek in wetgeving..." class="search-input">
            <button type="submit" class="search-button">Zoeken</button>
        </form>
    </div>
</div>

<div class="home-sections">
    <section class="home-section">
        <h3>Recente wijzigingen</h3>
        <ul class="recent-changes">
            <li><a href="#">Arbeidswet 1963</a> - gewijzigd 15 januari 2024</li>
            <li><a href="#">Wetboek van Strafrecht</a> - gewijzigd 10 december 2023</li>
        </ul>
    </section>

    <section class="home-section">
        <h3>Veelgebruikte wetten</h3>
        <ul class="popular-laws">
            <li><a href="#">Grondwet 1987</a></li>
            <li><a href="#">Burgerlijk Wetboek</a></li>
            <li><a href="#">Arbeidswet 1963</a></li>
        </ul>
    </section>

    <section class="home-section">
        <h3>Over deze database</h3>
        <p>
            Deze database bevat de wetgeving van Suriname in gestructureerde,
            doorzoekbare vorm. Alle teksten zijn voorzien van bronvermelding
            en wijzigingsgeschiedenis.
        </p>
    </section>
</div>
{% endblock %}
"""

SEARCH_TEMPLATE = """{% extends "base.html" %}

{% block title %}Zoeken - {{ site_title }}{% endblock %}

{% block content %}
<div class="search-page">
    <h2>Zoeken in wetgeving</h2>

    <div class="search-box-large">
        <form action="{{ base_url }}/search/" method="get" id="search-form">
            <input type="search" name="q" id="search-query" placeholder="Zoek in wetgeving..."
                   class="search-input-large" autofocus>
            <button type="submit" class="search-button-large">Zoeken</button>

            <div class="search-filters">
                <label>
                    <input type="checkbox" name="temporal" id="temporal-filter">
                    Tijdreis - bekijk wetgeving zoals deze gold op een specifieke datum
                </label>
                <input type="date" name="as_of_date" id="as-of-date" class="date-input" style="display:none;">
            </div>
        </form>
    </div>

    <div id="search-results" class="search-results">
        <!-- Results will be inserted here by JavaScript -->
    </div>
</div>
{% endblock %}

{% block extra_scripts %}
<script>
// Toggle temporal search
document.getElementById('temporal-filter').addEventListener('change', function(e) {
    document.getElementById('as-of-date').style.display = e.target.checked ? 'inline-block' : 'none';
});
</script>
{% endblock %}
"""

EXPRESSION_TEMPLATE = """{% extends "base.html" %}

{% block title %}{{ work.title }} - {{ site_title }}{% endblock %}

{% block content %}
<article class="law-document">
    <header class="law-header">
        <div class="law-breadcrumb">
            <a href="{{ base_url }}/">Home</a> ›
            <a href="{{ base_url }}/works/">Wetten</a> ›
            {{ work.short_title or work.title }}
        </div>

        <h1 class="law-title">{{ work.title }}</h1>

        <div class="law-meta">
            {% if is_latest %}
                <span class="badge badge-current">Actuele versie</span>
            {% else %}
                <span class="badge badge-historical">Historische versie</span>
            {% endif %}

            <dl class="law-metadata">
                <dt>Geldig op:</dt>
                <dd>{{ expression.version_date.strftime('%d %B %Y') }}</dd>

                {% if expression.in_force.start %}
                <dt>In werking:</dt>
                <dd>{{ expression.in_force.start.strftime('%d %B %Y') }}</dd>
                {% endif %}

                <dt>Status:</dt>
                <dd>{{ expression.status.value }}</dd>
            </dl>
        </div>

        <div class="law-actions">
            <button class="action-button" onclick="window.print()">Afdrukken</button>
            <button class="action-button">Download PDF</button>
            <button class="action-button" id="version-switcher">Andere versies</button>
        </div>
    </header>

    <div class="law-content">
        {% for article in fragments.articles %}
        <section class="article" id="article-{{ article.number }}">
            <div class="article-header">
                <h2 class="article-number">Artikel {{ article.number }}</h2>
                {% if article.title %}
                <h3 class="article-title">{{ article.title }}</h3>
                {% endif %}
            </div>

            <div class="article-text">
                {{ article.text }}
            </div>

            {% if article.metadata.get('amended') %}
            <div class="article-meta">
                <span class="amendment-note">
                    Laatst gewijzigd: {{ article.metadata.amended_date }}
                </span>
            </div>
            {% endif %}
        </section>
        {% endfor %}
    </div>

    <aside class="law-sidebar">
        <div class="sidebar-section">
            <h3>Navigatie</h3>
            <nav class="law-toc">
                <ul>
                    {% for article in fragments.articles %}
                    <li><a href="#article-{{ article.number }}">Art. {{ article.number }} {% if article.title %}- {{ article.title }}{% endif %}</a></li>
                    {% endfor %}
                </ul>
            </nav>
        </div>

        <div class="sidebar-section">
            <h3>Wijzigingsgeschiedenis</h3>
            <div class="timeline">
                <!-- Timeline would be generated here -->
                <p><em>Geen wijzigingen beschikbaar</em></p>
            </div>
        </div>
    </aside>
</article>
{% endblock %}
"""

FRAGMENT_TEMPLATE = """
<!-- Fragment template for embedded use -->
<div class="fragment fragment-{{ fragment.fragment_type.value }}">
    <div class="fragment-header">
        <span class="fragment-number">{{ fragment.number }}</span>
        {% if fragment.title %}
        <span class="fragment-title">{{ fragment.title }}</span>
        {% endif %}
    </div>
    <div class="fragment-text">
        {{ fragment.text }}
    </div>
</div>
"""

CSS_TEMPLATE = """
/* Wetten van Suriname - Stylesheet */
/* Inspired by wetten.overheid.nl */

:root {
    --primary-color: #154273;
    --secondary-color: #0077BB;
    --text-color: #333;
    --bg-color: #fff;
    --border-color: #ddd;
    --highlight-color: #FFF3CD;
    --success-color: #28a745;
    --warning-color: #ffc107;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    line-height: 1.6;
    color: var(--text-color);
    background-color: var(--bg-color);
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 20px;
}

/* Header */
.site-header {
    background-color: var(--primary-color);
    color: white;
    padding: 1rem 0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.site-title a {
    color: white;
    text-decoration: none;
    font-size: 1.5rem;
}

.main-nav {
    margin-top: 0.5rem;
}

.main-nav a {
    color: white;
    text-decoration: none;
    margin-right: 1.5rem;
    padding: 0.5rem 0;
    border-bottom: 2px solid transparent;
    transition: border-color 0.3s;
}

.main-nav a:hover {
    border-bottom-color: white;
}

/* Main content */
.site-main {
    padding: 2rem 0;
    min-height: 70vh;
}

/* Home page */
.home-hero {
    text-align: center;
    padding: 3rem 0;
    border-bottom: 1px solid var(--border-color);
}

.home-hero h2 {
    font-size: 2.5rem;
    margin-bottom: 1rem;
    color: var(--primary-color);
}

.lead {
    font-size: 1.2rem;
    color: #666;
    max-width: 800px;
    margin: 0 auto 2rem;
}

.search-box {
    max-width: 600px;
    margin: 0 auto;
}

.search-input {
    width: 70%;
    padding: 1rem;
    font-size: 1rem;
    border: 2px solid var(--border-color);
    border-radius: 4px 0 0 4px;
}

.search-button {
    width: 30%;
    padding: 1rem;
    font-size: 1rem;
    background-color: var(--secondary-color);
    color: white;
    border: none;
    border-radius: 0 4px 4px 0;
    cursor: pointer;
    transition: background-color 0.3s;
}

.search-button:hover {
    background-color: #005fa3;
}

/* Law document */
.law-document {
    display: grid;
    grid-template-columns: 1fr 300px;
    gap: 2rem;
}

.law-header {
    grid-column: 1 / -1;
    border-bottom: 2px solid var(--primary-color);
    padding-bottom: 1rem;
    margin-bottom: 2rem;
}

.law-breadcrumb {
    font-size: 0.9rem;
    color: #666;
    margin-bottom: 0.5rem;
}

.law-title {
    font-size: 2rem;
    color: var(--primary-color);
    margin-bottom: 1rem;
}

.badge {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    border-radius: 4px;
    font-size: 0.875rem;
    font-weight: 600;
}

.badge-current {
    background-color: var(--success-color);
    color: white;
}

.badge-historical {
    background-color: var(--warning-color);
    color: #333;
}

.law-metadata {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.5rem 1rem;
    margin-top: 1rem;
    font-size: 0.9rem;
}

.law-metadata dt {
    font-weight: 600;
}

.article {
    margin-bottom: 3rem;
    padding: 1.5rem;
    background-color: #fafafa;
    border-left: 4px solid var(--secondary-color);
}

.article-number {
    font-size: 1.3rem;
    color: var(--primary-color);
    margin-bottom: 0.5rem;
}

.article-title {
    font-size: 1.1rem;
    color: #555;
    margin-bottom: 1rem;
    font-weight: normal;
    font-style: italic;
}

.article-text {
    line-height: 1.8;
}

.law-sidebar {
    background-color: #f8f9fa;
    padding: 1.5rem;
    border-radius: 8px;
}

.sidebar-section {
    margin-bottom: 2rem;
}

.sidebar-section h3 {
    font-size: 1.1rem;
    color: var(--primary-color);
    margin-bottom: 1rem;
}

.law-toc ul {
    list-style: none;
}

.law-toc a {
    display: block;
    padding: 0.5rem 0;
    color: var(--text-color);
    text-decoration: none;
    border-bottom: 1px solid #ddd;
}

.law-toc a:hover {
    background-color: #e9ecef;
    padding-left: 0.5rem;
}

/* Footer */
.site-footer {
    background-color: #f8f9fa;
    padding: 2rem 0;
    margin-top: 4rem;
    border-top: 1px solid var(--border-color);
    text-align: center;
    font-size: 0.9rem;
}

.site-footer a {
    color: var(--secondary-color);
    text-decoration: none;
}

/* Responsive */
@media (max-width: 768px) {
    .law-document {
        grid-template-columns: 1fr;
    }

    .law-sidebar {
        order: -1;
    }

    .search-input {
        width: 60%;
    }

    .search-button {
        width: 40%;
    }
}

/* Print styles */
@media print {
    .site-header,
    .main-nav,
    .law-actions,
    .law-sidebar,
    .site-footer {
        display: none;
    }

    .article {
        page-break-inside: avoid;
        border: none;
        background: white;
    }
}
"""

JS_TEMPLATE = """
// Wetten van Suriname - JavaScript

(function() {
    'use strict';

    // Search functionality (client-side)
    function initSearch() {
        const searchForm = document.getElementById('search-form');
        if (!searchForm) return;

        searchForm.addEventListener('submit', async function(e) {
            e.preventDefault();

            const query = document.getElementById('search-query').value;
            const asOfDate = document.getElementById('as-of-date').value;

            // In production, this would call the API
            // For static site, we'd use a pre-built search index

            const resultsDiv = document.getElementById('search-results');
            resultsDiv.innerHTML = '<p>Zoeken...</p>';

            // Placeholder: in production, this would fetch from API or search index
            setTimeout(() => {
                resultsDiv.innerHTML = `
                    <div class="search-result">
                        <h3><a href="#">Resultaat voor "${query}"</a></h3>
                        <p>Zoekfunctionaliteit wordt geladen...</p>
                    </div>
                `;
            }, 500);
        });
    }

    // Version switcher
    function initVersionSwitcher() {
        const versionButton = document.getElementById('version-switcher');
        if (!versionButton) return;

        versionButton.addEventListener('click', function() {
            alert('Versieswitcher: andere versies van deze wet bekijken');
            // In production, this would show a modal with all versions
        });
    }

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            initSearch();
            initVersionSwitcher();
        });
    } else {
        initSearch();
        initVersionSwitcher();
    }
})();
"""
