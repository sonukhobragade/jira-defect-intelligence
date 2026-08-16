#!/usr/bin/env python3
"""
A mock JIRA REST server, for running this project end to end without a JIRA.

Why a server and not a stub DataFrame: the interesting code is between the API
and the DataFrame — pagination, changelog parsing, field extraction, the JQL
that gets built. Handing the analyser a ready-made frame skips exactly the part
most likely to be wrong, which is how a suite gets to be green while the tool
does not work.

This speaks enough of the JIRA REST API for the `jira` library to talk to it:

    GET /rest/api/2/serverInfo
    GET /rest/api/2/field
    GET /rest/api/2/search?jql=...&startAt=N&maxResults=M   (paginated)

The data is generated, not sampled from anywhere. Names are placeholders, and
the defect summaries describe a fictional e-commerce API.

    python scripts/mock_jira.py --port 8089
"""

from __future__ import annotations

import argparse
import json
import random
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

# Fixed seed: two runs produce the same numbers, so the figures quoted in the
# README can be reproduced rather than taken on trust.
SEED = 20260101

PROJECTS = [
    ("ORDERS", "Orders API"),
    ("BILLING", "Billing Service"),
    ("SEARCH", "Search Service"),
    ("MOBILE", "Mobile App"),
]

COMPONENTS = ["checkout", "payments", "catalogue", "auth", "notifications"]

SUMMARIES = [
    "Checkout fails when the basket contains a discounted item",
    "Duplicate charge on retried payment",
    "Search returns stale results after reindex",
    "Session expires early on slow connections",
    "Order confirmation email not sent",
    "Refund status stuck at pending",
    "Address validation rejects valid postcodes",
    "Cart total ignores currency rounding",
    "Push notification delivered twice",
    "Inventory count drifts after concurrent orders",
]

# Placeholder names. See CONTRIBUTING: no real people in fixtures.
PEOPLE = ["Alice Archer", "Bob Baker", "Carol Carter", "Dave Draper",
          "Erin Ellis", "Frank Fisher", "Grace Gardner"]

STATUSES = ["Open", "In Progress", "Resolved", "Closed", "Done"]
PRIORITIES = ["Highest", "High", "Medium", "Low"]
ISSUE_TYPES = ["Bug", "Defect"]

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _stamp(dt: datetime) -> str:
    """JIRA's timestamp format, which the client parses."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000%z")


def build_issues(count: int = 240, release: str = "REL-25") -> list[dict]:
    """Generate issues with the shape the JIRA REST API returns."""
    rng = random.Random(SEED)
    issues = []

    for n in range(1, count + 1):
        key_prefix, project_name = rng.choice(PROJECTS)
        created = NOW - timedelta(days=rng.randint(1, 180), hours=rng.randint(0, 23))
        status = rng.choices(STATUSES, weights=[15, 10, 30, 30, 15])[0]
        resolved_statuses = {"Resolved", "Closed", "Done"}
        is_resolved = status in resolved_statuses

        resolved_at = None
        if is_resolved:
            resolved_at = created + timedelta(hours=rng.randint(2, 720))
            if resolved_at > NOW:
                resolved_at = NOW - timedelta(hours=1)

        # Reopen history. About one issue in six comes back, and a few come
        # back more than once — the pattern the analysis is meant to surface.
        reopen_count = rng.choices([0, 1, 2, 3], weights=[82, 12, 4, 2])[0]
        histories = []
        cursor = created + timedelta(hours=2)
        for _ in range(reopen_count):
            histories.append({
                "created": _stamp(cursor),
                "items": [{"field": "status", "fieldtype": "jira",
                           "fromString": "In Progress", "toString": "Resolved"}],
            })
            cursor += timedelta(hours=rng.randint(4, 200))
            histories.append({
                "created": _stamp(cursor),
                "items": [{"field": "status", "fieldtype": "jira",
                           "fromString": "Resolved", "toString": "Reopened"}],
            })
            cursor += timedelta(hours=rng.randint(4, 200))
        if is_resolved:
            histories.append({
                "created": _stamp(resolved_at),
                "items": [{"field": "status", "fieldtype": "jira",
                           "fromString": "In Progress", "toString": status}],
            })

        # A quarter of issues are written up poorly: no description, no
        # component, nobody assigned. That is what reporting quality measures.
        sloppy = rng.random() < 0.25
        description = "" if sloppy else (
            "Steps to reproduce:\n1. Sign in\n2. Add two items to the basket\n"
            "3. Apply a discount code\n\nExpected: total updates. "
            "Actual: total is unchanged until the page is refreshed."
        )

        issues.append({
            "key": f"{key_prefix}-{n}",
            "fields": {
                "project": {"key": key_prefix, "name": project_name},
                "summary": rng.choice(SUMMARIES) if not sloppy else "bug",
                "issuetype": {"name": rng.choice(ISSUE_TYPES)},
                "priority": {"name": rng.choice(PRIORITIES)},
                "status": {"name": status},
                "created": _stamp(created),
                "updated": _stamp(resolved_at or NOW),
                "resolutiondate": _stamp(resolved_at) if resolved_at else None,
                "resolved": _stamp(resolved_at) if resolved_at else None,
                "reporter": {"displayName": rng.choice(PEOPLE)},
                "assignee": None if sloppy else {"displayName": rng.choice(PEOPLE)},
                "description": description,
                "components": [] if sloppy else [{"name": rng.choice(COMPONENTS)}],
                "labels": [] if sloppy else ["regression"],
                "versions": [{"name": release}],
                "fixVersions": [{"name": release}] if is_resolved else [],
                "customfield_99999": {"value": rng.choice(["S1", "S2", "S3", "S4"])},
            },
            "changelog": {"histories": histories, "total": len(histories)},
        })

    return issues


class MockJiraHandler(BaseHTTPRequestHandler):
    issues: list[dict] = []

    def _send(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        if parsed.path.endswith("/serverInfo"):
            return self._send({
                "baseUrl": f"http://{self.headers.get('Host', 'localhost')}",
                "version": "9.4.0", "versionNumbers": [9, 4, 0],
                "deploymentType": "Server", "serverTitle": "Mock JIRA",
            })

        if parsed.path.endswith("/field"):
            return self._send([
                {"id": "customfield_99999", "name": "Severity", "custom": True},
            ])

        if "/search" in parsed.path:
            start_at = int(query.get("startAt", ["0"])[0])
            max_results = int(query.get("maxResults", ["50"])[0])
            page = self.issues[start_at:start_at + max_results]
            return self._send({
                "startAt": start_at,
                "maxResults": max_results,
                "total": len(self.issues),
                "issues": page,
            })

        return self._send({"errorMessages": [f"Unhandled path {parsed.path}"]}, 404)

    def do_POST(self):  # noqa: N802
        # The client uses GET /search; POST is here so a different client
        # version does not fall over.
        return self.do_GET()

    def log_message(self, *args):
        pass  # quiet


def serve(port: int, count: int, release: str):
    MockJiraHandler.issues = build_issues(count, release)
    server = HTTPServer(("127.0.0.1", port), MockJiraHandler)
    print(f"Mock JIRA on http://127.0.0.1:{port} with {count} issues "
          f"for release {release}")
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--port", type=int, default=8089)
    parser.add_argument("--count", type=int, default=240)
    parser.add_argument("--release", default="REL-25")
    args = parser.parse_args()
    serve(args.port, args.count, args.release)
