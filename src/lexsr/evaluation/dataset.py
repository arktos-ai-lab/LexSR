"""
Known-answer datasets for evaluation.

Hand-curated question-answer pairs for Suriname legal retrieval,
citation resolution, and temporal correctness testing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class KnownAnswer:
    """A single known-answer test case."""
    id: str
    category: str                         # "citation", "temporal", "retrieval", "entity"
    input_text: str                       # the query or text to process
    expected_uris: List[str] = field(default_factory=list)  # expected canonical URIs
    expected_text: Optional[str] = None   # expected answer text (substring match)
    query_date: Optional[date] = None     # for temporal queries
    source: str = ""                      # where this test case came from
    difficulty: str = "medium"            # easy, medium, hard
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class KnownAnswerDataset:
    """
    Collection of known-answer test cases for benchmarking.

    Can be loaded from JSON or built programmatically.
    """

    def __init__(self, name: str = "default"):
        self.name = name
        self._cases: List[KnownAnswer] = []

    @property
    def count(self) -> int:
        return len(self._cases)

    def add(self, case: KnownAnswer) -> None:
        self._cases.append(case)

    def cases(self, category: Optional[str] = None) -> List[KnownAnswer]:
        if category:
            return [c for c in self._cases if c.category == category]
        return list(self._cases)

    def categories(self) -> List[str]:
        return sorted(set(c.category for c in self._cases))

    def save(self, path: str) -> None:
        """Save dataset to JSON."""
        data = {
            "name": self.name,
            "cases": [
                {
                    "id": c.id,
                    "category": c.category,
                    "input_text": c.input_text,
                    "expected_uris": c.expected_uris,
                    "expected_text": c.expected_text,
                    "query_date": c.query_date.isoformat() if c.query_date else None,
                    "source": c.source,
                    "difficulty": c.difficulty,
                    "tags": c.tags,
                    "metadata": c.metadata,
                }
                for c in self._cases
            ],
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, path: str) -> KnownAnswerDataset:
        """Load dataset from JSON."""
        data = json.loads(Path(path).read_text())
        ds = cls(name=data.get("name", "loaded"))
        for c in data.get("cases", []):
            ds.add(KnownAnswer(
                id=c["id"],
                category=c["category"],
                input_text=c["input_text"],
                expected_uris=c.get("expected_uris", []),
                expected_text=c.get("expected_text"),
                query_date=date.fromisoformat(c["query_date"]) if c.get("query_date") else None,
                source=c.get("source", ""),
                difficulty=c.get("difficulty", "medium"),
                tags=c.get("tags", []),
                metadata=c.get("metadata", {}),
            ))
        return ds

    @classmethod
    def suriname_legal_seed(cls) -> KnownAnswerDataset:
        """Create a seed dataset with Suriname legal test cases."""
        ds = cls(name="suriname_legal_seed")

        # Citation resolution test cases
        ds.add(KnownAnswer(
            id="cit-001",
            category="citation",
            input_text="artikel 2 Arbeidswet",
            expected_uris=["/id/law/arbeidswet-1963"],
            source="manual",
            difficulty="easy",
            tags=["arbeidswet", "legislation"],
        ))
        ds.add(KnownAnswer(
            id="cit-002",
            category="citation",
            input_text="ECLI:NL:HR:2020:1234, r.o. 4.3",
            expected_uris=["/id/ecli/ECLI:NL:HR:2020:1234/consideration/4.3"],
            source="manual",
            difficulty="easy",
            tags=["ecli", "case_law"],
        ))
        ds.add(KnownAnswer(
            id="cit-003",
            category="citation",
            input_text="artikel 1 lid 1 Grondwet",
            expected_uris=["/id/law/grondwet-1987"],
            source="manual",
            difficulty="easy",
            tags=["grondwet"],
        ))
        ds.add(KnownAnswer(
            id="cit-004",
            category="citation",
            input_text="Verordening (EU) 2016/679",
            expected_uris=["/id/celex/32016R0679"],
            source="manual",
            difficulty="medium",
            tags=["eu", "avg", "gdpr"],
        ))
        ds.add(KnownAnswer(
            id="cit-005",
            category="citation",
            input_text="artikel 287 Sr stelt doodslag strafbaar",
            expected_uris=["/id/law/wetboek-van-strafrecht"],
            source="manual",
            difficulty="easy",
            tags=["strafrecht"],
        ))
        ds.add(KnownAnswer(
            id="cit-006",
            category="citation",
            input_text=(
                "Zoals bepaald in artikel 3 BW (zie "
                "ECLI:NL:HR:2020:1234, r.o. 4.3)."
            ),
            expected_uris=[
                "/id/law/burgerlijk-wetboek",
                "/id/ecli/ECLI:NL:HR:2020:1234/consideration/4.3",
            ],
            source="manual",
            difficulty="hard",
            tags=["multi_ref", "complex"],
        ))

        # Temporal correctness test cases
        ds.add(KnownAnswer(
            id="temp-001",
            category="temporal",
            input_text="What was article 2 Arbeidswet on 2020-03-15?",
            query_date=date(2020, 3, 15),
            expected_uris=["/id/law/arbeidswet-1963"],
            source="manual",
            difficulty="medium",
            tags=["temporal", "arbeidswet"],
        ))

        # Gazette reference
        ds.add(KnownAnswer(
            id="cit-007",
            category="citation",
            input_text="S.B. 1963 no. 163",
            expected_uris=["/id/gazette/sr-1963-163"],
            source="manual",
            difficulty="medium",
            tags=["gazette", "staatsblad"],
        ))

        # Gouvernementsblad reference
        ds.add(KnownAnswer(
            id="cit-008",
            category="citation",
            input_text="G.B. 1936 no. 144",
            expected_uris=["/id/gazette/sr-1936-144"],
            source="manual",
            difficulty="hard",
            tags=["gazette", "gouvernementsblad"],
        ))

        return ds

    # Keep backward compatibility alias
    @classmethod
    def dutch_legal_seed(cls) -> KnownAnswerDataset:
        """Alias for suriname_legal_seed (backward compatibility)."""
        return cls.suriname_legal_seed()
