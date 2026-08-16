"""
Tests for QuickJiraCollector's pure helpers and error contract.

No Jira server: the constructor is bypassed, since none of the logic here
needs a live session. Two of these are regression tests for defects that made
the tool report confidently wrong results rather than fail.
"""

from __future__ import annotations

import types

import pytest

from config import Config
from jira_client import QuickJiraCollector

from conftest import make_issue


@pytest.fixture
def collector():
    """Build the collector without connecting to Jira."""
    return QuickJiraCollector.__new__(QuickJiraCollector)


class TestReleaseSequence:
    def test_counts_backwards_within_a_year(self, collector):
        assert collector._generate_release_sequence("REL-25", 3) == ["REL-25", "REL-24", "REL-23"]

    def test_rolls_over_into_the_previous_year(self, collector):
        # A two-part identifier, so the minor part rolls over into the major.
        # A single-number name like "REL-02" counts straight down to REL-00
        # instead, which is a different case and covered separately.
        seq = collector._generate_release_sequence("2026-02", 3)
        assert seq == ["2026-02", "2026-01", "2025-52"]

    def test_a_single_number_name_does_not_roll_over(self, collector):
        assert collector._generate_release_sequence("REL-02", 3) == [
            "REL-02", "REL-01", "REL-00"]

    def test_a_dotted_version_counts_down(self, collector):
        """Behaviour change, deliberately. This used to return ["2026.1"]
        alone, because the matcher only understood one organisation's
        `R<yy>-<nn>` naming and everything else fell through. A trailing
        number has an obvious predecessor, so it is used."""
        assert collector._generate_release_sequence("2026.1", 2) == ["2026.1", "2026.0"]

    def test_a_name_with_no_number_is_returned_untouched(self, collector):
        """There is no way to guess what came before "Autumn Release", and
        inventing one would send queries for releases that never existed."""
        assert collector._generate_release_sequence("Autumn Release", 3) == ["Autumn Release"]

    def test_naming_schemes_other_than_the_original_are_supported(self, collector):
        # The original matcher was `R(\d{2})-(\d{2})`: literal R, both widths
        # fixed. Every other site silently got a one-element list.
        assert collector._generate_release_sequence("REL-25", 2) == ["REL-25", "REL-24"]
        assert collector._generate_release_sequence("Release42", 2) == ["Release42", "Release41"]
        assert collector._generate_release_sequence("v9", 2) == ["v9", "v8"]

    def test_none_is_tolerated(self, collector):
        assert collector._generate_release_sequence(None, 2) == [None]


class TestSeverityField:
    """Regression: SEVERITY_FIELD holds the bare numeric id because JQL's
    cf[NNNNN] syntax needs it, but the REST attribute is customfield_NNNNN.
    Reading the bare id off the issue always missed, so every defect was
    reported as severity 'Unknown'."""

    def test_bare_id_reads_the_customfield_attribute(self, collector, monkeypatch):
        monkeypatch.setattr(Config, "SEVERITY_FIELD", "99999")
        issue = make_issue(customfield_99999="S1")
        assert collector._severity_of(issue) == "S1"

    def test_full_attribute_name_also_works(self, collector, monkeypatch):
        monkeypatch.setattr(Config, "SEVERITY_FIELD", "customfield_99999")
        assert collector._severity_of(make_issue(customfield_99999="S2")) == "S2"

    def test_select_list_objects_are_unwrapped(self, collector, monkeypatch):
        """Jira returns select fields as objects, not strings; str() on one
        gives a repr that is useless in a report."""
        monkeypatch.setattr(Config, "SEVERITY_FIELD", "99999")
        option = types.SimpleNamespace(value="Blocker")
        assert collector._severity_of(make_issue(customfield_99999=option)) == "Blocker"

    def test_unset_field_is_unknown(self, collector, monkeypatch):
        monkeypatch.setattr(Config, "SEVERITY_FIELD", "")
        assert collector._severity_of(make_issue()) == "Unknown"

    def test_absent_value_is_unknown(self, collector, monkeypatch):
        monkeypatch.setattr(Config, "SEVERITY_FIELD", "99999")
        assert collector._severity_of(make_issue(customfield_99999=None)) == "Unknown"


class TestQueryFailures:
    def test_a_failed_query_raises_instead_of_returning_no_defects(self, collector, monkeypatch):
        """Regression: the exception handler returned an empty DataFrame, so a
        bad credential was indistinguishable from a clean release."""
        monkeypatch.setattr(Config, "SEVERITY_FIELD", "")
        monkeypatch.setattr(Config, "DEFECT_ISSUE_TYPES", ["Bug"])

        def boom(*args, **kwargs):
            raise ConnectionError("401 Unauthorized")

        collector.jira = types.SimpleNamespace(search_issues=boom)
        with pytest.raises(RuntimeError, match="JIRA query failed"):
            collector.get_defects_quick("REL-25")

    def test_the_original_error_is_preserved(self, collector, monkeypatch):
        monkeypatch.setattr(Config, "SEVERITY_FIELD", "")
        monkeypatch.setattr(Config, "DEFECT_ISSUE_TYPES", ["Bug"])
        collector.jira = types.SimpleNamespace(
            search_issues=lambda *a, **k: (_ for _ in ()).throw(ConnectionError("401"))
        )
        with pytest.raises(RuntimeError) as excinfo:
            collector.get_defects_quick("REL-25")
        assert isinstance(excinfo.value.__cause__, ConnectionError)

    def test_missing_release_raises_rather_than_querying_everything(self, collector, monkeypatch):
        monkeypatch.setattr(Config, "CURRENT_RELEASE", "")
        with pytest.raises(ValueError, match="No release specified"):
            collector.get_defects_quick()
