"""
Tests for configuration parsing.

Every Jira site assigns its own custom-field ids and its own issue-type
scheme, so all of this is environment driven. A parsing slip here does not
crash: it silently produces an empty mapping, and the analysis then reports
zero critical defects on a release full of them.

Config evaluates the environment at import, so each test reloads the module.
"""

from __future__ import annotations

import importlib


def load_config(monkeypatch, **env):
    """Reload config with a controlled environment."""
    for key in ("CUSTOM_FIELDS", "SEVERITY_FIELD", "DEFECT_ISSUE_TYPES",
                "CRITICAL_ISSUE_TYPES", "CURRENT_RELEASE", "DEFAULT_RELEASES"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import config
    # override=True in load_dotenv would put a developer's .env back on top.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    return importlib.reload(config).Config


class TestCustomFields:
    def test_pairs_are_parsed(self, monkeypatch):
        cfg = load_config(
            monkeypatch,
            CUSTOM_FIELDS="app_version=customfield_101,os_version=customfield_102",
        )
        assert cfg.CUSTOM_FIELDS == {
            "app_version": "customfield_101",
            "os_version": "customfield_102",
        }

    def test_surrounding_whitespace_is_stripped(self, monkeypatch):
        cfg = load_config(monkeypatch, CUSTOM_FIELDS=" app_version = customfield_101 ")
        assert cfg.CUSTOM_FIELDS == {"app_version": "customfield_101"}

    def test_unset_gives_an_empty_mapping_not_a_crash(self, monkeypatch):
        assert load_config(monkeypatch).CUSTOM_FIELDS == {}

    def test_entries_without_an_equals_sign_are_ignored(self, monkeypatch):
        cfg = load_config(monkeypatch, CUSTOM_FIELDS="garbage,app_version=customfield_101")
        assert cfg.CUSTOM_FIELDS == {"app_version": "customfield_101"}

    def test_a_value_containing_equals_is_kept_whole(self, monkeypatch):
        cfg = load_config(monkeypatch, CUSTOM_FIELDS="odd=a=b")
        assert cfg.CUSTOM_FIELDS == {"odd": "a=b"}


class TestIssueTypes:
    def test_defect_types_default_to_bug(self, monkeypatch):
        """A site that sets nothing should still find its bugs."""
        assert load_config(monkeypatch).DEFECT_ISSUE_TYPES == ["Bug"]

    def test_defect_types_split_and_strip(self, monkeypatch):
        cfg = load_config(monkeypatch, DEFECT_ISSUE_TYPES="Bug, Defect ,Incident")
        assert cfg.DEFECT_ISSUE_TYPES == ["Bug", "Defect", "Incident"]

    def test_empty_entries_are_dropped(self, monkeypatch):
        cfg = load_config(monkeypatch, DEFECT_ISSUE_TYPES="Bug,,Defect")
        assert cfg.DEFECT_ISSUE_TYPES == ["Bug", "Defect"]

    def test_critical_types_default_to_empty(self, monkeypatch):
        """No default is correct: guessing which type is 'critical' on someone
        else's site would silently mis-rank their report."""
        assert load_config(monkeypatch).CRITICAL_ISSUE_TYPES == []


class TestSeverityField:
    def test_unset_is_empty(self, monkeypatch):
        assert load_config(monkeypatch).SEVERITY_FIELD == ""

    def test_bare_id_is_kept_as_given(self, monkeypatch):
        """JQL's cf[NNNNN] wants the bare id; the REST attribute name is
        derived from it at the point of use."""
        assert load_config(monkeypatch, SEVERITY_FIELD="99999").SEVERITY_FIELD == "99999"
