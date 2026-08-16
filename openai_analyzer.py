"""
OpenAI integration for enhanced defect analysis.

This module provides advanced analysis capabilities using OpenAI's API
to analyze defect patterns, generate insights, and provide recommendations.
"""
import os
import openai
import pandas as pd
from typing import Dict, List, Any, Optional
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("openai-analyzer")

# Load environment variables
load_dotenv(override=True)

class OpenAIDefectAnalyzer:
    """
    Provides advanced defect analysis using OpenAI's API.
    """
    
    def __init__(self):
        """
        Initialize the OpenAI analyzer with API key from environment variables.
        """
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            logger.warning("OpenAI API key not found in environment variables")
            self.available = False
        else:
            self.client = openai.OpenAI(api_key=self.api_key)
            self.available = True
            self.model = os.getenv('OPENAI_MODEL', 'gpt-4o')
            logger.info(f"OpenAI analyzer initialized with model: {self.model}")
    
    def analyze_defect_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze defect patterns using OpenAI.
        
        Args:
            df: DataFrame containing defect data
            
        Returns:
            Dictionary containing analysis results
        """
        if not self.available or df.empty:
            logger.warning("OpenAI analysis not available or empty dataframe")
            return {"error": "OpenAI analysis not available or empty dataframe"}
        
        try:
            # Prepare data summary for OpenAI
            data_summary = self._prepare_data_summary(df)
            
            # Create prompt for pattern analysis
            prompt = f"""
            You are an expert defect analyst. Analyze the following defect data summary and identify key patterns:
            
            {data_summary}
            
            Provide the following analysis:
            1. Top 3 root causes of defects
            2. Key patterns in high-priority defects
            3. Component reliability assessment
            4. Recommendations for quality improvement
            
            Format your response as JSON with the following structure:
            {{
                "root_causes": [list of 3 objects with "cause" and "evidence" fields],
                "high_priority_patterns": [list of patterns with "pattern" and "impact" fields],
                "component_reliability": [list of component assessments with "component", "score", and "issues" fields],
                "recommendations": [list of recommendations with "action", "impact", and "priority" fields]
            }}
            """
            
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "You are an AI defect analysis assistant that provides insights in JSON format."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse and return the analysis
            import json
            analysis_text = response.choices[0].message.content
            analysis = json.loads(analysis_text)
            
            logger.info("Successfully completed OpenAI defect pattern analysis")
            return analysis
            
        except Exception as e:
            logger.error(f"Error in OpenAI defect pattern analysis: {str(e)}")
            return {"error": str(e)}
    
    def generate_defect_recommendations(self, defect_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate specific recommendations for individual defects.
        
        Args:
            defect_data: Dictionary containing defect information
            
        Returns:
            List of recommendations
        """
        if not self.available:
            logger.warning("OpenAI analysis not available")
            return [{"error": "OpenAI analysis not available"}]
        
        try:
            # Create prompt for defect recommendations
            prompt = f"""
            You are an expert defect analyst. Analyze the following defect and provide specific recommendations:
            
            Key: {defect_data.get('key', 'Unknown')}
            Summary: {defect_data.get('summary', 'No summary')}
            Description: {defect_data.get('description', 'No description')[:500]}...
            Issue Type: {defect_data.get('issue_type', 'Unknown')}
            Priority: {defect_data.get('priority', 'Unknown')}
            Status: {defect_data.get('status', 'Unknown')}
            Age: {defect_data.get('age_days', 0)} days
            Components: {', '.join(defect_data.get('components', ['None']))}
            
            Provide the following recommendations:
            1. Suggested priority adjustment (if needed)
            2. Potential root cause analysis
            3. Recommended next steps
            4. Risk assessment
            
            Format your response as JSON with the following structure:
            {{
                "priority_recommendation": {{ "current": "current priority", "suggested": "suggested priority", "reason": "reason for change" }},
                "potential_root_cause": {{ "cause": "potential cause", "confidence": "high/medium/low", "reasoning": "reasoning" }},
                "next_steps": [list of specific next steps with "action" and "rationale" fields],
                "risk_assessment": {{ "risk_level": "high/medium/low", "impact": "impact description", "mitigation": "mitigation strategy" }}
            }}
            """
            
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "You are an AI defect analysis assistant that provides recommendations in JSON format."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse and return the recommendations
            import json
            recommendations_text = response.choices[0].message.content
            recommendations = json.loads(recommendations_text)
            
            logger.info(f"Successfully generated recommendations for defect {defect_data.get('key', 'Unknown')}")
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating defect recommendations: {str(e)}")
            return [{"error": str(e)}]
    
    def analyze_defect_text(self, text: str, context: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze defect description text to extract insights.
        
        Args:
            text: Defect description or summary text
            context: Additional context about the defect
            
        Returns:
            Dictionary containing analysis results
        """
        if not self.available or not text:
            logger.warning("OpenAI analysis not available or empty text")
            return {"error": "OpenAI analysis not available or empty text"}
        
        try:
            # Create prompt for text analysis
            prompt = f"""
            You are an expert defect analyst. Analyze the following defect text:
            
            {text[:1000]}
            
            {f"Additional context: {context}" if context else ""}
            
            Extract the following information:
            1. Technical keywords and concepts mentioned
            2. Severity assessment based on the description
            3. Potential impact on users or system
            4. Suggested categorization
            
            Format your response as JSON with the following structure:
            {{
                "technical_keywords": [list of technical terms found in the text],
                "severity_assessment": {{ "level": "critical/high/medium/low", "reasoning": "reasoning" }},
                "potential_impact": {{ "user_impact": "impact description", "system_impact": "impact description" }},
                "suggested_category": {{ "category": "suggested category", "confidence": "high/medium/low" }}
            }}
            """
            
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "You are an AI defect analysis assistant that extracts insights from text in JSON format."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse and return the analysis
            import json
            analysis_text = response.choices[0].message.content
            analysis = json.loads(analysis_text)
            
            logger.info("Successfully completed OpenAI defect text analysis")
            return analysis
            
        except Exception as e:
            logger.error(f"Error in OpenAI defect text analysis: {str(e)}")
            return {"error": str(e)}
    
    def _prepare_data_summary(self, df: pd.DataFrame) -> str:
        """
        Prepare a summary of the defect data for OpenAI analysis.
        
        Args:
            df: DataFrame containing defect data
            
        Returns:
            String containing data summary
        """
        try:
            # Basic statistics
            total_defects = len(df)
            open_defects = len(df[df['status'] != 'Resolved'])
            high_priority = len(df[df['priority'].isin(['Highest', 'High'])])
            
            # Get top components
            component_counts = {}
            for _, row in df.iterrows():
                components = row.get('components', [])
                if isinstance(components, list):
                    for comp in components:
                        component_counts[comp] = component_counts.get(comp, 0) + 1
            
            top_components = sorted(component_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            
            # Get issue type distribution
            issue_type_counts = df['issue_type'].value_counts().to_dict()
            
            # Create summary text
            summary = f"""
            Defect Data Summary:
            - Total Defects: {total_defects}
            - Open Defects: {open_defects} ({open_defects/total_defects*100:.1f}%)
            - High Priority Defects: {high_priority} ({high_priority/total_defects*100:.1f}%)
            
            Issue Type Distribution:
            {', '.join([f"{k}: {v}" for k, v in issue_type_counts.items()])}
            
            Top Components:
            {', '.join([f"{comp}: {count}" for comp, count in top_components])}
            
            Average Age of Open Defects: {df[df['status'] != 'Resolved']['age_days'].mean():.1f} days
            """
            
            # Add sample defects
            if len(df) > 0:
                sample_defects = df.sample(min(5, len(df)))
                summary += "\nSample Defects:\n"
                for _, defect in sample_defects.iterrows():
                    summary += f"- {defect.get('key', 'Unknown')}: {defect.get('summary', 'No summary')[:100]}\n"
            
            return summary
            
        except Exception as e:
            logger.error(f"Error preparing data summary: {str(e)}")
            return f"Error preparing data summary: {str(e)}"


# Example usage
if __name__ == "__main__":
    analyzer = OpenAIDefectAnalyzer()
    if analyzer.available:
        print("OpenAI analyzer is available")
        
        # Example text analysis
        sample_text = """
        The application crashes when a user attempts to save a large file (>100MB) 
        in the document editor. This happens consistently on Chrome browser but works 
        fine on Firefox. The error in the console shows "Out of memory" exception.
        """
        
        analysis = analyzer.analyze_defect_text(sample_text)
        print("Text Analysis Results:")
        import json
        print(json.dumps(analysis, indent=2))
    else:
        print("OpenAI analyzer is not available. Please set OPENAI_API_KEY environment variable.")
