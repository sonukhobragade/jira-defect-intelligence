"""
Tests for query construction and result completeness.

Both defects here are invisible on small data and wrong on real data, which is
the worst combination: they pass every manual check during development and
silently corrupt every metric in production.

- The release name was interpolated into JQL bare, so an ordinary name with a
  space produced invalid JQL and one containing a quote could alter the query.
- The search asked for 1000 results and stopped, with nothing to say the answer
  was truncated. Every rate computed downstream then described a subset while
  claiming to describe the release.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from jira_client import QuickJiraCollector, _jql_string


class TestJqlQuoting:
    def test_a_plain_name_is_quoted(self):
        assert _jql_string("R1-25") == '"R1-25"'

    def test_a_name_with_spaces_survives(self):
        # Bare interpolation of this produced invalid JQL and the query failed
        # outright, which at least was visible. The next case was not.
        assert _jql_string("Release 1 2025") == '"Release 1 2025"'

    def test_an_embedded_quote_is_escaped(self):
        assert _jql_string('R1" OR project = "X') == '"R1\\" OR project = \\"X"'

    def test_a_backslash_is_doubled_before_quotes_are_escaped(self):
        """Order matters: escaping quotes first and backslashes second would
        undo the quote escaping."""
        assert _jql_string('a\\b') == '"a\\\\b"'

    @pytest.mark.parametrize("value", [1, 2.5, None])
    def test_non_string_values_do_not_raise(self, value):
        assert _jql_string(value).startswith('"')


class TestPagination:
    """`get_defects_quick` documents itself as fetching all defects for a
    release."""

    def collector_returning(self, pages):
        collector = QuickJiraCollector.__new__(QuickJiraCollector)
        collector.jira = MagicMock()
        collector.jira.search_issues.side_effect = pages
        return collector

    def test_every_page_is_followed(self):
        page_size = 100
        pages = [
            [MagicMock() for _ in range(page_size)],
            [MagicMock() for _ in range(page_size)],
            [MagicMock() for _ in range(17)],
        ]
        collector = self.collector_returning(pages)

        issues = collector._search_all("issuetype = Bug", page_size=page_size)

        assert len(issues) == 217
        assert collector.jira.search_issues.call_count == 3

    def test_it_starts_where_the_last_page_ended(self):
        page_size = 100
        collector = self.collector_returning([
            [MagicMock() for _ in range(page_size)],
            [MagicMock() for _ in range(3)],
        ])

        collector._search_all("issuetype = Bug", page_size=page_size)

        starts = [c.kwargs["startAt"] for c in collector.jira.search_issues.call_args_list]
        assert starts == [0, 100]

    def test_a_short_first_page_stops_immediately(self):
        collector = self.collector_returning([[MagicMock() for _ in range(4)]])
        assert len(collector._search_all("issuetype = Bug", page_size=100)) == 4
        assert collector.jira.search_issues.call_count == 1

    def test_an_empty_result_is_not_an_error(self):
        collector = self.collector_returning([[]])
        assert collector._search_all("issuetype = Bug", page_size=100) == []

    def test_the_runaway_guard_announces_truncation(self, capsys):
        """If the cap is ever reached the result IS incomplete, and staying
        quiet about it is how a subset gets reported as a release."""
        page_size = 10
        collector = QuickJiraCollector.__new__(QuickJiraCollector)
        collector.jira = MagicMock()
        collector.jira.search_issues.return_value = [MagicMock() for _ in range(page_size)]

        collector._search_all("issuetype = Bug", page_size=page_size, hard_cap=30)

        assert "TRUNCATED" in capsys.readouterr().out
