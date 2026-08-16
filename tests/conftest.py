"""
Shared fixtures.

The Jira SDK is not needed to exercise any of the logic under test, so the
tests build DataFrames in the shape jira_client produces and fake issue objects
rather than talking to a server.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def defects_df() -> pd.DataFrame:
    """Five defects across two projects, in the shape get_defects_quick returns.

    Deliberately mixed: resolved and open, critical and not, young and old, so
    a single fixture exercises every branch of the aggregations.
    """
    return pd.DataFrame([
        {"key": "AAA-1", "project": "AAA", "summary": "crash on launch",
         "issue_type": "Bug", "priority": "High", "status": "Open",
         "severity": "S1", "age_days": 45, "assignee": "alice",
         "affected_version": "REL-25"},
        {"key": "AAA-2", "project": "AAA", "summary": "typo",
         "issue_type": "Bug", "priority": "Low", "status": "Resolved",
         "severity": "S4", "age_days": 3, "assignee": "bob",
         "affected_version": "REL-25"},
        {"key": "AAA-3", "project": "AAA", "summary": "data loss",
         "issue_type": "Critical Bug", "priority": "High", "status": "Open",
         "severity": "S1", "age_days": 120, "assignee": "alice",
         "affected_version": "REL-25"},
        {"key": "BBB-1", "project": "BBB", "summary": "slow query",
         "issue_type": "Bug", "priority": "Medium", "status": "Open",
         "severity": "Unknown", "age_days": 10, "assignee": "carol",
         "affected_version": "REL-25"},
        {"key": "BBB-2", "project": "BBB", "summary": "regression",
         "issue_type": "Critical Bug", "priority": "Medium", "status": "Resolved",
         "severity": "S2", "age_days": 20, "assignee": "carol",
         "affected_version": "REL-25"},
    ])


@pytest.fixture
def critical_types(monkeypatch):
    """Config reads the environment at import, so patch the loaded class."""
    from config import Config
    monkeypatch.setattr(Config, "CRITICAL_ISSUE_TYPES", ["Critical Bug"])
    return ["Critical Bug"]


def make_issue(**fields):
    """A stand-in for a jira.Issue: only .fields attribute access is used."""
    return types.SimpleNamespace(fields=types.SimpleNamespace(**fields))
