"""
Legal document consolidation and amendment tracking.

Pipeline stages:
  1. DocumentClassifier  -- base law vs. wijzigingswet, extracts AmendmentTargets
  2. AmendmentParser     -- extracts AmendmentInstructions from wijzigingswet text
  3. ConsolidationEngine -- applies instructions to the store, creates new Expressions
"""

from .classifier import (
    AmendmentTarget,
    ClassificationResult,
    DocumentClassifier,
    DocumentType,
)
from .amendment import (
    AmendmentInstruction,
    OperationType,
    ParsedAmendment,
)
from .parser import AmendmentParser
from .engine import ConsolidationEngine, ConsolidationResult, ApplicationResult

__all__ = [
    # Classifier
    "DocumentClassifier",
    "DocumentType",
    "ClassificationResult",
    "AmendmentTarget",
    # Amendment model
    "AmendmentInstruction",
    "OperationType",
    "ParsedAmendment",
    # Parser
    "AmendmentParser",
    # Engine
    "ConsolidationEngine",
    "ConsolidationResult",
    "ApplicationResult",
]
