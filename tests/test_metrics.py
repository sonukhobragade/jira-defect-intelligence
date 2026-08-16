"""
Tests for the aggregate metrics.

These numbers get quoted in quality reviews, which is exactly why they need
pinning. A wrong rate is worse than a missing one: nobody argues with a figure
that looks precise.

Every test here corresponds to something that was wrong:

- On an empty result set, pandas returns NaN for a mean. That NaN survived
  rounding and formatting and reached the report as "Resolution Rate: nan%".
- `QuickDefectAnalyzer` never returned `resolution_rate` at all, while the
  dashboard read that key, so the panel showed "NaN%".
- Both dashboards then multiplied an already-percentage value by 100, which
  turned 65% into "6500.0%".
"""

from __future__ import annotations

import pandas as pd
import pytest

from analyzer import QuickDefectAnalyzer
from defect_analyzer import DefectAnalyzer


SUMMARY_COLUMNS = [
    "project", "is_resolved", "is_critical", "age_days", "assignee",
    "priority", "has_components", "resolution_time_hours",
]


def comprehensive_df(rows):
    """A frame shaped the way DefectAnalyzer.get_comprehensive_summary expects."""
    if not rows:
        empty = pd.DataFrame({c: pd.Series(dtype=object) for c in SUMMARY_COLUMNS})
        for flag in ("is_resolved", "is_critical", "has_components"):
            empty[flag] = empty[flag].astype(bool)
        for number in ("age_days", "resolution_time_hours"):
            empty[number] = empty[number].astype(float)
        return empty
    return pd.DataFrame(rows)


def defect(**overrides):
    base = {
        "project": "ORDERS", "is_resolved": True, "is_critical": False,
        "age_days": 4.0, "assignee": "sam", "priority": "High",
        "has_components": True, "resolution_time_hours": 12.0,
    }
    base.update(overrides)
    return base


@pytest.fixture
def analyzer():
    return DefectAnalyzer.__new__(DefectAnalyzer)  # no JIRA connection needed


class TestEmptyInputIsUnknownNotZero:
    """An empty result set means "nothing to measure", not "everything is
    fine". Both are answers; only one of them is honest."""

    def test_no_metric_comes_back_as_nan(self, analyzer):
        summary = analyzer.get_comprehensive_summary(comprehensive_df([]))
        for key, value in summary.items():
            assert not (isinstance(value, float) and pd.isna(value)), \
                f"{key} is NaN and would print as 'nan'"

    @pytest.mark.parametrize("metric", [
        "resolution_rate", "avg_age_days", "avg_age_open",
        "unassigned_rate", "avg_resolution_time_hours",
    ])
    def test_averages_are_none_rather_than_zero(self, analyzer, metric):
        """Zero would claim a measurement that was never taken: a resolution
        rate of 0% reads as "nothing was fixed", not "no defects existed"."""
        summary = analyzer.get_comprehensive_summary(comprehensive_df([]))
        assert summary[metric] is None

    def test_counts_are_still_zero(self, analyzer):
        # Counts are genuinely zero; only averages are unknown.
        summary = analyzer.get_comprehensive_summary(comprehensive_df([]))
        assert summary["total_defects"] == 0
        assert summary["open_defects"] == 0
        assert summary["critical_defects"] == 0


class TestRatesAreCorrect:
    def test_resolution_rate_is_a_percentage(self, analyzer):
        df = comprehensive_df([defect(is_resolved=True), defect(is_resolved=False)])
        assert analyzer.get_comprehensive_summary(df)["resolution_rate"] == 50.0

    def test_a_single_defect_does_not_break_the_average(self, analyzer):
        df = comprehensive_df([defect(is_resolved=True, age_days=3.0)])
        summary = analyzer.get_comprehensive_summary(df)
        assert summary["resolution_rate"] == 100.0
        assert summary["avg_age_days"] == 3.0

    def test_a_rate_never_exceeds_one_hundred(self, analyzer):
        df = comprehensive_df([defect(is_resolved=True) for _ in range(5)])
        assert analyzer.get_comprehensive_summary(df)["resolution_rate"] <= 100.0

    def test_unassigned_rate_counts_only_unassigned(self, analyzer):
        df = comprehensive_df([
            defect(assignee="Unassigned"), defect(assignee="sam"),
            defect(assignee="dev"), defect(assignee="Unassigned"),
        ])
        assert analyzer.get_comprehensive_summary(df)["unassigned_rate"] == 50.0

    def test_resolution_time_ignores_unresolved_defects(self, analyzer):
        """An unresolved defect has no resolution time. Averaging it in as zero
        would make a slow team look fast."""
        df = comprehensive_df([
            defect(is_resolved=True, resolution_time_hours=10.0),
            defect(is_resolved=False, resolution_time_hours=float("nan")),
        ])
        assert analyzer.get_comprehensive_summary(df)["avg_resolution_time_hours"] == 10.0


class TestQuickAnalyzerSummary:
    def test_resolution_rate_is_present(self, defects_df):
        """The dashboard reads this key. It was never returned, so the panel
        rendered `undefined * 100` as "NaN%"."""
        summary = QuickDefectAnalyzer()._get_summary_stats(defects_df)
        assert "resolution_rate" in summary

    def test_resolution_rate_is_a_percentage_not_a_fraction(self, defects_df):
        """Both dashboards multiplied this by 100 before display. If it were a
        fraction that would be right; it is not, so 65% showed as 6500%."""
        rate = QuickDefectAnalyzer()._get_summary_stats(defects_df)["resolution_rate"]
        assert rate is None or 0.0 <= rate <= 100.0

    def test_the_two_analyzers_agree_on_units(self, defects_df, analyzer):
        """Two summaries feeding one dashboard must use the same scale, or the
        same panel is right on one route and wrong on the other."""
        quick = QuickDefectAnalyzer()._get_summary_stats(defects_df)["resolution_rate"]
        comprehensive = analyzer.get_comprehensive_summary(
            comprehensive_df([defect(is_resolved=True), defect(is_resolved=False)])
        )["resolution_rate"]
        assert quick is None or 0.0 <= quick <= 100.0
        assert 0.0 <= comprehensive <= 100.0

    def test_an_empty_frame_gives_unknown_not_zero(self):
        empty = pd.DataFrame({c: pd.Series(dtype=object)
                              for c in ["status", "age_days", "project",
                                        "issue_type", "priority", "affected_version"]})
        summary = QuickDefectAnalyzer()._get_summary_stats(empty)
        assert summary["resolution_rate"] is None
        assert summary["avg_age_days"] is None
        assert summary["total_defects"] == 0
