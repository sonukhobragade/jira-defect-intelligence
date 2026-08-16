"""
Database models and operations for Defect Intelligence System.

This module provides SQLite database functionality for storing and managing
defect data across multiple releases.
"""

import sqlite3
import pandas as pd
from typing import List, Dict, Any
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class DefectDatabase:
    """
    Database manager for defect intelligence system.
    
    Handles storage and retrieval of defect data, analysis results,
    and release management.
    """
    
    def __init__(self, db_path: str = "defect_intelligence.db"):
        """
        Initialize database connection and create tables if needed.
        
        Args:
            db_path (str): Path to SQLite database file.
        """
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Releases table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS releases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    last_analyzed TIMESTAMP
                )
            """)
            
            # Defects table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS defects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    release_id INTEGER NOT NULL,
                    project TEXT NOT NULL,
                    summary TEXT,
                    description TEXT,
                    issue_type TEXT,
                    status TEXT,
                    priority TEXT,
                    severity TEXT,
                    assignee TEXT,
                    reporter TEXT,
                    created_date TIMESTAMP,
                    updated_date TIMESTAMP,
                    resolved_date TIMESTAMP,
                    resolution TEXT,
                    components TEXT,
                    labels TEXT,
                    age_days INTEGER,
                    resolution_time_hours REAL,
                    raw_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (release_id) REFERENCES releases (id),
                    UNIQUE(key, release_id)
                )
            """)
            
            # Analysis results table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analysis_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    release_id INTEGER NOT NULL,
                    analysis_type TEXT NOT NULL,
                    results TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (release_id) REFERENCES releases (id)
                )
            """)
            
            # ML predictions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ml_predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    defect_id INTEGER NOT NULL,
                    model_type TEXT NOT NULL,
                    risk_score REAL,
                    prediction_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (defect_id) REFERENCES defects (id)
                )
            """)
            
            # Create indexes for better performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_defects_release ON defects(release_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_defects_key ON defects(key)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_defects_status ON defects(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_defects_priority ON defects(priority)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_analysis_release ON analysis_results(release_id)")
            
            conn.commit()
            logger.info("Database initialized successfully")
    
    def add_release(self, name: str, description: str = None) -> int:
        """
        Add a new release to track.
        
        Args:
            name (str): Release name (e.g., 'R1-25')
            description (str): Optional description
            
        Returns:
            int: Release ID
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO releases (name, description)
                    VALUES (?, ?)
                """, (name, description))
                release_id = cursor.lastrowid
                conn.commit()
                logger.info(f"Added release: {name} (ID: {release_id})")
                return release_id
            except sqlite3.IntegrityError:
                # Release already exists, get its ID
                cursor.execute("SELECT id FROM releases WHERE name = ?", (name,))
                result = cursor.fetchone()
                if result:
                    logger.info(f"Release {name} already exists (ID: {result[0]})")
                    return result[0]
                raise
    
    def get_releases(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        Get all releases.
        
        Args:
            active_only (bool): Only return active releases
            
        Returns:
            List[Dict]: List of release information
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = "SELECT * FROM releases"
            if active_only:
                query += " WHERE is_active = 1"
            query += " ORDER BY created_at DESC"
            
            cursor.execute(query)
            releases = [dict(row) for row in cursor.fetchall()]
            
            # Add defect counts
            for release in releases:
                cursor.execute("""
                    SELECT COUNT(*) as total,
                           SUM(CASE WHEN status NOT IN ('Resolved', 'Closed', 'Done') THEN 1 ELSE 0 END) as open
                    FROM defects WHERE release_id = ?
                """, (release['id'],))
                counts = cursor.fetchone()
                release['total_defects'] = counts['total'] or 0
                release['open_defects'] = counts['open'] or 0
            
            return releases
    
    def store_defects(self, defects_df: pd.DataFrame, release_name: str) -> int:
        """
        Store defects data in database.
        
        Args:
            defects_df (pd.DataFrame): DataFrame with defect data
            release_name (str): Release name
            
        Returns:
            int: Number of defects stored
        """
        release_id = self.add_release(release_name)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            stored_count = 0
            for _, row in defects_df.iterrows():
                try:
                    # Convert lists/dicts to JSON strings
                    components = json.dumps(row.get('components', [])) if row.get('components') else None
                    labels = json.dumps(row.get('labels', [])) if row.get('labels') else None
                    raw_data = json.dumps(row.to_dict(), default=str)
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO defects (
                            key, release_id, project, summary, description, issue_type,
                            status, priority, severity, assignee, reporter,
                            created_date, updated_date, resolved_date, resolution,
                            components, labels, age_days, resolution_time_hours, raw_data,
                            updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (
                        row.get('key'),
                        release_id,
                        row.get('project'),
                        row.get('summary'),
                        row.get('description'),
                        row.get('issue_type'),
                        row.get('status'),
                        row.get('priority'),
                        row.get('severity'),
                        row.get('assignee'),
                        row.get('reporter'),
                        row.get('created_date'),
                        row.get('updated_date'),
                        row.get('resolved_date'),
                        row.get('resolution'),
                        components,
                        labels,
                        row.get('age_days'),
                        row.get('resolution_time_hours'),
                        raw_data
                    ))
                    stored_count += 1
                except Exception as e:
                    logger.error(f"Error storing defect {row.get('key', 'unknown')}: {e}")
            
            # Update last analyzed timestamp
            cursor.execute("""
                UPDATE releases SET last_analyzed = CURRENT_TIMESTAMP WHERE id = ?
            """, (release_id,))
            
            conn.commit()
            logger.info(f"Stored {stored_count} defects for release {release_name}")
            return stored_count
    
    def get_defects(self, release_names: List[str] = None, 
                   status_filter: str = None) -> pd.DataFrame:
        """
        Retrieve defects from database.
        
        Args:
            release_names (List[str]): List of release names to filter by
            status_filter (str): Status to filter by ('open', 'closed', 'all')
            
        Returns:
            pd.DataFrame: Defects data
        """
        with sqlite3.connect(self.db_path) as conn:
            query = """
                SELECT d.*, r.name as release_name
                FROM defects d
                JOIN releases r ON d.release_id = r.id
                WHERE 1=1
            """
            params = []
            
            if release_names:
                placeholders = ','.join(['?' for _ in release_names])
                query += f" AND r.name IN ({placeholders})"
                params.extend(release_names)
            
            if status_filter == 'open':
                query += " AND d.status NOT IN ('Resolved', 'Closed', 'Done')"
            elif status_filter == 'closed':
                query += " AND d.status IN ('Resolved', 'Closed', 'Done')"
            
            query += " ORDER BY d.created_date DESC"
            
            df = pd.read_sql_query(query, conn, params=params)
            
            # Parse JSON fields back to Python objects
            if not df.empty:
                for col in ['components', 'labels']:
                    if col in df.columns:
                        df[col] = df[col].apply(
                            lambda x: json.loads(x) if x and x != 'null' else []
                        )
            
            return df
    
    def store_analysis_results(self, release_name: str, analysis_type: str, 
                             results: Dict[str, Any]) -> int:
        """
        Store analysis results in database.
        
        Args:
            release_name (str): Release name
            analysis_type (str): Type of analysis
            results (Dict): Analysis results
            
        Returns:
            int: Analysis result ID
        """
        release_id = self.add_release(release_name)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO analysis_results (release_id, analysis_type, results)
                VALUES (?, ?, ?)
            """, (release_id, analysis_type, json.dumps(results, default=str)))
            
            result_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Stored {analysis_type} analysis for {release_name}")
            return result_id
    
    def get_analysis_results(self, release_names: List[str], 
                           analysis_type: str = None) -> List[Dict[str, Any]]:
        """
        Get analysis results from database.
        
        Args:
            release_names (List[str]): Release names to get results for
            analysis_type (str): Optional analysis type filter
            
        Returns:
            List[Dict]: Analysis results
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = """
                SELECT ar.*, r.name as release_name
                FROM analysis_results ar
                JOIN releases r ON ar.release_id = r.id
                WHERE r.name IN ({})
            """.format(','.join(['?' for _ in release_names]))
            
            params = release_names
            
            if analysis_type:
                query += " AND ar.analysis_type = ?"
                params.append(analysis_type)
            
            query += " ORDER BY ar.created_at DESC"
            
            cursor.execute(query, params)
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                result['results'] = json.loads(result['results'])
                results.append(result)
            
            return results
    
    def get_database_stats(self) -> Dict[str, Any]:
        """
        Get database statistics.
        
        Returns:
            Dict: Database statistics
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get counts
            cursor.execute("SELECT COUNT(*) FROM releases WHERE is_active = 1")
            active_releases = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM defects")
            total_defects = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM analysis_results")
            total_analyses = cursor.fetchone()[0]
            
            # Get database size
            db_size = Path(self.db_path).stat().st_size if Path(self.db_path).exists() else 0
            
            return {
                'active_releases': active_releases,
                'total_defects': total_defects,
                'total_analyses': total_analyses,
                'database_size_mb': round(db_size / (1024 * 1024), 2),
                'database_path': self.db_path
            }
