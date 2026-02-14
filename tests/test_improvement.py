"""
Tests for the continuous improvement system (Sprint 6).

Covers: ActiveLearner, LearningExample, LearningStats,
QualityDashboard, QualitySnapshot.

Run with: python -m pytest tests/test_improvement.py -v
"""

import pytest

from lexsr.improvement.active_learning import (
    ActiveLearner,
    LearningExample,
    LearningStats,
)
from lexsr.improvement.quality_dashboard import QualityDashboard, QualitySnapshot


# ===================================================================
# Quality Dashboard
# ===================================================================

class TestQualitySnapshot:
    def test_default_snapshot(self):
        snap = QualitySnapshot()
        assert snap.citation_f1 == 0.0
        assert snap.total_works == 0
        assert snap.timestamp != ""

    def test_snapshot_summary(self):
        snap = QualitySnapshot(
            version="0.4.0",
            citation_precision=0.85,
            citation_recall=0.90,
            citation_f1=0.875,
            resolution_rate=0.80,
            total_works=100,
            total_expressions=200,
            total_fragments=500,
            integrity_errors=2,
            integrity_warnings=5,
            benchmark_pass_rate=0.92,
        )
        s = snap.summary()
        assert s["version"] == "0.4.0"
        assert s["citation"]["precision"] == 0.85
        assert s["citation"]["f1"] == 0.875
        assert s["data"]["works"] == 100
        assert s["integrity"]["errors"] == 2
        assert s["benchmark_pass_rate"] == 0.92


class TestQualityDashboard:
    @pytest.fixture
    def dashboard(self, tmp_path):
        d = QualityDashboard(str(tmp_path / "quality_test.db"))
        yield d
        d.close()

    def test_empty_dashboard(self, dashboard):
        assert dashboard.get_latest() is None
        assert dashboard.get_history() == []

    def test_record_and_get_latest(self, dashboard):
        snap = QualitySnapshot(
            version="0.4.0",
            citation_f1=0.85,
            total_works=50,
        )
        snap_id = dashboard.record_snapshot(snap)
        assert snap_id > 0

        latest = dashboard.get_latest()
        assert latest is not None
        assert latest.version == "0.4.0"
        assert latest.citation_f1 == 0.85
        assert latest.total_works == 50

    def test_history(self, dashboard):
        for i in range(5):
            dashboard.record_snapshot(QualitySnapshot(
                timestamp=f"2024-01-{i+1:02d}T00:00:00",
                version=f"v{i}",
                citation_f1=0.5 + i * 0.1,
            ))

        history = dashboard.get_history(limit=3)
        assert len(history) == 3
        # Most recent first
        assert history[0].version == "v4"

    def test_trend(self, dashboard):
        for i in range(5):
            dashboard.record_snapshot(QualitySnapshot(
                timestamp=f"2024-01-{i+1:02d}T00:00:00",
                citation_f1=0.5 + i * 0.1,
            ))

        trend = dashboard.trend("citation_f1")
        assert len(trend) == 5
        # Chronological order
        assert trend[0]["value"] == 0.5
        assert trend[-1]["value"] == pytest.approx(0.9, abs=0.01)

    def test_trend_invalid_metric(self, dashboard):
        result = dashboard.trend("invalid_metric_name")
        assert result == []

    def test_is_improving(self, dashboard):
        for i in range(5):
            dashboard.record_snapshot(QualitySnapshot(
                timestamp=f"2024-01-{i+1:02d}T00:00:00",
                citation_f1=0.5 + i * 0.1,
            ))
        assert dashboard.is_improving("citation_f1") is True

    def test_is_improving_declining(self, dashboard):
        for i in range(5):
            dashboard.record_snapshot(QualitySnapshot(
                timestamp=f"2024-01-{i+1:02d}T00:00:00",
                citation_f1=0.9 - i * 0.1,
            ))
        assert dashboard.is_improving("citation_f1") is False

    def test_is_improving_insufficient_data(self, dashboard):
        dashboard.record_snapshot(QualitySnapshot(citation_f1=0.5))
        assert dashboard.is_improving("citation_f1") is None

    def test_context_manager(self, tmp_path):
        path = str(tmp_path / "ctx_quality.db")
        with QualityDashboard(path) as d:
            d.record_snapshot(QualitySnapshot(version="test"))
        # Should not raise after close


# ===================================================================
# Active Learner
# ===================================================================

class TestLearningStats:
    def test_empty_stats(self):
        stats = LearningStats()
        s = stats.summary()
        assert s["total_examples"] == 0
        assert s["annotation_rate"] == 0.0

    def test_stats_with_data(self):
        stats = LearningStats(
            total_examples=100,
            annotated=40,
            pending=60,
            corrections_applied=10,
            new_abbreviations=3,
        )
        s = stats.summary()
        assert s["annotation_rate"] == 0.4
        assert s["corrections_applied"] == 10


class TestActiveLearner:
    @pytest.fixture
    def learner(self, tmp_path):
        al = ActiveLearner(str(tmp_path / "learning_test.db"))
        yield al
        al.close()

    def _add_example(self, learner, id_: str, text: str = "test ref",
                     ref_type: str = "legislation") -> None:
        learner._conn.execute("""
            INSERT INTO learning_examples (id, raw_text, ref_type, confidence, attempts)
            VALUES (?, ?, ?, 0.3, 1)
        """, (id_, text, ref_type))
        learner._conn.commit()

    def test_empty_learner(self, learner):
        stats = learner.stats()
        assert stats.total_examples == 0
        assert stats.pending == 0

    def test_get_next_batch_empty(self, learner):
        batch = learner.get_next_batch(10)
        assert batch == []

    def test_add_and_get_batch(self, learner):
        self._add_example(learner, "ex-1", "artikel 5 Wet Bob")
        self._add_example(learner, "ex-2", "art. 12 Wet xyz")

        batch = learner.get_next_batch(10)
        assert len(batch) == 2
        assert isinstance(batch[0], LearningExample)
        assert batch[0].raw_text in ["artikel 5 Wet Bob", "art. 12 Wet xyz"]

    def test_submit_annotation(self, learner):
        self._add_example(learner, "ex-1", "artikel 5 Wet Bob")

        success = learner.submit_annotation(
            "ex-1",
            correct_uri="/id/law/some-law-id/2024-01-15/article/5",
            annotator="tester",
        )
        assert success

        # Should no longer appear in pending batch
        batch = learner.get_next_batch(10)
        assert len(batch) == 0

    def test_stats_after_annotation(self, learner):
        self._add_example(learner, "ex-1")
        self._add_example(learner, "ex-2")
        learner.submit_annotation("ex-1", correct_uri="/id/law/x")

        stats = learner.stats()
        assert stats.total_examples == 2
        assert stats.annotated == 1
        assert stats.pending == 1

    def test_apply_corrections(self, learner):
        # Add example with metadata containing parsed_law
        learner._conn.execute("""
            INSERT INTO learning_examples
                (id, raw_text, ref_type, confidence, metadata, annotated, correct_uri)
            VALUES (?, ?, ?, 0.3, ?, 1, ?)
        """, (
            "ex-1", "art. 5 Wet Bob", "legislation",
            '{"parsed_law": "Wet Bob"}',
            "/id/law/some-law-id/2024-01-15/article/5",
        ))
        learner._conn.commit()

        applied = learner.apply_corrections()
        assert applied == 1

        corrections = learner.get_corrections()
        assert len(corrections) == 1
        assert corrections[0]["abbreviation"] == "Wet Bob"
        assert corrections[0]["bwb_id"] == "some-law-id"

    def test_apply_corrections_no_parsed_law(self, learner):
        learner._conn.execute("""
            INSERT INTO learning_examples
                (id, raw_text, ref_type, confidence, metadata, annotated, correct_uri)
            VALUES (?, ?, ?, 0.3, '{}', 1, ?)
        """, ("ex-1", "some ref", "legislation", "/id/law/x"))
        learner._conn.commit()

        applied = learner.apply_corrections()
        assert applied == 0  # no parsed_law in metadata

    def test_context_manager(self, tmp_path):
        path = str(tmp_path / "ctx_learning.db")
        with ActiveLearner(path) as al:
            stats = al.stats()
            assert stats.total_examples == 0
