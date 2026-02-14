"""
Static site generator for legal documents.

Generates wetten.overheid.nl-style HTML pages with:
- Clean, readable article/paragraph layout
- Amendment history timeline
- Version switcher (temporal navigation)
- Mobile-responsive design
- SEO optimization
- Accessibility (WCAG 2.1 AA)
"""

from .generator import StaticSiteGenerator
from .templates import TemplateEngine

__all__ = ["StaticSiteGenerator", "TemplateEngine"]
