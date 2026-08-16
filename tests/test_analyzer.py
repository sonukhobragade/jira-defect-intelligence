"""
Tests for QuickDefectAnalyzer.

analyze_defects() named five helpers that were never written, so it raised
AttributeError on any non-empty DataFrame and every CLI path in main.py that
used it was dead. The first test here is the regression test for that; the
rest pin the behaviour of the helpers that were added.
"""

from __future__ import annotations

import pandas as pd
import pytest

from analyzer import QuickDefectAnalyzer


@pytest.fixture
def analyzer():
    return QuickDefectAnalyzer()


class TestAnalyzeDefects:
    def test_returns_every_documented_section(self, analyzer, defects_df, critical_types):
        """Regression: this used to raise AttributeError on the first missing
        helper, so the whole analysis was unreachable."""
        result = analyzer.analyze_defects(defects_df)
        assert set(result) == {
            "summary", "project_breakdown", "priorities", "issue_types",
            "custom_field", "aging", "cross_project_insights", "top_risks",
            "recommendations",
        }

    def test_empty_frame_reports_an_error_rather_than_raising(self, analyzer):
        assert analyzer.analyze_defects(pd.DataFrame()) == {"error": "No data to analyze"}


class TestSummaryStats:
    def test_counts_open_and_critical(self, analyzer, defects_df, critical_types):
        summary = analyzer._get_summary_stats(defects_df)
        assert summary["total_defects"] == 5
        assert summary["projects_affected"] == 2
        assert summary["open_defects"] == 3
        assert summary["critical_count"] == 2
        assert summary["high_priority_count"] == 2


class TestPrioritiesAndTypes:
    def test_priority_counts(self, analyzer, defects_df):
        assert analyzer._analyze_priorities(defects_df) == {"High": 2, "Medium": 2, "Low": 1}

    def test_issue_type_counts(self, analyzer, defects_df):
        assert analyzer._analyze_issue_types(defects_df) == {"Bug": 3, "Critical Bug": 2}

    def test_missing_column_returns_empty_rather_than_raising(self, analyzer):
        assert analyzer._analyze_priorities(pd.DataFrame([{"key": "A-1"}])) == {}


class TestCustomField:
    def test_unknown_is_reported_not_hidden(self, analyzer, defects_df):
        """A large Unknown count is the signal that SEVERITY_FIELD is wrong.
        Dropping it would make a misconfiguration look like clean data."""
        result = analyzer._analyze_custom_field(defects_df)
        assert result["unknown_count"] == 1
        assert result["distribution"]["S1"] == 2

    def test_most_common_ignores_unknown(self, analyzer, defects_df):
        assert analyzer._analyze_custom_field(defects_df)["most_common"] == "S1"

    def test_all_unknown_has_no_most_common(self, analyzer):
        df = pd.DataFrame([{"severity": "Unknown"}, {"severity": "Unknown"}])
        assert analyzer._analyze_custom_field(df)["most_common"] is None


class TestAging:
    def test_defects_land_in_the_right_buckets(self, analyzer, defects_df):
        dist = analyzer._analyze_aging(defects_df)["age_distribution"]
        assert dist["0-7 days"] == 1      # 3 days
        assert dist["8-14 days"] == 1     # 10 days
        assert dist["15-30 days"] == 1    # 20 days
        assert dist["31-60 days"] == 1    # 45 days
        assert dist["90+ days"] == 1      # 120 days

    def test_buckets_cover_every_defect_exactly_once(self, analyzer, defects_df):
        """Off-by-one bucket edges would double count or drop a defect."""
        dist = analyzer._analyze_aging(defects_df)["age_distribution"]
        assert sum(dist.values()) == len(defects_df)

    def test_oldest_open_defect_ignores_resolved_ones(self, analyzer, defects_df):
        oldest = analyzer._analyze_aging(defects_df)["oldest_open_defect"]
        assert oldest["key"] == "AAA-3"
        assert oldest["age_days"] == 120

    def test_all_resolved_has_no_oldest_open(self, analyzer):
        df = pd.DataFrame([{"key": "A-1", "project": "A", "age_days": 9,
                            "status": "Resolved"}])
        assert analyzer._analyze_aging(df)["oldest_open_defect"] is None


class TestTopRisks:
    def test_ranked_worst_first(self, analyzer, defects_df, critical_types):
        risks = analyzer._identify_top_risks(defects_df)
        assert risks[0]["key"] == "AAA-3"  # critical, open, oldest
        scores = [r["risk_score"] for r in risks]
        assert scores == sorted(scores, reverse=True)

    def test_resolved_defects_score_below_comparable_open_ones(self, analyzer, critical_types):
        df = pd.DataFrame([
            {"key": "A-1", "project": "A", "issue_type": "Bug", "priority": "Low",
             "status": "Open", "age_days": 10, "assignee": "x", "summary": "s"},
            {"key": "A-2", "project": "A", "issue_type": "Bug", "priority": "Low",
             "status": "Resolved", "age_days": 10, "assignee": "x", "summary": "s"},
        ])
        by_key = {r["key"]: r["risk_score"] for r in analyzer._identify_top_risks(df)}
        assert by_key["A-1"] > by_key["A-2"]

    def test_age_contribution_is_capped(self, analyzer, critical_types):
        """Without a cap a very old defect outranks every critical one purely
        on age, which is how genuinely urgent items get buried."""
        df = pd.DataFrame([
            {"key": "OLD", "project": "A", "issue_type": "Bug", "priority": "Low",
             "status": "Open", "age_days": 3650, "assignee": "x", "summary": "s"},
            {"key": "CRIT", "project": "A", "issue_type": "Critical Bug",
             "priority": "High", "status": "Open", "age_days": 30,
             "assignee": "x", "summary": "s"},
        ])
        by_key = {r["key"]: r["risk_score"] for r in analyzer._identify_top_risks(df)}
        assert by_key["CRIT"] > by_key["OLD"]

    def test_limit_is_respected(self, analyzer, defects_df, critical_types):
        assert len(analyzer._identify_top_risks(defects_df, limit=2)) == 2

    def test_empty_frame_gives_no_risks(self, analyzer):
        assert analyzer._identify_top_risks(pd.DataFrame()) == []
