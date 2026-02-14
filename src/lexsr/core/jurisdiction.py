"""
Jurisdiction configuration for LexSR.

Provides jurisdiction-specific settings like language, URI prefixes,
citation patterns, and fragment naming conventions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class JurisdictionConfig:
    """
    Configuration for a specific legal jurisdiction.

    Encapsulates all jurisdiction-specific settings so the core
    system remains jurisdiction-agnostic.
    """
    code: str                          # ISO-like code: "SR", "NL", "EU"
    name: str                          # Full name: "Suriname", "Netherlands"
    language: str                      # Primary language: "nl", "en"
    uri_prefix: str                    # URI prefix: "sr", "nl"
    gazette_name: str = ""             # Name of official gazette
    citation_patterns: List[str] = field(default_factory=list)
    fragment_aliases: Dict[str, str] = field(default_factory=dict)
    abbreviations: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def suriname(cls) -> JurisdictionConfig:
        """Create configuration for Suriname."""
        return cls(
            code="SR",
            name="Suriname",
            language="nl",
            uri_prefix="sr",
            gazette_name="Staatsblad van de Republiek Suriname",
            citation_patterns=[
                r"[Aa]rt(?:ikel)?\.?\s+(\d+(?:[:\.]\d+)?[a-z]?)",
                r"[Ll]id\s+(\d+[a-z]?)",
            ],
            fragment_aliases={
                "artikel": "article",
                "lid": "paragraph",
                "sub": "sub",
                "boek": "book",
                "titel": "title",
                "hoofdstuk": "chapter",
                "afdeling": "section",
            },
            abbreviations={
                "Arbeidswet": "arbeidswet-1963",
                "AW": "arbeidswet-1963",
                "Grondwet": "grondwet-1987",
                "GW": "grondwet-1987",
                "WvSr": "wetboek-van-strafrecht",
                "Sr": "wetboek-van-strafrecht",
                "WvSv": "wetboek-van-strafvordering",
                "Sv": "wetboek-van-strafvordering",
                "BW": "burgerlijk-wetboek",
                "Hw": "huwelijkswet",
                "Pw": "personeelswet",
            },
        )

    @classmethod
    def default(cls) -> JurisdictionConfig:
        """Create default (Suriname) configuration."""
        return cls.suriname()
