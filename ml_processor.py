# ml_processor.py
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
import joblib
import logging
import os
from config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ml-processor")

class QuickDefectPredictor:
    def __init__(self):
        self.models = {}
        self.encoders = {}
        self.openai_analyzer = None
        
        # Try to import OpenAI analyzer if available
        try:
            from openai_analyzer import OpenAIDefectAnalyzer
            self.openai_analyzer = OpenAIDefectAnalyzer()
            if self.openai_analyzer.available:
                logger.info("OpenAI analyzer initialized successfully")
            else:
                logger.info("OpenAI analyzer not available (API key not found)")
        except ImportError:
            logger.info("OpenAI analyzer module not found")
        except Exception as e:
            logger.error(f"Error initializing OpenAI analyzer: {str(e)}")
        
    def prepare_data_quick(self, df):
        """Quick data preparation for ML"""
        if df.empty:
            logger.warning("Empty dataframe provided for data preparation")
            return df
        
        logger.info(f"Preparing data for ML with {len(df)} records")
        
        # Create target variables
        df['is_high_priority'] = (df['priority'].isin(['High', 'Highest'])).astype(int)
        df['is_critical_issue'] = df['issue_type'].isin(Config.CRITICAL_ISSUE_TYPES).astype(int)
        df['needs_attention'] = ((df['age_days'] > 7) & (df['status'] != 'Resolved')).astype(int)
        
        # Create simple features
        df['summary_length'] = df['summary'].str.len()
        df['description_length'] = df['description'].str.len()
        df['has_components'] = (df['components'].str.len() > 0).astype(int)
        
        # Enhanced features
        # Age buckets for better feature representation
        df['age_bucket'] = pd.cut(
            df['age_days'], 
            bins=[0, 7, 14, 30, 60, float('inf')],
            labels=[0, 1, 2, 3, 4]
        ).astype(int)
        
        # Status encoding
        status_mapping = {
            'Open': 0,
            'In Progress': 1,
            'In Review': 2,
            'Resolved': 3,
            'Closed': 4
        }
        df['status_encoded'] = df['status'].map(status_mapping).fillna(0).astype(int)
        
        # Handle categorical fields that might be missing
        for field in ['reporter', 'assignee', 'project']:
            if field in df.columns:
                df[f'{field}_encoded'] = self._encode_categorical(df, field)
            else:
                df[f'{field}_encoded'] = 0
        
        # Handle custom fields that might be missing
        if 'severity' in df.columns:
            df['severity_encoded'] = self._encode_categorical(df, 'severity')
        else:
            df['severity_encoded'] = 0
        
        # Issue-type weighting. Types listed in CRITICAL_ISSUE_TYPES rank
        # above the rest; anything unrecognised falls back to the base weight.
        # The names themselves come from your Jira site, so they are read from
        # configuration rather than fixed here.
        critical = list(Config.CRITICAL_ISSUE_TYPES)
        issue_type_mapping = {
            name: len(critical) + 1 - i for i, name in enumerate(critical)
        }
        df['issue_type_severity'] = df['issue_type'].map(issue_type_mapping).fillna(1)
        # Normalised to 0-1 against the actual maximum. The risk score below
        # divided by a hard-coded 4, which is only correct when exactly three
        # critical issue types are configured. With five, this term alone
        # reached 1.5 and the "risk score" exceeded 100%.
        df['issue_type_severity_norm'] = (
            df['issue_type_severity'] / (len(critical) + 1) if critical else 0.25
        )
        
        # Text-based features if OpenAI analyzer is available
        if self.openai_analyzer and self.openai_analyzer.available:
            logger.info(f"Enhancing features with OpenAI text analysis for {len(df)} defects")
            self._enhance_features_with_openai(df)
        
        logger.info(f"Data preparation complete with {len(df.columns)} features")
        return df
        
    def _enhance_features_with_openai(self, df):
        """Enhance features using OpenAI text analysis"""
        if not self.openai_analyzer or not self.openai_analyzer.available:
            return
            
        try:
            # Sample a few defects for text analysis to avoid API costs
            sample_size = min(10, len(df))
            sample_indices = np.random.choice(df.index, sample_size, replace=False)
            
            for idx in sample_indices:
                defect = df.loc[idx]
                text = f"Summary: {defect.get('summary', '')}\nDescription: {defect.get('description', '')[:500]}"
                
                analysis = self.openai_analyzer.analyze_defect_text(text)
                
                if 'error' not in analysis:
                    # Store the severity assessment
                    severity_level = analysis.get('severity_assessment', {}).get('level', 'medium')
                    severity_score = {
                        'critical': 1.0,
                        'high': 0.75,
                        'medium': 0.5,
                        'low': 0.25
                    }.get(severity_level, 0.5)
                    
                    df.at[idx, 'ai_severity_score'] = severity_score
                    
                    # Store user impact assessment
                    user_impact = analysis.get('potential_impact', {}).get('user_impact', '')
                    if 'severe' in user_impact.lower() or 'critical' in user_impact.lower():
                        df.at[idx, 'ai_user_impact'] = 1.0
                    elif 'moderate' in user_impact.lower():
                        df.at[idx, 'ai_user_impact'] = 0.5
                    else:
                        df.at[idx, 'ai_user_impact'] = 0.25
            
            # Fill missing values with median
            if 'ai_severity_score' in df.columns:
                median_severity = df['ai_severity_score'].median()
                df['ai_severity_score'] = df['ai_severity_score'].fillna(median_severity)
                
            if 'ai_user_impact' in df.columns:
                median_impact = df['ai_user_impact'].median()
                df['ai_user_impact'] = df['ai_user_impact'].fillna(median_impact)
                
            logger.info("Successfully enhanced features with OpenAI text analysis")
            
        except Exception as e:
            logger.error(f"Error enhancing features with OpenAI: {str(e)}")
            # Continue without OpenAI features
    
    def _encode_categorical(self, df, column):
        """Quick categorical encoding with handling for missing values and new categories"""
        # Fill missing values with 'unknown'
        values = df[column].fillna('unknown').astype(str)
        
        if column not in self.encoders:
            # First time encoding this column
            self.encoders[column] = LabelEncoder()
            return self.encoders[column].fit_transform(values)
        else:
            # Handle potential new categories not seen during training
            try:
                return self.encoders[column].transform(values)
            except ValueError:
                # If new categories are found, re-fit the encoder
                print(f"⚠️ New categories found in {column}, re-fitting encoder")
                self.encoders[column] = LabelEncoder()
                return self.encoders[column].fit_transform(values)
    
    def train_quick_models(self, df):
        """Train simple but effective models with robust feature handling"""
        if len(df) < 10:
            logger.warning("Not enough data for training (minimum 10 samples required)")
            return
        
        logger.info(f"Starting model training with {len(df)} samples")
        
        # Define expected features
        expected_features = [
            'summary_length', 'description_length', 'has_components',
            'age_days', 'issue_type_severity', 'reporter_encoded',
            'assignee_encoded', 'severity_encoded'
        ]
        
        # Add enhanced features if available
        enhanced_features = [
            'age_bucket', 'status_encoded', 'project_encoded',
            'ai_severity_score', 'ai_user_impact'
        ]
        
        for feature in enhanced_features:
            if feature in df.columns:
                expected_features.append(feature)
        
        # Check which features are available
        available_features = [col for col in expected_features if col in df.columns]
        
        if len(available_features) < 3:
            logger.warning(f"Not enough features available for training (found {len(available_features)})")
            return
        
        logger.info(f"Training models with {len(available_features)} features: {', '.join(available_features)}")
        
        # Prepare features, filling missing values with 0
        X = df[available_features].fillna(0)
        
        # Split data for training and validation
        try:
            X_train, X_val, y_train_priority, y_val_priority = train_test_split(
                X, df['is_high_priority'], test_size=0.2, random_state=42
            )
            
            # Train priority prediction model
            if 'is_high_priority' in df.columns:
                logger.info("Training priority prediction model")
                self.models['priority'] = RandomForestClassifier(n_estimators=100, random_state=42)
                self.models['priority'].fit(X_train, y_train_priority)
                
                # Evaluate model
                val_score = self.models['priority'].score(X_val, y_val_priority)
                logger.info(f"Priority model trained with {len(X_train)} samples, validation accuracy: {val_score:.4f}")
            
            # Train attention prediction model
            if 'needs_attention' in df.columns:
                logger.info("Training attention prediction model")
                _, _, y_train_attention, y_val_attention = train_test_split(
                    X, df['needs_attention'], test_size=0.2, random_state=42
                )
                
                self.models['attention'] = RandomForestClassifier(n_estimators=100, random_state=42)
                self.models['attention'].fit(X_train, y_train_attention)
                
                # Evaluate model
                val_score = self.models['attention'].score(X_val, y_val_attention)
                logger.info(f"Attention model trained with {len(X_train)} samples, validation accuracy: {val_score:.4f}")
            
            # Train critical issue prediction model
            if 'is_critical_issue' in df.columns:
                logger.info("Training critical issue prediction model")
                _, _, y_train_critical, y_val_critical = train_test_split(
                    X, df['is_critical_issue'], test_size=0.2, random_state=42
                )
                
                self.models['critical'] = RandomForestClassifier(n_estimators=100, random_state=42)
                self.models['critical'].fit(X_train, y_train_critical)
                
                # Evaluate model
                val_score = self.models['critical'].score(X_val, y_val_critical)
                logger.info(f"Critical issue model trained with {len(X_train)} samples, validation accuracy: {val_score:.4f}")
            
            # Save models if requested
            if os.getenv('SAVE_ML_MODELS', 'false').lower() == 'true':
                logger.info("Saving trained models to disk")
                try:
                    os.makedirs('models', exist_ok=True)
                    for model_name, model in self.models.items():
                        joblib.dump(model, f'models/{model_name}_model.joblib')
                    logger.info("Models saved successfully")
                except Exception as e:
                    logger.error(f"Error saving models: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error during model training: {str(e)}")
            # Continue with basic models if possible
    
    def predict_defect_risk(self, df):
        """Make predictions on defects with robust feature handling"""
        if df.empty:
            logger.warning("Empty dataframe provided for prediction")
            return df

        logger.info(f"Making predictions for {len(df)} defects")

        # Define expected features
        expected_features = [
            'summary_length', 'description_length', 'has_components',
            'age_days', 'issue_type_severity', 'reporter_encoded',
            'assignee_encoded', 'severity_encoded'
        ]

        # Add enhanced features if available
        enhanced_features = [
            'age_bucket', 'status_encoded', 'project_encoded',
            'ai_severity_score', 'ai_user_impact'
        ]

        for feature in enhanced_features:
            if feature in df.columns:
                expected_features.append(feature)

        # Check which features are available
        available_features = [col for col in expected_features if col in df.columns]

        # If we don't have enough features or models, use fallback scoring
        if len(available_features) < 3 or not self.models:
            logger.warning("Not enough features or models for prediction, using fallback scoring")
            # Fallback risk calculation
            df['overall_risk_score'] = (
                df['is_critical'].astype(float) * 0.3 +
                (df['priority'].isin(['High', 'Highest'])).astype(float) * 0.2 +
                np.clip(df['age_days'] / 30, 0, 1) * 0.3 +
                (~df['is_resolved']).astype(float) * 0.2
            )
            return df

        logger.info(f"Predicting with {len(available_features)} features: {', '.join(available_features)}")

        # Prepare features, filling missing values with 0
        X = df[available_features].fillna(0)

        # Predict priority risk
        if 'priority' in self.models:
            try:
                # Get prediction probabilities
                proba = self.models['priority'].predict_proba(X)

                # Check if we have two columns (binary classification)
                if proba.shape[1] >= 2:
                    df['priority_risk_score'] = proba[:, 1]  # Use second column for positive class
                else:
                    # If only one column, use the raw predictions
                    df['priority_risk_score'] = self.models['priority'].predict(X).astype(float)

                logger.info("Priority risk prediction successful")
            except Exception as e:
                logger.error(f"Error in priority prediction: {str(e)}")
                df['priority_risk_score'] = 0.5  # Default value
        else:
            df['priority_risk_score'] = 0.5  # Default value

        # Predict attention needed
        if 'attention' in self.models:
            try:
                # Get prediction probabilities
                proba = self.models['attention'].predict_proba(X)

                # Check if we have two columns (binary classification)
                if proba.shape[1] >= 2:
                    df['attention_score'] = proba[:, 1]  # Use second column for positive class
                else:
                    # If only one column, use the raw predictions
                    df['attention_score'] = self.models['attention'].predict(X).astype(float)

                logger.info("Attention prediction successful")
            except Exception as e:
                logger.error(f"Error in attention prediction: {str(e)}")
                df['attention_score'] = 0.5  # Default value
        else:
            df['attention_score'] = 0.5  # Default value

        # Predict critical issue likelihood if model exists
        if 'critical' in self.models:
            try:
                proba = self.models['critical'].predict_proba(X)
                if proba.shape[1] >= 2:
                    df['critical_score'] = proba[:, 1]
                else:
                    df['critical_score'] = self.models['critical'].predict(X).astype(float)
                logger.info("Critical issue prediction successful")
            except Exception as e:
                logger.error(f"Error in critical issue prediction: {str(e)}")
                df['critical_score'] = 0.5  # Default value
        else:
            df['critical_score'] = 0.5  # Default value

        # Calculate overall risk score with OpenAI insights if available
        if 'ai_severity_score' in df.columns and 'critical_score' in df.columns:
            df['overall_risk_score'] = (
                df['priority_risk_score'] * 0.3 +
                df['attention_score'] * 0.2 +
                df['critical_score'] * 0.2 +
                df['ai_severity_score'] * 0.2 +
                df['issue_type_severity_norm'] * 0.1
            )
            logger.info("Overall risk score calculation complete with OpenAI insights")
        else:
            df['overall_risk_score'] = (
                df['priority_risk_score'] * 0.4 +
                df['attention_score'] * 0.3 +
                df['issue_type_severity_norm'] * 0.3
            )
            logger.info("Overall risk score calculation complete")
        
        return df