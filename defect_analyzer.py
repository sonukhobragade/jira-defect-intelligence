# defect_analyzer.py -- fetch, classify and predict across all defects
import pandas as pd
from jira import JIRA
import os
from dotenv import load_dotenv
from datetime import datetime
import numpy as np
import warnings
import time
from ml_processor import QuickDefectPredictor
from config import Config
warnings.filterwarnings('ignore')

load_dotenv(override=True)

class DefectAnalyzer:
    def __init__(self):
        self.jira_server = os.getenv('JIRA_SERVER')
        self.jira_username = os.getenv('JIRA_USERNAME')
        self.jira_api_key = os.getenv('JIRA_API_KEY')
        self.current_release = os.getenv('CURRENT_RELEASE', '')
        
        print("🚀 DEFECT INTELLIGENCE")
        print(f"   Release: {self.current_release}")
        print(f"   Server: {self.jira_server}")
        print("   Mode: ANALYZE ALL BUGS")
        
        self.jira = JIRA(
            server=self.jira_server,
            basic_auth=(self.jira_username, self.jira_api_key)
        )
        
        # Initialize the ML predictor from ml_processor.py
        self.ml_predictor = QuickDefectPredictor()
        self.encoders = {}
        
    def get_all_release_defects(self, release_version=None):
        """Get ALL defects for the release (no limits)"""
        release = release_version or self.current_release

        # Issue types are configuration: a Jira site's issue-type scheme is
        # local to that site.
        issue_types = ", ".join(f'"{t}"' for t in Config.DEFECT_ISSUE_TYPES)
        jql = f'''
        issuetype IN ({issue_types})
        AND affectedVersion = "{release}" 
        ORDER BY created DESC
        '''
        
        print(f"\n🔍 Fetching ALL defects for {release}...")
        print(f"Query: {jql}")
        print("⏳ This may take a few minutes for large datasets...")
        
        try:
            # First, get the total count
            search_result = self.jira.search_issues(jql, maxResults=1)
            total_issues = search_result.total
            print(f"📊 Found {total_issues} total defects to analyze!")
            
            if total_issues == 0:
                print("❌ No defects found!")
                return pd.DataFrame()
            
            # Fetch all issues in batches
            all_issues = []
            batch_size = 100  # JIRA's recommended batch size
            
            for start_at in range(0, total_issues, batch_size):
                batch_num = (start_at // batch_size) + 1
                total_batches = (total_issues // batch_size) + 1
                
                print(f"📦 Fetching batch {batch_num}/{total_batches} ({start_at+1}-{min(start_at+batch_size, total_issues)})")
                
                batch_issues = self.jira.search_issues(
                    jql, 
                    startAt=start_at, 
                    maxResults=batch_size,
                    expand='changelog'
                )
                
                all_issues.extend(batch_issues)
                
                # Small delay to be nice to the JIRA server
                time.sleep(0.5)
            
            print(f"✅ Successfully fetched {len(all_issues)} defects!")
            
            # Extract data from all issues
            defects = []
            error_count = 0
            
            print("🔧 Extracting defect details...")
            
            for i, issue in enumerate(all_issues):
                try:
                    defect_data = self.extract_defect_details_safe(issue)
                    if defect_data and 'error' not in defect_data:
                        defects.append(defect_data)
                    else:
                        # extract_defect_details_safe swallows its own
                        # exceptions and returns None, so a dropped defect
                        # reached neither the frame nor the error count. It
                        # simply left the denominator, and a release with
                        # malformed fields looked cleaner than it was.
                        error_count += 1
                        if error_count <= 10:
                            print(f"⚠️ Skipped {getattr(issue, 'key', '<unknown>')}: "
                                  f"could not extract fields")

                    # Progress indicator
                    if (i + 1) % 50 == 0:
                        print(f"   Processed {i+1}/{len(all_issues)} issues...")
                        
                except Exception as e:
                    error_count += 1
                    if error_count <= 10:  # Show first 10 errors
                        print(f"⚠️ Error extracting {issue.key}: {e}")
            
            if error_count > 10:
                print(f"⚠️ ... and {error_count - 10} more extraction errors")
            
            if not defects:
                print("❌ No valid defects extracted!")
                return pd.DataFrame()
            
            df = pd.DataFrame(defects)
            print(f"📊 Successfully extracted {len(df)} defects across {df['project'].nunique()} projects")
            if all_issues:
                rate = len(df) / len(all_issues) * 100
                print(f"📈 Data extraction success rate: {rate:.1f}%")
                if len(df) < len(all_issues):
                    # Say it plainly. Every rate below is computed against the
                    # defects that survived extraction, not the ones that exist.
                    print(f"⚠️ {len(all_issues) - len(df)} of {len(all_issues)} issues "
                          f"were dropped. Metrics below describe the remainder.")
            
            return df
            
        except Exception as e:
            print(f"❌ Error fetching defects: {e}")
            return pd.DataFrame()
    
    def extract_defect_details_safe(self, issue):
        """Safely extract comprehensive defect details"""
        try:
            # Basic fields with safe access
            defect = {
                'key': issue.key,
                'project': self.safe_get(issue.fields, 'project.key', 'Unknown'),
                'project_name': self.safe_get(issue.fields, 'project.name', 'Unknown'),
                'summary': self.safe_get(issue.fields, 'summary', 'No summary'),
                'description': self.safe_get(issue.fields, 'description', ''),
                'issue_type': self.safe_get(issue.fields, 'issuetype.name', 'Unknown'),
                'status': self.safe_get(issue.fields, 'status.name', 'Unknown'),
                'priority': self.safe_get(issue.fields, 'priority.name', 'Medium'),
            }
            
            # Handle resolution safely
            resolution = getattr(issue.fields, 'resolution', None)
            defect['resolution'] = resolution.name if resolution else None
            
            # Handle people safely
            reporter = getattr(issue.fields, 'reporter', None)
            defect['reporter'] = reporter.displayName if reporter else 'Unknown'
            
            assignee = getattr(issue.fields, 'assignee', None)
            defect['assignee'] = assignee.displayName if assignee else 'Unassigned'
            
            # Handle dates safely
            defect['created'] = getattr(issue.fields, 'created', None)
            defect['updated'] = getattr(issue.fields, 'updated', None)
            defect['resolved'] = getattr(issue.fields, 'resolutiondate', None)
            
            # Custom field ids are assigned per Jira site, so an id from one
            # instance means nothing on another. Map your own in
            # config.CUSTOM_FIELDS (see .env.example) rather than hardcoding
            # another site's ids here.
            for name, field_id in Config.CUSTOM_FIELDS.items():
                defect[name] = getattr(issue.fields, field_id, None)
            
            # Handle arrays safely
            components = getattr(issue.fields, 'components', [])
            defect['components'] = [c.name for c in components] if components else []
            defect['components_str'] = ', '.join(defect['components'])
            
            labels = getattr(issue.fields, 'labels', [])
            defect['labels'] = labels if labels else []
            defect['labels_str'] = ', '.join(labels) if labels else ''
            
            versions = getattr(issue.fields, 'versions', [])
            defect['affected_versions'] = [v.name for v in versions] if versions else []
            defect['affected_versions_str'] = ', '.join(defect['affected_versions'])
            
            fix_versions = getattr(issue.fields, 'fixVersions', [])
            defect['fix_versions'] = [v.name for v in fix_versions] if fix_versions else []
            defect['fix_versions_str'] = ', '.join(defect['fix_versions'])
            
            # Calculated fields
            defect['age_days'] = self.calculate_age_days_safe(defect['created'])
            defect['resolution_time_hours'] = self.calculate_resolution_time_safe(defect['created'], defect['resolved'])
            defect['is_resolved'] = Config.is_resolved_status(defect['status'])
            defect['is_critical'] = defect['issue_type'] in Config.CRITICAL_ISSUE_TYPES
            defect['is_open'] = defect['status'] in ['Open', 'In Progress', 'Reopened', 'To Do']
            defect['summary_length'] = len(defect['summary'])
            defect['has_description'] = bool(defect['description'])
            defect['description_length'] = len(defect['description'])
            defect['has_assignee'] = defect['assignee'] != 'Unassigned'
            defect['has_components'] = len(defect['components']) > 0
            defect['has_labels'] = len(defect['labels']) > 0
            
            # Week/month categorization for trending
            if defect['created']:
                created_dt = datetime.strptime(str(defect['created'])[:19], '%Y-%m-%dT%H:%M:%S')
                defect['created_week'] = created_dt.strftime('%Y-W%U')
                defect['created_month'] = created_dt.strftime('%Y-%m')
                defect['created_day'] = created_dt.strftime('%Y-%m-%d')
            else:
                defect['created_week'] = 'Unknown'
                defect['created_month'] = 'Unknown'
                defect['created_day'] = 'Unknown'
            
            return defect
            
        except Exception:
            return None
    
    def safe_get(self, obj, path, default=None):
        """Safely get nested attributes"""
        try:
            attrs = path.split('.')
            result = obj
            for attr in attrs:
                result = getattr(result, attr)
            return result if result is not None else default
        except AttributeError:
            # A missing attribute in the chain is the expected miss. A bare
            # except also caught KeyboardInterrupt and MemoryError.
            return default
    
    def calculate_age_days_safe(self, created_date):
        """Safely calculate age in days"""
        try:
            if not created_date:
                return 0
            created = datetime.strptime(str(created_date)[:19], '%Y-%m-%dT%H:%M:%S')
            return (datetime.now() - created).days
        except (ValueError, TypeError):
            # Unparseable or non-string date.
            return 0
    
    def calculate_resolution_time_safe(self, created_date, resolved_date):
        """Safely calculate resolution time in hours"""
        try:
            if not created_date or not resolved_date:
                return None
            created = datetime.strptime(str(created_date)[:19], '%Y-%m-%dT%H:%M:%S')
            resolved = datetime.strptime(str(resolved_date)[:19], '%Y-%m-%dT%H:%M:%S')
            return round((resolved - created).total_seconds() / 3600, 2)
        except (ValueError, TypeError):
            return None
    
    def comprehensive_analysis(self, df):
        """Comprehensive analysis of ALL bugs"""
        if df.empty:
            return {"error": "No defects to analyze"}
        
        print("\n📊 Performing Comprehensive Analysis...")
        
        analysis = {
            'summary': self.get_comprehensive_summary(df),
            'project_analysis': self.get_detailed_project_analysis(df),
            'severity_analysis': self.get_comprehensive_severity_analysis(df),
            'aging_analysis': self.get_detailed_aging_analysis(df),
            'trend_analysis': self.get_trend_analysis(df),
            'assignee_analysis': self.get_assignee_analysis(df),
            'component_analysis': self.get_component_analysis(df),
            'performance_metrics': self.get_performance_metrics(df),
            'top_risks': self.get_enhanced_top_risks(df),
            'recommendations': self.generate_comprehensive_recommendations(df)
        }
        
        # Add OpenAI pattern analysis for all defects
        if self.ml_predictor.openai_analyzer and self.ml_predictor.openai_analyzer.available:
            print(f"🤖 Performing OpenAI pattern analysis for all {len(df)} defects...")
            try:
                openai_analysis = self.ml_predictor.openai_analyzer.analyze_defect_patterns(df)
                if 'error' not in openai_analysis:
                    analysis['openai_insights'] = openai_analysis
                    print("✅ OpenAI pattern analysis completed successfully!")
                else:
                    print(f"⚠️ OpenAI analysis error: {openai_analysis['error']}")
            except Exception as e:
                print(f"⚠️ OpenAI analysis failed: {str(e)}")
        
        # Clean NaN values for JSON serialization
        analysis = self._clean_nan_values(analysis)
        return analysis
    
    @staticmethod
    def _safe_mean(series, ndigits=1):
        """
        Mean of a series, or None when there is nothing to average.

        pandas returns NaN for the mean of an empty series, and NaN survives
        rounding, JSON encoding and string formatting. A quality report that
        prints "Resolution Rate: nan%" is worse than one that prints nothing,
        because the reader has to work out whether it means zero or unknown.
        None says unknown.
        """
        if series is None or len(series) == 0:
            return None
        value = series.mean()
        if pd.isna(value):
            return None
        return round(float(value), ndigits)

    @classmethod
    def _safe_percentage(cls, series, ndigits=1):
        """Percentage of True values, or None when the set is empty."""
        mean = cls._safe_mean(series, ndigits=6)
        return None if mean is None else round(mean * 100, ndigits)

    def get_comprehensive_summary(self, df):
        """Enhanced summary statistics"""
        resolved_df = df[df['is_resolved']]
        open_df = df[~df['is_resolved']]

        # Every average below is guarded. On an empty result set these used to
        # come back as NaN and get printed into the report as "nan%".
        return {
            'total_defects': len(df),
            'projects_affected': df['project'].nunique(),
            'open_defects': len(open_df),
            'resolved_defects': len(resolved_df),
            'critical_defects': len(df[df['is_critical']]),
            'critical_open': len(df[df['is_critical'] & ~df['is_resolved']]),
            'avg_age_days': self._safe_mean(df['age_days']),
            'avg_age_open': self._safe_mean(open_df['age_days']),
            'oldest_open_defect_days': int(open_df['age_days'].max()) if len(open_df) > 0 else 0,
            'resolution_rate': self._safe_percentage(df['is_resolved']),
            'avg_resolution_time_hours': (
                self._safe_mean(resolved_df['resolution_time_hours'])
                if 'resolution_time_hours' in resolved_df.columns else None
            ),
            'unassigned_count': len(df[df['assignee'] == 'Unassigned']),
            'unassigned_rate': self._safe_percentage(df['assignee'] == 'Unassigned'),
            'high_priority_count': len(df[df['priority'] == 'High']),
            'no_components_count': len(df[~df['has_components']])
        }
    
    def get_comprehensive_severity_analysis(self, df):
        """Analyze severity and issue types in detail"""
        # Analyze by issue type
        issue_type_counts = df['issue_type'].value_counts().to_dict()
        
        # Analyze by priority
        priority_counts = df['priority'].value_counts().to_dict()
        
        # Critical issues by project
        critical_by_project = df[df['is_critical']].groupby('project').size().to_dict()
        
        # Critical issues by component
        critical_components = []
        for components in df[df['is_critical']]['components']:
            if isinstance(components, list):
                critical_components.extend(components)
        
        critical_component_counts = {}
        if critical_components:
            critical_component_counts = pd.Series(critical_components).value_counts().head(10).to_dict()
        
        # Severity trends over time
        severity_trend = df.groupby('created_month').agg({
            'is_critical': 'mean',
            'priority': lambda x: (x == 'High').mean()
        }).tail(6).round(3)
        
        return {
            'issue_type_distribution': issue_type_counts,
            'priority_distribution': priority_counts,
            'critical_by_project': critical_by_project,
            'top_critical_components': critical_component_counts,
            'severity_trend': {
                'critical_rate': severity_trend['is_critical'].to_dict(),
                'high_priority_rate': severity_trend['priority'].to_dict()
            }
        }
        
    def get_detailed_project_analysis(self, df):
        """Comprehensive project breakdown"""
        project_stats = df.groupby('project').agg({
            'key': 'count',
            'is_resolved': lambda x: (~x).sum(),  # Open defects
            'is_critical': 'sum',
            'age_days': 'mean',
            'priority': lambda x: (x == 'High').sum(),
            'assignee': lambda x: (x == 'Unassigned').sum(),
            'resolution_time_hours': 'mean'
        }).round(2)

        project_stats.columns = [
            'total_defects', 'open_defects', 'critical_defects', 
            'avg_age_days', 'high_priority_count', 'unassigned_count', 'avg_resolution_hours'
        ]

        # Age of the OPEN defects only.
        #
        # age_days is always "now minus created", so a resolved defect keeps
        # ageing forever. Averaging it across resolved and open alike meant a
        # project that fixed everything promptly still decayed month after
        # month with no change in its data, and the health score below fell
        # with it. Only an unfixed defect gets older in any sense that matters.
        open_ages = (
            df[~df['is_resolved']].groupby('project')['age_days'].mean().round(2)
        )
        project_stats['avg_age_open_days'] = open_ages.reindex(
            project_stats.index
        ).fillna(0)

        # Add project health score
        project_stats['health_score'] = (
            (1 - project_stats['open_defects'] / project_stats['total_defects']) * 0.4 +
            (1 - project_stats['critical_defects'] / project_stats['total_defects']) * 0.3 +
            (1 - np.clip(project_stats['avg_age_open_days'] / 30, 0, 1)) * 0.3
        ).round(3)
        
        return project_stats.sort_values('health_score').to_dict('index')
    
    def get_trend_analysis(self, df):
        """Analyze trends over time"""
        # Weekly trends
        weekly_trends = df.groupby('created_week').agg({
            'key': 'count',
            'is_critical': 'sum',
            'is_resolved': 'mean'
        }).tail(12)  # Last 12 weeks
        
        # Monthly trends
        monthly_trends = df.groupby('created_month').agg({
            'key': 'count',
            'is_critical': 'sum',
            'is_resolved': 'mean'
        }).tail(6)  # Last 6 months
        
        return {
            'weekly_creation_trend': weekly_trends['key'].to_dict(),
            'weekly_critical_trend': weekly_trends['is_critical'].to_dict(),
            'monthly_creation_trend': monthly_trends['key'].to_dict(),
            'monthly_resolution_rate': monthly_trends['is_resolved'].round(3).to_dict()
        }
    
    def get_detailed_aging_analysis(self, df):
        """Detailed analysis of defect aging"""
        # Age buckets
        age_buckets = {
            '0-7 days': (0, 7),
            '8-14 days': (8, 14),
            '15-30 days': (15, 30),
            '31-60 days': (31, 60),
            '61-90 days': (61, 90),
            '90+ days': (91, float('inf'))
        }
        
        # Create age bucket categories
        age_distribution = {}
        for bucket, (min_age, max_age) in age_buckets.items():
            age_distribution[bucket] = len(df[(df['age_days'] >= min_age) & (df['age_days'] <= max_age)])
        
        # Age by project for open defects
        open_df = df[~df['is_resolved']]
        project_aging = {}
        
        if not open_df.empty:
            project_aging = open_df.groupby('project').agg({
                'age_days': ['mean', 'max', 'count']
            })
            project_aging.columns = ['avg_age', 'oldest_defect', 'open_count']
            project_aging = project_aging.round(1).sort_values('avg_age', ascending=False).to_dict('index')
        
        # Age by priority
        priority_aging = df.groupby('priority').agg({
            'age_days': 'mean',
            'is_resolved': lambda x: (~x).sum() / len(x)  # Percentage still open
        }).round(3)
        priority_aging.columns = ['avg_age_days', 'percent_open']
        
        # Age by issue type
        type_aging = df.groupby('issue_type').agg({
            'age_days': 'mean',
            'is_resolved': lambda x: (~x).sum() / len(x)  # Percentage still open
        }).round(3)
        type_aging.columns = ['avg_age_days', 'percent_open']
        
        return {
            'age_distribution': age_distribution,
            'project_aging': project_aging,
            'priority_aging': priority_aging.to_dict('index'),
            'issue_type_aging': type_aging.to_dict('index'),
            'oldest_open_defect': {
                'key': open_df.loc[open_df['age_days'].idxmax(), 'key'] if not open_df.empty else None,
                'age': int(open_df['age_days'].max()) if not open_df.empty else 0,
                'project': open_df.loc[open_df['age_days'].idxmax(), 'project'] if not open_df.empty else None
            }
        }
    
    def get_assignee_analysis(self, df):
        """Analyze by assignee"""
        assignee_stats = df.groupby('assignee').agg({
            'key': 'count',
            'is_resolved': lambda x: (~x).sum(),
            'is_critical': 'sum',
            'age_days': 'mean',
            'resolution_time_hours': 'mean'
        }).round(2)
        
        assignee_stats.columns = ['total_assigned', 'open_count', 'critical_count', 'avg_age', 'avg_resolution_hours']
        
        # Filter out unassigned and show top 20 by workload
        assigned_stats = assignee_stats[assignee_stats.index != 'Unassigned'].sort_values('open_count', ascending=False).head(20)
        
        return assigned_stats.to_dict('index')
    
    def get_component_analysis(self, df):
        """Analyze by component"""
        # Explode components for analysis
        component_df = df.explode('components')
        component_df = component_df[component_df['components'].notna()]
        
        if len(component_df) == 0:
            return {}
        
        component_stats = component_df.groupby('components').agg({
            'key': 'count',
            'is_resolved': lambda x: (~x).sum(),
            'is_critical': 'sum',
            'age_days': 'mean'
        }).round(2)
        
        component_stats.columns = ['total_defects', 'open_count', 'critical_count', 'avg_age']
        
        return component_stats.sort_values('open_count', ascending=False).head(15).to_dict('index')
    
    def get_performance_metrics(self, df):
        """Calculate performance metrics"""
        resolved_df = df[df['is_resolved'] & df['resolution_time_hours'].notna()]
        
        metrics = {}
        
        if len(resolved_df) > 0:
            metrics['resolution_time_percentiles'] = {
                'p50': round(resolved_df['resolution_time_hours'].quantile(0.5), 1),
                'p75': round(resolved_df['resolution_time_hours'].quantile(0.75), 1),
                'p90': round(resolved_df['resolution_time_hours'].quantile(0.9), 1),
                'p95': round(resolved_df['resolution_time_hours'].quantile(0.95), 1)
            }
        
        # SLA compliance (assuming 48 hours for critical, 168 hours for normal)
        critical_resolved = resolved_df[resolved_df['is_critical']]
        normal_resolved = resolved_df[~resolved_df['is_critical']]
        
        metrics['sla_compliance'] = {
            'critical_under_48h': round((critical_resolved['resolution_time_hours'] <= 48).mean() * 100, 1) if len(critical_resolved) > 0 else 0,
            'normal_under_168h': round((normal_resolved['resolution_time_hours'] <= 168).mean() * 100, 1) if len(normal_resolved) > 0 else 0
        }
        
        return metrics
    
    def get_enhanced_top_risks(self, df):
        """Enhanced risk analysis using ML predictor"""
        try:
            # First try to use the ML predictor
            print("🤖 Using ML predictor for risk analysis...")
            
            # Prepare data for ML prediction
            prepared_df = self.ml_predictor.prepare_data_quick(df.copy())
            
            # Train ML models if not already trained
            self.ml_predictor.train_quick_models(prepared_df)
            
            # Predict defect risks using ML model
            predicted_df = self.ml_predictor.predict_defect_risk(prepared_df)
            
            # Get top risks based on overall_risk_score from ML prediction
            if 'overall_risk_score' in predicted_df.columns:
                print("✅ ML risk prediction successful!")
                top_risks = predicted_df.nlargest(25, 'overall_risk_score')[
                    ['key', 'project', 'summary', 'issue_type', 'priority', 
                     'age_days', 'status', 'assignee', 'overall_risk_score']
                ].rename(columns={'overall_risk_score': 'risk_score'}).to_dict('records')
                
                return top_risks
            else:
                raise ValueError("ML prediction did not produce overall_risk_score column")
            
        except Exception as e:
            print(f"⚠️ Error in ML risk prediction: {str(e)}")
            print("⚠️ Falling back to basic risk calculation")
            
            # Calculate enhanced risk score using the original method
            df['risk_score'] = (
                df['is_critical'].astype(float) * 0.3 +
                (df['priority'] == 'High').astype(float) * 0.2 +
                np.clip(df['age_days'] / 30, 0, 1) * 0.3 +
                (~df['is_resolved']).astype(float) * 0.2
            )
            
            top_risks = df.nlargest(25, 'risk_score')[
                ['key', 'project', 'summary', 'issue_type', 'priority', 
                 'age_days', 'status', 'assignee', 'risk_score']
            ].to_dict('records')
            
            return top_risks
    
    def generate_comprehensive_recommendations(self, df):
        """Generate comprehensive recommendations"""
        recommendations = []
        
        # Critical open issues
        critical_open = df[df['is_critical'] & ~df['is_resolved']]
        if len(critical_open) > 0:
            recommendations.append({
                'type': 'critical_open',
                'priority': 'Critical',
                'message': f"{len(critical_open)} critical bugs are still open",
                'action': "Immediately assign and prioritize critical bugs",
                'count': len(critical_open),
                'impact': 'High'
            })
        
        # Very old open defects
        very_old_open = df[(df['age_days'] > 30) & (~df['is_resolved'])]
        if len(very_old_open) > 0:
            recommendations.append({
                'type': 'very_old_defects',
                'priority': 'High',
                'message': f"{len(very_old_open)} defects are older than 30 days",
                'action': "Review and close/fix very old defects",
                'count': len(very_old_open),
                'impact': 'Medium'
            })
        
        # Unassigned defects
        unassigned = df[(df['assignee'] == 'Unassigned') & (~df['is_resolved'])]
        if len(unassigned) > 10:
            recommendations.append({
                'type': 'unassigned_defects',
                'priority': 'Medium',
                'message': f"{len(unassigned)} open defects are unassigned",
                'action': "Assign ownership to open defects",
                'count': len(unassigned),
                'impact': 'Medium'
            })
        
        # Project with most issues
        project_counts = df[~df['is_resolved']].groupby('project').size()
        if not project_counts.empty:
            worst_project = project_counts.idxmax()
            recommendations.append({
                'type': 'project_focus',
                'priority': 'Medium',
                'message': f"Project {worst_project} has {project_counts[worst_project]} open defects",
                'action': f"Focus QA efforts on {worst_project} project",
                'count': int(project_counts[worst_project]),
                'impact': 'Medium'
            })
        
        # High priority unresolved
        high_priority_open = df[(df['priority'] == 'High') & (~df['is_resolved'])]
        if len(high_priority_open) > 0:
            recommendations.append({
                'type': 'high_priority_open',
                'priority': 'High',
                'message': f"{len(high_priority_open)} high priority defects are still open",
                'action': "Review and expedite high priority defects",
                'count': len(high_priority_open),
                'impact': 'High'
            })
        
        return recommendations
    
    def save_comprehensive_report(self, df, analysis, filename=None):
        """Save comprehensive analysis report"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"complete_defect_analysis_{self.current_release}_{timestamp}"
        
        # Save comprehensive DataFrame
        df.to_csv(f"{filename}.csv", index=False)
        print(f"💾 Complete defect data saved to: {filename}.csv")
        
        # Save detailed analysis report
        with open(f"{filename}_comprehensive_report.txt", 'w') as f:
            f.write(f"COMPREHENSIVE DEFECT ANALYSIS REPORT - {self.current_release}\n")
            f.write("=" * 80 + "\n\n")
            
            # Summary
            f.write("EXECUTIVE SUMMARY:\n")
            f.write("-" * 40 + "\n")
            summary = analysis['summary']
            for key, value in summary.items():
                f.write(f"  {key.replace('_', ' ').title()}: {value}\n")
            
            # Project Analysis
            f.write("\nPROJECT HEALTH ANALYSIS:\n")
            f.write("-" * 40 + "\n")
            for project, stats in list(analysis['project_analysis'].items())[:10]:
                f.write(f"  {project}: {stats['total_defects']} total, {stats['open_defects']} open, Health Score: {stats['health_score']}\n")
            
            # Top Recommendations
            f.write("\nTOP RECOMMENDATIONS:\n")
            f.write("-" * 40 + "\n")
            for rec in analysis['recommendations']:
                f.write(f"  • [{rec['priority']}] {rec['message']}\n")
                f.write(f"    Action: {rec['action']}\n")
                f.write(f"    Impact: {rec['impact']}, Count: {rec['count']}\n\n")
            
            # Top Risk Defects
            f.write("\nTOP RISK DEFECTS:\n")
            f.write("-" * 40 + "\n")
            for i, risk in enumerate(analysis['top_risks'][:15], 1):
                f.write(f"{i:2d}. {risk['key']} ({risk['project']}) - Risk: {risk['risk_score']:.3f}\n")
                f.write(f"     {risk['summary'][:60]}...\n")
                f.write(f"     {risk['issue_type']} | {risk['priority']} | {risk['age_days']} days | {risk['assignee']}\n\n")
            
            # OpenAI Insights
            if 'openai_insights' in analysis:
                f.write("\nOPENAI PATTERN ANALYSIS:\n")
                f.write("=" * 40 + "\n")
                
                openai_data = analysis['openai_insights']
                
                # Root Causes
                if 'root_causes' in openai_data:
                    f.write("\nTOP ROOT CAUSES:\n")
                    f.write("-" * 30 + "\n")
                    for i, cause in enumerate(openai_data['root_causes'], 1):
                        f.write(f"{i}. {cause.get('cause', 'Unknown')}\n")
                        f.write(f"   Evidence: {cause.get('evidence', 'N/A')}\n\n")
                
                # High Priority Patterns
                if 'high_priority_patterns' in openai_data:
                    f.write("HIGH PRIORITY PATTERNS:\n")
                    f.write("-" * 30 + "\n")
                    for pattern in openai_data['high_priority_patterns']:
                        f.write(f"• {pattern.get('pattern', 'Unknown')}\n")
                        f.write(f"  Impact: {pattern.get('impact', 'N/A')}\n\n")
                
                # Component Reliability
                if 'component_reliability' in openai_data:
                    f.write("COMPONENT RELIABILITY ASSESSMENT:\n")
                    f.write("-" * 30 + "\n")
                    for comp in openai_data['component_reliability']:
                        f.write(f"• {comp.get('component', 'Unknown')}: Score {comp.get('score', 'N/A')}\n")
                        f.write(f"  Issues: {comp.get('issues', 'N/A')}\n\n")
                
                # AI Recommendations
                if 'recommendations' in openai_data:
                    f.write("AI-POWERED RECOMMENDATIONS:\n")
                    f.write("-" * 30 + "\n")
                    for rec in openai_data['recommendations']:
                        f.write(f"• [{rec.get('priority', 'Medium')}] {rec.get('action', 'Unknown')}\n")
                        f.write(f"  Impact: {rec.get('impact', 'N/A')}\n\n")
        
        print(f"📊 Comprehensive analysis report saved to: {filename}_comprehensive_report.txt")
        return filename
    
    def _clean_nan_values(self, obj):
        """Recursively clean NaN values from nested dictionaries and lists for JSON serialization"""
        import math
        
        if isinstance(obj, dict):
            return {k: self._clean_nan_values(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._clean_nan_values(item) for item in obj]
        elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return None
        else:
            return obj

def main():
    """Main function for complete analysis"""
    print("🚀 DEFECT INTELLIGENCE")
    print("=" * 60)
    print("🎯 ANALYZING ALL BUGS - NO LIMITS")
    print("=" * 60)
    
    analyzer = DefectAnalyzer()
    
    # Step 1: Fetch ALL defects
    print("\n📡 STEP 1: Fetching ALL defects...")
    df = analyzer.get_all_release_defects()
    
    if df.empty:
        print("❌ No defects found!")
        return
    
    # Step 2: Comprehensive Analysis
    print("\n🔬 STEP 2: Performing comprehensive analysis...")
    analysis = analyzer.comprehensive_analysis(df)
    
    # Step 3: Display Results
    print("\n📊 COMPREHENSIVE ANALYSIS RESULTS")
    print("=" * 50)
    
    summary = analysis['summary']
    print(f"📈 Total Defects Analyzed: {summary['total_defects']:,}")
    print(f"🏗️ Projects Affected: {summary['projects_affected']}")
    print(f"🔓 Open Defects: {summary['open_defects']:,}")
    print(f"✅ Resolved Defects: {summary['resolved_defects']:,}")
    print(f"🚨 Critical Defects: {summary['critical_defects']}")
    print(f"🔥 Critical Open: {summary['critical_open']}")
    print(f"⏰ Average Age: {summary['avg_age_days']} days")
    print(f"📊 Resolution Rate: {summary['resolution_rate']}%")
    print(f"👤 Unassigned Rate: {summary['unassigned_rate']}%")
    
    print("\n🏆 TOP PROJECT HEALTH SCORES:")
    project_health = sorted(analysis['project_analysis'].items(), 
                           key=lambda x: x[1]['health_score'], reverse=True)
    for i, (project, stats) in enumerate(project_health[:5], 1):
        print(f"{i}. {project}: Health Score {stats['health_score']:.3f} ({stats['open_defects']} open)")
    
    print("\n🚨 HIGHEST RISK DEFECTS:")
    for i, risk in enumerate(analysis['top_risks'][:10], 1):
        print(f"{i:2d}. {risk['key']} ({risk['project']}) - Risk: {risk['risk_score']:.3f}")
        print(f"    {risk['summary'][:70]}...")
        print(f"    {risk['issue_type']} | {risk['priority']} | {risk['age_days']} days | {risk['assignee']}")
    
    print("\n💡 CRITICAL RECOMMENDATIONS:")
    for i, rec in enumerate(analysis['recommendations'], 1):
        print(f"{i}. [{rec['priority']}] {rec['message']}")
        print(f"   Action: {rec['action']}")
        print(f"   Impact: {rec['impact']}, Count: {rec['count']}")
    
    # Step 4: Save comprehensive report
    print("\n💾 STEP 4: Saving comprehensive reports...")
    filename = analyzer.save_comprehensive_report(df, analysis)
    
    print("\n✅ COMPLETE ANALYSIS FINISHED!")
    print(f"🎯 Analyzed {len(df):,} defects successfully!")
    print(f"📁 Reports saved with prefix: {filename}")
    print("📊 Ready for executive review and action!")

if __name__ == "__main__":
    main()