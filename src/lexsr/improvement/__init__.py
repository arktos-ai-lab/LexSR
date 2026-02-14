"""
Continuous improvement loop for the Legal Knowledge Fabric.

Sprint 6 per PLAN.md:
  - Active learning on the resolver and entity linker
  - Automated regression tests for ingestion, linking, retrieval
  - Quality dashboards and alerting

"Done when: every release is measurably better."
"""

from .active_learning import ActiveLearner, LearningExample, LearningStats
from .quality_dashboard import QualityDashboard, QualitySnapshot

__all__ = [
    "ActiveLearner",
    "LearningExample",
    "LearningStats",
    "QualityDashboard",
    "QualitySnapshot",
]
