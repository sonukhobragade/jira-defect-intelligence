# jira_client.py
import os
import pandas as pd
from jira import JIRA
from datetime import datetime
import re
from config import Config

def _jql_string(value) -> str:
    """
    Quote a value for use as a JQL string literal.

    JQL escapes with a backslash, so a backslash must be doubled first.
    """
    escaped = str(value).replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def count_reopens(issue, is_resolved=None) -> int:
    """
    Count how many times an issue went from a finished status back to an
    unfinished one.

    The changelog was already being fetched — every query asks for
    `expand='changelog'` — and then never looked at. This reads it.

    A reopen is the signal worth having in defect data: it means the fix did
    not work, or the defect was never understood. An issue closed once and an
    issue closed four times look identical in every count-based metric, and
    they are not the same defect at all.
    """
    if is_resolved is None:
        is_resolved = Config.is_resolved_status

    changelog = getattr(issue, "changelog", None)
    if changelog is None:
        return 0

    reopens = 0
    for history in getattr(changelog, "histories", []) or []:
        for item in getattr(history, "items", []) or []:
            if getattr(item, "field", "") != "status":
                continue
            was_finished = is_resolved(getattr(item, "fromString", None))
            now_finished = is_resolved(getattr(item, "toString", None))
            if was_finished and not now_finished:
                reopens += 1
    return reopens


def reporting_quality(defect: dict) -> dict:
    """
    Score how well a defect was written up.

    Not a judgement of the person: a defect with no description and no
    component costs triage time before anyone can start on it, and the pattern
    across a team is the actionable part.

    Each check is worth one point. The absent ones are named so the result
    says what to fix rather than only that something is wrong.
    """
    checks = {
        "has_description": bool((defect.get("description") or "").strip()),
        "description_is_substantial": len((defect.get("description") or "").strip()) >= 60,
        "has_components": bool(defect.get("components")),
        "has_priority": bool(defect.get("priority")),
        "has_assignee": defect.get("assignee") not in (None, "", "Unassigned"),
        "summary_is_specific": len((defect.get("summary") or "").strip()) >= 15,
    }
    score = sum(1 for passed in checks.values() if passed)
    return {
        "quality_score": round(score / len(checks) * 100, 1),
        "missing": [name for name, passed in checks.items() if not passed],
    }


class QuickJiraCollector:
    def __init__(self):
        self.jira = JIRA(
            server=Config.JIRA_SERVER,
            basic_auth=(Config.JIRA_USERNAME, Config.JIRA_API_KEY)
        )
        
    def _search_all(self, jql, page_size: int = 100, hard_cap: int = 20000):
        """
        Run a JQL search and follow the pages.

        The previous call asked for maxResults=1000 and stopped there. Jira
        caps a single response anyway, so a release with more defects than the
        page size came back truncated with nothing to indicate it: every
        denominator downstream — escape rate, resolution rate, project health —
        was computed against a subset while claiming to describe the release.

        hard_cap is a runaway guard, and reaching it prints rather than
        returning quietly.
        """
        issues = []
        start_at = 0

        while True:
            page = self.jira.search_issues(
                jql, startAt=start_at, maxResults=page_size, expand='changelog'
            )
            issues.extend(page)

            if len(page) < page_size:
                break

            start_at += len(page)
            if start_at >= hard_cap:
                print(f"⚠️ Stopped at {hard_cap} issues. The result is TRUNCATED "
                      f"and every rate computed from it describes a subset.")
                break

        return issues

    def get_defects_quick(self, release_version=None):
        """Get all defects for a release, across every project.

        The issue types and the severity ordering field are configuration: a
        Jira site's issue-type scheme and custom-field ids are local to that
        site, so hardcoding one site's taxonomy makes this work nowhere else.
        """
        release = release_version or Config.CURRENT_RELEASE
        if not release:
            raise ValueError(
                "No release specified. Pass release_version or set CURRENT_RELEASE."
            )

        issue_types = ", ".join(f'"{t}"' for t in Config.DEFECT_ISSUE_TYPES)
        order_by = (
            f"cf[{Config.SEVERITY_FIELD}] ASC, created DESC"
            if Config.SEVERITY_FIELD
            else "created DESC"
        )
        # Quoted and escaped. Interpolated bare, an ordinary release name with
        # a space ("R1 25") produced invalid JQL, and one containing a quote
        # could change the query rather than fail it.
        jql = f'''
        issuetype IN ({issue_types})
        AND affectedversion = {_jql_string(release)}
        ORDER BY {order_by}
        '''

        print(f"Executing cross-project query: {jql}")

        try:
            issues = self._search_all(jql)
            defects = []
            
            for issue in issues:
                defect = {
                    'key': issue.key,
                    'project': issue.fields.project.key,  # Added project identification
                    'project_name': issue.fields.project.name,
                    'summary': issue.fields.summary,
                    'issue_type': issue.fields.issuetype.name,
                    'priority': issue.fields.priority.name if issue.fields.priority else 'Medium',
                    'status': issue.fields.status.name,
                    'created': issue.fields.created,
                    'updated': issue.fields.updated,
                    'resolved': issue.fields.resolved,
                    'reporter': issue.fields.reporter.displayName if issue.fields.reporter else 'Unknown',
                    'assignee': issue.fields.assignee.displayName if issue.fields.assignee else 'Unassigned',
                    'severity': self._severity_of(issue),
                    'description': issue.fields.description or '',
                    'components': [c.name for c in (issue.fields.components or [])],
                    'labels': issue.fields.labels or [],
                    'affected_version': release,
                    # Read from the changelog this query already pays to fetch.
                    'reopen_count': count_reopens(issue),
                    'resolution_time_hours': self._calc_resolution_time(issue),
                    'age_days': self._calc_age_days(issue)
                }
                defects.append(defect)
            
            df = pd.DataFrame(defects)
            print(f"✅ Found {len(df)} defects across {df['project'].nunique() if not df.empty else 0} projects")
            
            if not df.empty:
                print("📊 Project breakdown:")
                project_counts = df['project'].value_counts()
                for project, count in project_counts.head(10).items():
                    print(f"  • {project}: {count} defects")
            
            return df
            
        except Exception as e:
            # Do not return an empty DataFrame here. "the query failed" and
            # "this release has no defects" would then look identical, and a
            # broken credential would be reported as a clean release.
            raise RuntimeError(f"JIRA query failed for release {release}: {e}") from e
    
    def get_release_comparison(self, current_release=None, previous_releases=2):
        """Compare current release with previous releases"""
        current = current_release or Config.CURRENT_RELEASE
        
        # Generate previous release versions by decrementing the trailing number.
        releases = self._generate_release_sequence(current, previous_releases + 1)
        
        all_data = []
        for release in releases:
            print(f"🔍 Analyzing release: {release}")
            df = self.get_defects_quick(release)
            if not df.empty:
                all_data.append(df)
        
        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            return combined_df
        else:
            return pd.DataFrame()
    
    # Releases per year, used only when a two-part identifier rolls over.
    RELEASES_PER_YEAR = int(os.getenv('RELEASES_PER_YEAR', '52'))

    def _generate_release_sequence(self, current_release, count):
        """
        Generate this release and the ones before it, newest first.

        The previous implementation matched a fixed `R<yy>-<nn>` shape — one
        organisation's naming, with the R and both field widths fixed. Every
        other site fell into the "unrecognised" branch and silently got a
        one-element list back, so "compare against previous releases" compared
        against nothing and said so nowhere.

        Two shapes are understood now:

        * ``<prefix><major>-<minor>``  e.g. REL-25, SPRINT-3-14, 2026-04
          The minor part counts down and rolls over into the major.
        * ``<prefix><number>``         e.g. Release42, v9, 2026.1
          The trailing number counts down.

        Anything else comes back as a single-element list, which is honest:
        there is no way to guess the predecessor of "Autumn Release".
        """
        if not current_release:
            # Deliberately [current_release], not []. An empty list makes the
            # caller's loop do nothing without saying so; this reaches
            # get_defects_quick, which raises "No release specified".
            return [current_release]

        try:
            two_part = re.match(r'^(?P<prefix>.*?)(?P<major>\d+)-(?P<minor>\d+)$',
                                str(current_release))
            if two_part:
                prefix = two_part.group('prefix')
                major_text, minor_text = two_part.group('major'), two_part.group('minor')
                major, minor = int(major_text), int(minor_text)
                releases = []
                for _ in range(count):
                    if minor <= 0:
                        major -= 1
                        minor += self.RELEASES_PER_YEAR
                    releases.append(
                        f"{prefix}{major:0{len(major_text)}d}-{minor:0{len(minor_text)}d}"
                    )
                    minor -= 1
                return releases

            one_part = re.match(r'^(?P<prefix>.*?)(?P<number>\d+)$', str(current_release))
            if one_part:
                prefix = one_part.group('prefix')
                number_text = one_part.group('number')
                number = int(number_text)
                releases = []
                for _ in range(count):
                    if number < 0:
                        break
                    releases.append(f"{prefix}{number:0{len(number_text)}d}")
                    number -= 1
                return releases

            return [current_release]
        except (ValueError, TypeError, IndexError):
            return [current_release]

    @staticmethod
    def _severity_of(issue):
        """Read the configured severity field off an issue.

        SEVERITY_FIELD is the bare numeric id because that is what JQL's
        cf[NNNNN] syntax takes, but the REST field is named
        customfield_NNNNN. Reading the bare id off issue.fields always missed
        and every defect came back 'Unknown'.
        """
        field = (Config.SEVERITY_FIELD or "").strip()
        if not field:
            return 'Unknown'
        attr = field if field.startswith('customfield_') else f'customfield_{field}'
        value = getattr(issue.fields, attr, None)
        if value is None:
            return 'Unknown'
        # Jira returns select-list fields as objects carrying a display value.
        return getattr(value, 'value', None) or getattr(value, 'name', None) or str(value)

    def _calc_resolution_time(self, issue):
        """Calculate resolution time in hours"""
        if issue.fields.resolved and issue.fields.created:
            created = datetime.strptime(issue.fields.created[:19], '%Y-%m-%dT%H:%M:%S')
            resolved = datetime.strptime(issue.fields.resolved[:19], '%Y-%m-%dT%H:%M:%S')
            return (resolved - created).total_seconds() / 3600
        return None
    
    def _calc_age_days(self, issue):
        """Calculate age in days"""
        created = datetime.strptime(issue.fields.created[:19], '%Y-%m-%dT%H:%M:%S')
        return (datetime.now() - created).days