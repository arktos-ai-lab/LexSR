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
            from jinja2 import Environment, FileSystemLoader, DictLoader

            self._env_cls = Environment
            self._file_loader = FileSystemLoader
            self._dict_loader = DictLoader

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
            loader = self._dict_loader(self._get_builtin_templates())

        self.env = self._env_cls(loader=loader, autoescape=True)

    def _get_builtin_templates(self) -> Dict[str, str]:
        """Return built-in templates as a dictionary."""
        return {
            "base.html": BASE_TEMPLATE,
            "index.html": INDEX_TEMPLATE,
            "search.html": SEARCH_TEMPLATE,
            "expression.html": EXPRESSION_TEMPLATE,
            "fragment.html": FRAGMENT_TEMPLATE,
            "works_index.html": WORKS_INDEX_TEMPLATE,
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
        # Add Dutch status translations
        status_translations = {
            'in_force': 'Geldig',
            'draft': 'Ontwerp',
            'repealed': 'Ingetrokken',
            'unknown': 'Onbekend',
        }
        context['status_nl'] = status_translations.get(
            context.get('expression', {}).status.value if hasattr(context.get('expression', {}), 'status') else 'unknown',
            'Onbekend'
        )

        template = self.env.get_template("expression.html")
        return template.render(**context)

    def render_works_index(self, context: Dict[str, Any]) -> str:
        """Render works index page."""
        template = self.env.get_template("works_index.html")
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
            <p>© 2026 Wetten van Suriname - Juridische Database |
               LexSR Project
            </p>
            <p class="footer-note">
                Deze database bevat {{ total_works if total_works is defined else '550+' }} wetten van Suriname.
                Voor officiële doeleinden, raadpleeg altijd de originele publicaties.
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

            {% if document_type %}
                {% if document_type == 'base_law' %}
                    <span class="badge badge-doc-type badge-base-law">Basiswet</span>
                {% elif document_type == 'amendment' %}
                    <span class="badge badge-doc-type badge-amendment">Wijzigingswet</span>
                {% elif document_type == 'decree' %}
                    <span class="badge badge-doc-type badge-decree">Besluit</span>
                {% elif document_type == 'repeal' %}
                    <span class="badge badge-doc-type badge-repeal">Intrekkingswet</span>
                {% endif %}
            {% endif %}

            <dl class="law-metadata">
                {% if work.date_enacted %}
                <dt>Datum uitvaardiging:</dt>
                <dd>{{ work.date_enacted.strftime('%d %B %Y') }}</dd>
                {% endif %}

                {% if expression.in_force.start %}
                <dt>In werking:</dt>
                <dd>{{ expression.in_force.start.strftime('%d %B %Y') }}</dd>
                {% elif work.date_first_in_force %}
                <dt>In werking:</dt>
                <dd>{{ work.date_first_in_force.strftime('%d %B %Y') }}</dd>
                {% endif %}

                <dt>Status:</dt>
                <dd>{{ status_nl }}</dd>
            </dl>
        </div>

        {% if this_amends %}
        <div class="law-amendments-info">
            <h3 class="amendments-heading">Deze wet wijzigt:</h3>
            <ul class="amendments-list">
                {% for base in this_amends %}
                <li>
                    {% if base.id %}
                        <a href="{{ base_url }}/works/{{ base.id }}/">{{ base.title or 'Onbekende wet' }}</a>
                    {% else %}
                        <span class="unresolved-reference">{{ base.reference }}</span>
                        <span class="badge badge-warning badge-small">Niet gevonden</span>
                    {% endif %}
                </li>
                {% endfor %}
            </ul>
        </div>
        {% endif %}

        {% if amendments_to_this %}
        <div class="law-amendments-info">
            <h3 class="amendments-heading">Wijzigingen van deze wet:</h3>
            <ul class="amendments-list">
                {% for amendment in amendments_to_this %}
                <li>
                    <a href="{{ base_url }}/works/{{ amendment.id }}/">{{ amendment.title }}</a>
                </li>
                {% endfor %}
            </ul>
        </div>
        {% endif %}

        <div class="law-actions">
            <button class="action-button" onclick="window.print()">Afdrukken</button>
            {% if work.source_url %}
            <a href="{{ work.source_url }}" target="_blank" class="action-button">Bekijk Origineel PDF</a>
            {% endif %}
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
                {% if versions and versions|length > 1 %}
                    {% for v in versions %}
                    <div class="version-entry{% if v.is_current %} version-entry--current{% endif %}">
                        <div class="version-dot"></div>
                        <div class="version-body">
                            <span class="version-date">{{ v.version_date }}</span>
                            {% if v.is_current %}
                            <span class="version-badge version-badge--current">Huidig</span>
                            {% endif %}
                            {% if v.staatsblad_ref %}
                            <span class="version-sb">{{ v.staatsblad_ref }}</span>
                            {% endif %}
                            {% if v.amendment_title %}
                                {% if v.amendment_id %}
                                <a class="version-amendment-link" href="{{ base_url }}/works/{{ v.amendment_id }}/">{{ v.amendment_title }}</a>
                                {% else %}
                                <span class="version-amendment-link">{{ v.amendment_title }}</span>
                                {% endif %}
                            {% elif not loop.first %}
                            <span class="version-amendment-link version-amendment-unknown">Wijziging</span>
                            {% else %}
                            <span class="version-amendment-link version-amendment-original">Oorspronkelijke versie</span>
                            {% endif %}
                        </div>
                    </div>
                    {% endfor %}
                {% else %}
                <p><em>Geen wijzigingen beschikbaar</em></p>
                {% endif %}
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

.badge-doc-type {
    margin-left: 0.5rem;
}

.badge-base-law {
    background-color: #0077BB;
    color: white;
}

.badge-amendment {
    background-color: #FF8C00;
    color: white;
}

.badge-decree {
    background-color: #6C757D;
    color: white;
}

.badge-repeal {
    background-color: #DC3545;
    color: white;
}

.badge-warning {
    background-color: #FFC107;
    color: #333;
}

.badge-unknown {
    background-color: #999;
    color: white;
}

.badge-small {
    padding: 0.15rem 0.5rem;
    font-size: 0.75rem;
    margin-left: 0.5rem;
}

.law-amendments-info {
    margin-top: 1.5rem;
    padding: 1rem;
    background-color: #F0F8FF;
    border-left: 4px solid var(--secondary-color);
    border-radius: 4px;
}

.amendments-heading {
    font-size: 1rem;
    color: var(--primary-color);
    margin-bottom: 0.75rem;
    font-weight: 600;
}

.amendments-list {
    list-style: none;
    padding: 0;
    margin: 0;
}

.amendments-list li {
    padding: 0.5rem 0;
    border-bottom: 1px solid #D0E8F2;
}

.amendments-list li:last-child {
    border-bottom: none;
}

.amendments-list a {
    color: var(--secondary-color);
    text-decoration: none;
    font-weight: 500;
}

.amendments-list a:hover {
    text-decoration: underline;
}

.unresolved-reference {
    color: #666;
    font-style: italic;
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

/* Version history timeline (sidebar) */
.timeline {
    position: relative;
    padding-left: 1.25rem;
}

.timeline::before {
    content: '';
    position: absolute;
    left: 0.35rem;
    top: 0.25rem;
    bottom: 0.25rem;
    width: 2px;
    background-color: var(--border-color);
}

.version-entry {
    position: relative;
    padding: 0.5rem 0 0.5rem 0.75rem;
    margin-bottom: 0.25rem;
}

.version-dot {
    position: absolute;
    left: -0.95rem;
    top: 0.75rem;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background-color: var(--border-color);
    border: 2px solid #fff;
    box-shadow: 0 0 0 2px var(--border-color);
}

.version-entry--current .version-dot {
    background-color: var(--success-color);
    box-shadow: 0 0 0 2px var(--success-color);
}

.version-body {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
}

.version-date {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--primary-color);
    font-variant-numeric: tabular-nums;
}

.version-entry--current .version-date {
    color: var(--success-color);
}

.version-badge {
    display: inline-block;
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    width: fit-content;
}

.version-badge--current {
    background-color: var(--success-color);
    color: white;
}

.version-sb {
    font-size: 0.78rem;
    color: #555;
    font-style: italic;
}

.version-amendment-link {
    font-size: 0.8rem;
    color: var(--secondary-color);
    text-decoration: none;
    word-break: break-word;
}

a.version-amendment-link:hover {
    text-decoration: underline;
}

.version-amendment-original {
    color: #888;
    font-style: italic;
}

.version-amendment-unknown {
    color: #888;
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

/* Action buttons */
.action-button {
    display: inline-block;
    padding: 0.5rem 1rem;
    margin-right: 0.5rem;
    background-color: var(--secondary-color);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    text-decoration: none;
    font-size: 0.9rem;
}

.action-button:hover {
    background-color: #005fa3;
}

/* Footer */
.footer-note {
    margin-top: 0.5rem;
    font-size: 0.85rem;
    color: #666;
}

/* Works index */
.works-list {
    margin-top: 2rem;
}

.work-item {
    padding: 1.5rem;
    margin-bottom: 1rem;
    background-color: #f8f9fa;
    border-left: 4px solid var(--secondary-color);
    border-radius: 4px;
}

.work-item h3 {
    margin: 0 0 0.5rem 0;
    font-size: 1.2rem;
}

.work-item h3 a {
    color: var(--primary-color);
    text-decoration: none;
}

.work-item h3 a:hover {
    text-decoration: underline;
}

.work-meta {
    display: flex;
    gap: 1rem;
    font-size: 0.9rem;
    color: #666;
}

.work-meta span {
    display: inline-block;
}

/* Works index statistics */
.works-stats {
    background-color: #f8f9fa;
    padding: 1.5rem;
    margin: 2rem 0;
    border-radius: 8px;
    border-left: 4px solid var(--secondary-color);
}

.works-stats h3 {
    font-size: 1.1rem;
    color: var(--primary-color);
    margin-bottom: 1rem;
}

.stats-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
}

.stats-badges .badge {
    padding: 0.5rem 1rem;
    font-size: 0.9rem;
}

/* Works filter */
.works-filter {
    margin: 2rem 0;
    padding: 1rem;
    background-color: #f8f9fa;
    border-radius: 4px;
}

.works-filter label {
    font-weight: 600;
    margin-right: 1rem;
    color: var(--primary-color);
}

.filter-select {
    padding: 0.5rem 1rem;
    font-size: 1rem;
    border: 2px solid var(--border-color);
    border-radius: 4px;
    background-color: white;
    cursor: pointer;
    min-width: 200px;
}

.filter-select:focus {
    outline: none;
    border-color: var(--secondary-color);
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

WORKS_INDEX_TEMPLATE = """{% extends "base.html" %}

{% block title %}Alle Wetten - {{ site_title }}{% endblock %}

{% block content %}
<div class="works-index">
    <h2>Alle Wetten</h2>
    <p class="lead">
        {{ total_works }} wetten in de database
    </p>

    {% if type_counts %}
    <div class="works-stats">
        <h3>Documenttypen:</h3>
        <div class="stats-badges">
            {% if type_counts.get('base_law') %}
            <span class="badge badge-base-law">Basiswetten: {{ type_counts['base_law'] }}</span>
            {% endif %}
            {% if type_counts.get('amendment') %}
            <span class="badge badge-amendment">Wijzigingen: {{ type_counts['amendment'] }}</span>
            {% endif %}
            {% if type_counts.get('decree') %}
            <span class="badge badge-decree">Besluiten: {{ type_counts['decree'] }}</span>
            {% endif %}
            {% if type_counts.get('repeal') %}
            <span class="badge badge-repeal">Intrekkingen: {{ type_counts['repeal'] }}</span>
            {% endif %}
            {% if type_counts.get('unknown') %}
            <span class="badge badge-unknown">Onbekend: {{ type_counts['unknown'] }}</span>
            {% endif %}
        </div>
    </div>
    {% endif %}

    <div class="works-filter">
        <label for="type-filter">Filter op type:</label>
        <select id="type-filter" class="filter-select">
            <option value="all">Alle documenten</option>
            <option value="base_law">Basiswetten</option>
            <option value="amendment">Wijzigingen</option>
            <option value="decree">Besluiten</option>
            <option value="repeal">Intrekkingen</option>
            <option value="unknown">Onbekend</option>
        </select>
    </div>

    <div class="works-list">
        {% for item in works %}
        <div class="work-item" data-type="{{ item.document_type or 'unknown' }}">
            <h3><a href="{{ base_url }}/works/{{ item.work.id }}/">{{ item.work.title }}</a></h3>
            <div class="work-meta">
                {% if item.work.date_enacted %}
                <span class="work-date">{{ item.work.date_enacted.strftime('%d %B %Y') }}</span>
                {% endif %}

                {% if item.document_type == 'base_law' %}
                    <span class="badge badge-base-law badge-small">Basiswet</span>
                {% elif item.document_type == 'amendment' %}
                    <span class="badge badge-amendment badge-small">Wijziging</span>
                {% elif item.document_type == 'decree' %}
                    <span class="badge badge-decree badge-small">Besluit</span>
                {% elif item.document_type == 'repeal' %}
                    <span class="badge badge-repeal badge-small">Intrekking</span>
                {% else %}
                    <span class="badge badge-unknown badge-small">Onbekend</span>
                {% endif %}
            </div>
        </div>
        {% endfor %}
    </div>
</div>
{% endblock %}

{% block extra_scripts %}
<script>
// Filter works by document type
document.getElementById('type-filter').addEventListener('change', function(e) {
    const filterValue = e.target.value;
    const workItems = document.querySelectorAll('.work-item');

    workItems.forEach(function(item) {
        if (filterValue === 'all') {
            item.style.display = '';
        } else {
            const itemType = item.getAttribute('data-type');
            item.style.display = itemType === filterValue ? '' : 'none';
        }
    });
});
</script>
{% endblock %}
"""
