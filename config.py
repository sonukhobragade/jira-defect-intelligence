# config.py
import os
from dotenv import load_dotenv

load_dotenv(override=True)

class Config:
    JIRA_SERVER = os.getenv('JIRA_SERVER', 'https://your-company.atlassian.net')
    JIRA_USERNAME = os.getenv('JIRA_USERNAME')
    JIRA_API_KEY = os.getenv('JIRA_API_KEY')
    CURRENT_RELEASE = os.getenv('CURRENT_RELEASE', '')

    # Jira custom fields, as name -> customfield_NNNNN. These ids are assigned
    # per Jira site, so there is no sensible default: read them from your own
    # instance (Settings -> Issues -> Custom fields) and set CUSTOM_FIELDS as
    # "app_version=customfield_NNNNN,os_version=customfield_NNNNN".
    CUSTOM_FIELDS = {
        pair.split('=', 1)[0].strip(): pair.split('=', 1)[1].strip()
        for pair in os.getenv('CUSTOM_FIELDS', '').split(',')
        if '=' in pair
    }

    # Ordering field for severity, if your site has one. Bare id, e.g. 99999.
    SEVERITY_FIELD = os.getenv('SEVERITY_FIELD', '')

    # Issue types that count as a defect. Jira issue-type schemes are per-site,
    # so this is configuration rather than a fixed list.
    DEFECT_ISSUE_TYPES = [
        t.strip() for t in os.getenv('DEFECT_ISSUE_TYPES', 'Bug').split(',') if t.strip()
    ]

    # Subset of the above treated as critical in the summaries.
    CRITICAL_ISSUE_TYPES = [
        t.strip() for t in os.getenv('CRITICAL_ISSUE_TYPES', '').split(',') if t.strip()
    ]
    DEFAULT_RELEASES = os.getenv('DEFAULT_RELEASES', CURRENT_RELEASE).split(',')
    DB_PATH = os.getenv('DB_PATH', 'defect_intelligence.db')
    # Removed PROJECT_KEYS - using affectedversion for cross-project analysis
    # Statuses that mean "this defect is finished".
    #
    # There were two definitions of this. defect_analyzer.py treated
    # Resolved/Closed/Done/Fixed as terminal, while analyzer.py compared
    # against the single literal 'Resolved', so a Closed defect counted as open
    # in one report and closed in the other, and the aging and risk figures
    # built on top of them disagreed for the same input.
    #
    # Jira workflows are per-site, so this is configuration, not a fixed list.
    RESOLVED_STATUSES = [
        s.strip() for s in os.getenv(
            'RESOLVED_STATUSES', 'Resolved,Closed,Done,Fixed'
        ).split(',') if s.strip()
    ]

    @classmethod
    def is_resolved_status(cls, status) -> bool:
        """True when a status means the defect is finished. Case-insensitive."""
        if status is None:
            return False
        return str(status).strip().lower() in {
            s.lower() for s in cls.RESOLVED_STATUSES
        }
