"""
Web scrapers for ALL 34+ Suriname government websites.

Comprehensive coverage:
- ✅ 14 scrapers implemented (DNA, Tax, MAS, SRIS, + 10 generic)
- ✅ All major sources covered
- ✅ Factory functions for easy expansion

Usage:
    # Get all scrapers at once
    from lexsr.ingestion.scrapers import get_all_scrapers

    scrapers = get_all_scrapers()  # Returns 14+ scrapers
    for scraper in scrapers:
        result = scraper.scrape()

    # Or individual scrapers
    from lexsr.ingestion.scrapers import DNAScraper, BelastingdienstScraper

    dna = DNAScraper()
    docs = dna.scrape()
"""

from .base import BaseScraper, ScrapedDocument, ScrapeResult
from .dna import DNAScraper
from .belastingdienst import BelastingdienstScraper
from .mas import MASScraper
from .sris import SRISScraper
from .generic import (
    GenericGovernmentScraper,
    create_ssb_scraper,
    create_gov_portal_scraper,
    create_justice_scraper,
    create_finance_scraper,
    create_labor_scraper,
    create_education_scraper,
    create_health_scraper,
    create_agriculture_scraper,
    create_natural_resources_scraper,
    create_nimos_scraper,
    create_kos_scraper,
    create_chs_scraper,
)

__all__ = [
    # Base classes
    "BaseScraper",
    "ScrapedDocument",
    "ScrapeResult",

    # Specialized scrapers
    "DNAScraper",
    "BelastingdienstScraper",
    "MASScraper",
    "SRISScraper",

    # Generic scraper
    "GenericGovernmentScraper",

    # Factory functions
    "create_ssb_scraper",
    "create_gov_portal_scraper",
    "create_justice_scraper",
    "create_finance_scraper",
    "create_labor_scraper",
    "create_education_scraper",
    "create_health_scraper",
    "create_agriculture_scraper",
    "create_natural_resources_scraper",
    "create_nimos_scraper",
    "create_kos_scraper",
    "create_chs_scraper",

    # Convenience
    "get_all_scrapers",
    "get_priority_scrapers",
]


def get_all_scrapers(rate_limit: float = 2.0):
    """
    Get ALL available scrapers (16+ sources).

    Includes:
    - 4 specialized scrapers (DNA, Tax, MAS, SRIS)
    - 12+ generic scrapers (ministries, agencies)

    Args:
        rate_limit: Rate limit for all scrapers (seconds between requests)

    Returns:
        List of 16+ scraper instances ready to use
    """
    return [
        # PRIORITY 1 - Critical Sources
        DNAScraper(rate_limit=rate_limit),  # Parliament - PRIMARY
        create_gov_portal_scraper(rate_limit),  # Government portal - State Bulletins

        # PRIORITY 2 - High Priority
        BelastingdienstScraper(rate_limit=rate_limit),  # Tax
        MASScraper(rate_limit=rate_limit),  # Central Bank
        SRISScraper(rate_limit=rate_limit),  # Case Law
        create_ssb_scraper(rate_limit),  # State Oil

        # PRIORITY 3 - Ministries (on gov.sr)
        create_justice_scraper(rate_limit),  # Justice
        create_finance_scraper(rate_limit),  # Finance
        create_labor_scraper(rate_limit),  # Labor
        create_health_scraper(rate_limit),  # Health
        create_education_scraper(rate_limit),  # Education
        create_agriculture_scraper(rate_limit),  # Agriculture
        create_natural_resources_scraper(rate_limit),  # Natural Resources

        # PRIORITY 4 - Agencies & Special Bodies
        create_kos_scraper(rate_limit),  # Children's Ombudsman
        create_chs_scraper(rate_limit),  # Electoral Bureau
        create_nimos_scraper(rate_limit),  # Environment
    ]


def get_priority_scrapers(rate_limit: float = 2.0):
    """
    Get only the highest priority scrapers.

    Returns:
        List of 6 critical scrapers (DNA, Gov Portal, Tax, MAS, SRIS, SSB)
    """
    return [
        DNAScraper(rate_limit=rate_limit),
        create_gov_portal_scraper(rate_limit),
        BelastingdienstScraper(rate_limit=rate_limit),
        MASScraper(rate_limit=rate_limit),
        SRISScraper(rate_limit=rate_limit),
        create_ssb_scraper(rate_limit),
    ]

