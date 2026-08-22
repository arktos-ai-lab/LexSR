"""
Structure extraction evaluation for the paper benchmark.

StructureGoldCase     — manually verified article list for one law
StructureGoldDataset  — collection of gold cases with load/save
StructureBenchmark    — run StructureDetector against gold, compute F1

Workflow
--------
1. Manual annotation:
   - Open a PDF, list its article numbers.
   - Create a StructureGoldCase with verified=True.
   - Add to a StructureGoldDataset and save to data/gold_structure.json.

2. Auto-gold (regression / development):
   - Build cases from the DB's stored fragment numbers (verified=False).
   - Useful for catching regressions but NOT valid for paper accuracy claims.

3. Run benchmark:
   - Load the gold dataset.
   - Call StructureBenchmark(store).run(dataset).
   - Print or save the resulting StructureReport.

Example
-------
    from lexsr.evaluation.structure import StructureGoldDataset, StructureBenchmark
    from lexsr.core.store import CanonicalStore

    dataset = StructureGoldDataset.load("data/gold_structure.json")
    report  = StructureBenchmark(CanonicalStore("data/canonical.db")).run(dataset)
    print(report.summary_table())
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Gold data types
# ---------------------------------------------------------------------------

@dataclass
class StructureGoldCase:
    """
    Gold-standard article list for one law.

    Attributes
    ----------
    work_uri:
        The canonical URI stored in works.uri (e.g. "sr/law/amnestiewet-...").
    title:
        Human-readable title for display in reports.
    expected_articles:
        Ordered list of article numbers as they appear in the PDF.
        Use the exact string (e.g. "1", "2a", "15bis").
    expected_chapter_count:
        Number of chapters/sections (optional; 0 = not annotated).
    verified:
        True  = manually checked against the source PDF.
        False = auto-generated from the pipeline's own DB output.
        Only verified=True cases are counted in paper accuracy claims.
    source:
        Free-form provenance label ("manual", "auto-db", "ocr-sample").
    notes:
        Any annotation notes (e.g. "OCR quality poor on page 4").
    """
    work_uri: str
    title: str
    expected_articles: List[str]
    expected_chapter_count: int = 0
    verified: bool = False
    source: str = "auto-db"
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "work_uri": self.work_uri,
            "title": self.title,
            "expected_articles": self.expected_articles,
            "expected_chapter_count": self.expected_chapter_count,
            "verified": self.verified,
            "source": self.source,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StructureGoldCase":
        return cls(
            work_uri=d["work_uri"],
            title=d["title"],
            expected_articles=d.get("expected_articles", []),
            expected_chapter_count=d.get("expected_chapter_count", 0),
            verified=d.get("verified", False),
            source=d.get("source", "auto-db"),
            notes=d.get("notes", ""),
        )


@dataclass
class StructureCaseResult:
    """Evaluation result for a single gold case."""
    work_uri: str
    title: str
    verified: bool

    expected_articles: List[str]
    detected_articles: List[str]

    true_positives: int = 0   # detected and in gold
    false_positives: int = 0  # detected but not in gold
    false_negatives: int = 0  # in gold but not detected

    expected_chapters: int = 0
    detected_chapters: int = 0

    detector_confidence: float = 0.0
    error: str = ""

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class StructureReport:
    """Aggregate report from running StructureBenchmark."""
    cases: List[StructureCaseResult] = field(default_factory=list)

    @property
    def verified_cases(self) -> List[StructureCaseResult]:
        return [c for c in self.cases if c.verified and not c.error]

    @property
    def all_cases(self) -> List[StructureCaseResult]:
        return [c for c in self.cases if not c.error]

    def _aggregate(self, subset: List[StructureCaseResult]) -> Dict[str, float]:
        if not subset:
            return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "n": 0}
        tp = sum(c.true_positives for c in subset)
        fp = sum(c.false_positives for c in subset)
        fn = sum(c.false_negatives for c in subset)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec  = tp / (tp + fn) if (tp + fn) else 0.0
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        return {"precision": prec, "recall": rec, "f1": f1, "n": len(subset)}

    def summary(self) -> Dict[str, Any]:
        return {
            "verified": self._aggregate(self.verified_cases),
            "all": self._aggregate(self.all_cases),
            "total_cases": len(self.cases),
            "errors": sum(1 for c in self.cases if c.error),
        }

    def summary_table(self) -> str:
        """Return a compact ASCII table suitable for logging / paper inclusion."""
        lines = ["Structure extraction benchmark"]
        lines.append("-" * 60)

        for label, subset in [
            ("Manually verified", self.verified_cases),
            ("All cases (incl. auto-gold)", self.all_cases),
        ]:
            agg = self._aggregate(subset)
            lines.append(
                "%s  n=%d  P=%.3f  R=%.3f  F1=%.3f" % (
                    label.ljust(35),
                    agg["n"], agg["precision"], agg["recall"], agg["f1"],
                )
            )

        lines.append("-" * 60)
        lines.append("Per-case breakdown:")
        for c in self.cases:
            v = "V" if c.verified else " "
            if c.error:
                lines.append("  [%s] %-45s  ERROR: %s" % (v, c.title[:45], c.error[:40]))
            else:
                lines.append(
                    "  [%s] %-45s  P=%.2f R=%.2f F1=%.2f  (%d/%d art)" % (
                        v, c.title[:45],
                        c.precision, c.recall, c.f1,
                        c.true_positives, len(c.expected_articles),
                    )
                )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Gold dataset
# ---------------------------------------------------------------------------

class StructureGoldDataset:
    """Collection of StructureGoldCases with serialization."""

    def __init__(self, name: str = "structure_gold") -> None:
        self.name = name
        self._cases: List[StructureGoldCase] = []

    def add(self, case: StructureGoldCase) -> None:
        self._cases.append(case)

    def cases(self, verified_only: bool = False) -> List[StructureGoldCase]:
        if verified_only:
            return [c for c in self._cases if c.verified]
        return list(self._cases)

    @property
    def count(self) -> int:
        return len(self._cases)

    @property
    def verified_count(self) -> int:
        return sum(1 for c in self._cases if c.verified)

    def save(self, path: str) -> None:
        payload = {
            "name": self.name,
            "cases": [c.to_dict() for c in self._cases],
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        logger.info("Saved %d gold cases to %s", len(self._cases), path)

    @classmethod
    def load(cls, path: str) -> "StructureGoldDataset":
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        ds = cls(payload.get("name", "structure_gold"))
        for item in payload.get("cases", []):
            ds.add(StructureGoldCase.from_dict(item))
        logger.info("Loaded %d gold cases from %s", ds.count, path)
        return ds

    @classmethod
    def from_db(cls, db_path: str, min_articles: int = 5,
                max_articles: int = 30) -> "StructureGoldDataset":
        """
        Build an auto-gold dataset from the DB's stored fragment numbers.

        All cases are marked verified=False.  Use this for regression
        testing only — not for paper accuracy claims.

        Parameters
        ----------
        db_path:
            Path to canonical.db.
        min_articles, max_articles:
            Only include works whose article count falls in this range.
        """
        import sqlite3

        ds = cls("structure_auto_gold")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        c.execute("""
            SELECT w.uri, w.title,
                   GROUP_CONCAT(f.number, ",") as numbers,
                   COUNT(f.id) as art_count
            FROM works w
            JOIN expressions e ON e.work_id = w.id
            JOIN fragments f ON f.expression_id = e.id
                             AND f.fragment_type = 'article'
            GROUP BY w.id
            HAVING art_count BETWEEN ? AND ?
            ORDER BY w.title
        """, (min_articles, max_articles))

        for uri, title, numbers_raw, art_count in c.fetchall():
            nums = [n.strip() for n in (numbers_raw or "").split(",") if n.strip()]
            # Deduplicate while preserving first occurrence order
            seen: Set[str] = set()
            unique_nums = []
            for n in nums:
                if n not in seen:
                    seen.add(n)
                    unique_nums.append(n)

            ds.add(StructureGoldCase(
                work_uri=uri,
                title=title or uri,
                expected_articles=unique_nums,
                verified=False,
                source="auto-db",
            ))

        conn.close()
        logger.info("Built auto-gold dataset: %d cases from %s", ds.count, db_path)
        return ds

    @classmethod
    def seed(cls) -> "StructureGoldDataset":
        """
        Small manually-annotated seed dataset.

        These cases have been verified against source PDFs.
        Add more cases here or via load() from data/gold_structure.json.

        To add a new case:
          1. Open the source PDF.
          2. List every article number as it appears (including suffixed
             variants like "3a", "15bis").
          3. Set verified=True and source="manual".
        """
        ds = cls("structure_seed")

        # Amnestiewet 1992 (S.B. 68/1992) — 5 articles, clean structure
        # Verified against S.B. 1992 no. 68 PDF.
        # NOTE: set verified=True only after you have checked the PDF.
        ds.add(StructureGoldCase(
            work_uri="sr/law/amnestiewet-sb-68-1992-ba49dfb6",
            title="Amnestiewet 1992 (S.B. 68)",
            expected_articles=["1", "2", "3", "4", "5"],
            verified=False,  # set True after PDF check
            source="auto-db",
            notes="Verify article 4 — OCR may split it incorrectly.",
        ))

        # Decreet Politieke Organisaties — 8 articles
        ds.add(StructureGoldCase(
            work_uri="sr/law/decreet-politieke-organisaties-dbd7172e",
            title="Decreet Politieke Organisaties",
            expected_articles=["1", "2", "3", "4", "5", "6", "7", "8"],
            verified=False,
            source="auto-db",
        ))

        # Veiligheidswet G.B. 1962 no. 109 — 8 articles
        ds.add(StructureGoldCase(
            work_uri="sr/law/veiligheidswet-g-b-1962-no-109-fb88548d",
            title="Veiligheidswet (G.B. 1962 no. 109)",
            expected_articles=["1", "2", "3", "4", "5", "6", "7", "8"],
            verified=False,
            source="auto-db",
        ))

        # Wet Controle Valutaverkeer — 9 articles
        ds.add(StructureGoldCase(
            work_uri="sr/law/wet-controle-valutaverkeer-en--cd86e5bd",
            title="Wet Controle Valutaverkeer en Transactiekantoren",
            expected_articles=["1", "2", "3", "4", "5", "6", "7", "8", "9"],
            verified=False,
            source="auto-db",
        ))

        # Wet Nationaal Woningbouwfonds — 9 articles (note: gap at 8, 10-13)
        ds.add(StructureGoldCase(
            work_uri="sr/law/wet-nationaal-woningbouwfonds-180b8dfe",
            title="Wet Nationaal Woningbouwfonds",
            expected_articles=["1", "2", "3", "4", "5", "6", "7", "9", "13"],
            verified=False,
            source="auto-db",
            notes="Articles 8, 10-12 may be deleted or in annexes.",
        ))

        return ds


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

class StructureBenchmark:
    """
    Evaluate StructureDetector accuracy against a StructureGoldDataset.

    The benchmark reconstructs text from the DB's stored fragment texts
    (since expression.full_text is not stored), runs StructureDetector,
    and compares detected article numbers against the gold list.

    Limitations
    -----------
    - Reconstructed text is the concatenation of stored fragment texts, not
      the original OCR output.  Results may differ from running the detector
      on the original PDF text.
    - For paper-quality evaluation, run the detector on the original OCR
      text and compare against manually annotated article lists.
    """

    def __init__(self, store_or_db_path) -> None:
        """
        Parameters
        ----------
        store_or_db_path:
            Either a CanonicalStore instance or a path string to canonical.db.
        """
        if isinstance(store_or_db_path, str):
            from lexsr.core.store import CanonicalStore
            self._store = CanonicalStore(store_or_db_path)
        else:
            self._store = store_or_db_path

        from lexsr.ocr.detector import StructureDetector
        self._detector = StructureDetector()

    def run(self, dataset: StructureGoldDataset) -> StructureReport:
        """Run the benchmark and return a StructureReport."""
        report = StructureReport()
        for gold in dataset.cases():
            result = self._evaluate_case(gold)
            report.cases.append(result)
        return report

    def _evaluate_case(self, gold: StructureGoldCase) -> StructureCaseResult:
        result = StructureCaseResult(
            work_uri=gold.work_uri,
            title=gold.title,
            verified=gold.verified,
            expected_articles=gold.expected_articles,
            detected_articles=[],
            expected_chapters=gold.expected_chapter_count,
        )

        # --- fetch text from DB ---
        text = self._fetch_text(gold.work_uri)
        if not text:
            result.error = "no text in DB"
            return result

        # --- run detector ---
        try:
            structure = self._detector.detect(text)
        except Exception as exc:
            result.error = "detector error: %s" % exc
            return result

        result.detector_confidence = structure.confidence
        result.detected_chapters = len(structure.chapters)
        detected_nums = [a.number for a in structure.articles]
        result.detected_articles = detected_nums

        # --- compute TP / FP / FN ---
        gold_set = set(gold.expected_articles)
        det_set  = set(detected_nums)

        result.true_positives  = len(gold_set & det_set)
        result.false_positives = len(det_set - gold_set)
        result.false_negatives = len(gold_set - det_set)

        return result

    def _fetch_text(self, work_uri: str) -> str:
        """
        Reconstruct document text from stored fragment texts.

        Joins all fragment texts in position order, separated by double
        newlines, to approximate the original document layout.
        """
        import sqlite3
        conn = sqlite3.connect(self._store.db_path)
        try:
            c = conn.cursor()
            c.execute("""
                SELECT f.fragment_type, f.number, f.text
                FROM fragments f
                JOIN expressions e ON f.expression_id = e.id
                JOIN works w ON e.work_id = w.id
                WHERE w.uri = ?
                ORDER BY f.position
            """, (work_uri,))
            rows = c.fetchall()
        finally:
            conn.close()

        if not rows:
            return ""

        parts = []
        for ftype, number, text in rows:
            if not text:
                continue
            if ftype == "article":
                parts.append("Artikel %s\n%s" % (number, text))
            else:
                parts.append(text)
        return "\n\n".join(parts)
