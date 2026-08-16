# analyzer.py - Updated for cross-project analysis
from config import Config

class QuickDefectAnalyzer:
    def __init__(self):
        pass
    
    def analyze_defects(self, df):
        """Enhanced analysis for cross-project defects"""
        if df.empty:
            return {"error": "No data to analyze"}
        
        analysis = {
            'summary': self._get_summary_stats(df),
            'project_breakdown': self._analyze_by_project(df),
            'priorities': self._analyze_priorities(df),
            'issue_types': self._analyze_issue_types(df),
            'custom_field': self._analyze_custom_field(df),
            'aging': self._analyze_aging(df),
            'cross_project_insights': self._get_cross_project_insights(df),
            'top_risks': self._identify_top_risks(df),
            'recommendations': self._generate_recommendations(df)
        }
        
        return analysis
    
    def _analyze_by_project(self, df):
        """Analyze defects by project"""
        if 'project' not in df.columns:
            return {}
        
        project_analysis = {}
        for project in df['project'].unique():
            project_df = df[df['project'] == project]
            project_analysis[project] = {
                'total_defects': len(project_df),
                'open_defects': len(project_df[~project_df['status'].map(Config.is_resolved_status)]),
                'critical_defects': len(project_df[project_df['issue_type'].isin(Config.CRITICAL_ISSUE_TYPES)]),
                'avg_age': project_df['age_days'].mean(),
                'top_issue_type': project_df['issue_type'].mode().iloc[0] if not project_df.empty else 'N/A'
            }
        
        return project_analysis
    
    def _get_cross_project_insights(self, df):
        """Get insights across projects"""
        if 'project' not in df.columns or df.empty:
            return {}
        
        insights = {
            'total_projects_affected': df['project'].nunique(),
            'most_affected_project': df['project'].value_counts().index[0],
            'projects_with_critical_bugs': len(df[df['issue_type'].isin(Config.CRITICAL_ISSUE_TYPES)]['project'].unique()),
            'avg_defects_per_project': df.groupby('project').size().mean(),
            'projects_with_old_bugs': len(df[(df['age_days'] > 30) & ~df['status'].map(Config.is_resolved_status)]['project'].unique())
        }
        
        return insights
    
    def _get_summary_stats(self, df):
        return {
            'total_defects': len(df),
            'projects_affected': df['project'].nunique() if 'project' in df.columns else 1,
            'open_defects': len(df[~df['status'].map(Config.is_resolved_status)]),
            'avg_age_days': round(df['age_days'].mean(), 1) if not df.empty else None,
            # As a percentage (0-100), matching DefectAnalyzer. The dashboard
            # read this key and it was never returned, so it rendered "NaN%".
            'resolution_rate': (
                round(df['status'].map(Config.is_resolved_status).mean() * 100, 1)
                if not df.empty else None
            ),
            'critical_count': len(df[df['issue_type'].isin(Config.CRITICAL_ISSUE_TYPES)]),
            'high_priority_count': len(df[df['priority'] == 'High']),
            'current_release': df['affected_version'].iloc[0] if not df.empty else 'Unknown'
        }
    
    def _generate_recommendations(self, df):
        """Enhanced recommendations for cross-project analysis"""
        recommendations = []
        
        # Cross-project critical bug analysis
        if 'project' in df.columns:
            critical_by_project = df[df['issue_type'].isin(Config.CRITICAL_ISSUE_TYPES)].groupby('project').size()
            if not critical_by_project.empty:
                worst_project = critical_by_project.idxmax()
                recommendations.append({
                    'type': 'cross_project_critical',
                    'message': f"Project '{worst_project}' has {critical_by_project[worst_project]} critical bugs",
                    'action': f"Focus QA efforts on {worst_project} project",
                    'count': critical_by_project[worst_project]
                })
        
        # Overall aging analysis
        old_open = df[(df['age_days'] > 14) & ~df['status'].map(Config.is_resolved_status)]
        if not old_open.empty:
            recommendations.append({
                'type': 'aging_defects',
                'message': f"{len(old_open)} defects across all projects are older than 14 days",
                'action': "Review and prioritize old defects across all projects",
                'count': len(old_open)
            })
        
        # Custom field analysis
        if 'severity' in df.columns:
            high_risk_cf = df[df['severity'] != 'Unknown']['severity'].value_counts()
            if not high_risk_cf.empty:
                recommendations.append({
                    'type': 'custom_field_pattern',
                    'message': f"Most common severity value: {high_risk_cf.index[0]} ({high_risk_cf.iloc[0]} defects)",
                    'action': f"Investigate pattern in severity = {high_risk_cf.index[0]}",
                    'count': high_risk_cf.iloc[0]
                })
        
        return recommendations
    # ------------------------------------------------------------------
    # The five analyses below were named in analyze_defects() but never
    # implemented, so any non-empty DataFrame raised AttributeError and the
    # whole CLI path in main.py failed. They deliberately mirror the shapes
    # DefectAnalyzer produces, so both analysers can feed the same report.
    # ------------------------------------------------------------------

    AGE_BUCKETS = {
        '0-7 days':   (0, 7),
        '8-14 days':  (8, 14),
        '15-30 days': (15, 30),
        '31-60 days': (31, 60),
        '61-90 days': (61, 90),
        '90+ days':   (91, float('inf')),
    }

    def _analyze_priorities(self, df):
        """Defect counts per priority, highest first."""
        if 'priority' not in df.columns:
            return {}
        return df['priority'].value_counts().to_dict()

    def _analyze_issue_types(self, df):
        """Defect counts per Jira issue type."""
        if 'issue_type' not in df.columns:
            return {}
        return df['issue_type'].value_counts().to_dict()

    def _analyze_custom_field(self, df):
        """Distribution of the configured severity field.

        'Unknown' is reported alongside the real values rather than dropped:
        a high Unknown count usually means SEVERITY_FIELD is unset or wrong,
        and hiding it makes that look like clean data.
        """
        if 'severity' not in df.columns:
            return {}
        counts = df['severity'].value_counts().to_dict()
        known = {k: v for k, v in counts.items() if k != 'Unknown'}
        return {
            'distribution': counts,
            'unknown_count': int(counts.get('Unknown', 0)),
            'most_common': next(iter(known), None),
        }

    def _analyze_aging(self, df):
        """Age buckets overall, plus the oldest defect still open."""
        if 'age_days' not in df.columns:
            return {}

        distribution = {
            bucket: int(((df['age_days'] >= lo) & (df['age_days'] <= hi)).sum())
            for bucket, (lo, hi) in self.AGE_BUCKETS.items()
        }

        open_df = df[~df['status'].map(Config.is_resolved_status)] if 'status' in df.columns else df
        oldest = None
        if not open_df.empty:
            row = open_df.loc[open_df['age_days'].idxmax()]
            oldest = {
                'key': row.get('key'),
                'age_days': int(row['age_days']),
                'project': row.get('project'),
            }

        return {
            'age_distribution': distribution,
            'open_count': int(len(open_df)),
            'oldest_open_defect': oldest,
        }

    def _identify_top_risks(self, df, limit=25):
        """Rank defects by a transparent risk score.

        Deliberately arithmetic rather than learned: this analyser has no
        trained model, and an unexplainable score in a triage report gets
        ignored. Critical type and age dominate; anything already resolved
        loses the open-defect weight.
        """
        if df.empty or 'age_days' not in df.columns:
            return []

        scored = df.copy()
        is_critical = (
            scored['issue_type'].isin(Config.CRITICAL_ISSUE_TYPES)
            if 'issue_type' in scored.columns
            else False
        )
        is_high = scored['priority'] == 'High' if 'priority' in scored.columns else False
        is_open = ~scored['status'].map(Config.is_resolved_status) if 'status' in scored.columns else True

        age_factor = (scored['age_days'] / 30).clip(lower=0, upper=1)

        scored['risk_score'] = (
            (is_critical * 0.3)
            + (is_high * 0.2)
            + (age_factor * 0.3)
            + (is_open * 0.2)
        ).round(3)

        columns = [c for c in ('key', 'project', 'summary', 'issue_type',
                               'priority', 'age_days', 'status', 'assignee',
                               'risk_score') if c in scored.columns]
        return scored.nlargest(min(limit, len(scored)), 'risk_score')[columns].to_dict('records')
