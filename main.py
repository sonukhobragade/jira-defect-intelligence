# main.py
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn
from jira_client import QuickJiraCollector
from ml_processor import QuickDefectPredictor
from analyzer import QuickDefectAnalyzer
from defect_analyzer import DefectAnalyzer

app = FastAPI(title="Defect Intelligence MVP", version="1.0.0")

# Global instances
collector = QuickJiraCollector()
predictor = QuickDefectPredictor()
analyzer = QuickDefectAnalyzer()
comprehensive_analyzer = DefectAnalyzer()

# Updated main.py - dashboard section for cross-project view
@app.get("/")
async def dashboard():
    """Enhanced dashboard for cross-project analysis"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Release Defect Intelligence Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .card { border: 1px solid #ddd; padding: 20px; margin: 10px 0; border-radius: 8px; }
            .metric { display: inline-block; margin: 10px 20px 10px 0; }
            .project-card { border-left: 4px solid #007cba; margin: 10px 0; padding: 10px; background: #f9f9f9; }
            .risk-high { color: red; font-weight: bold; }
            .risk-medium { color: orange; font-weight: bold; }
            .risk-low { color: green; }
            button { background: #007cba; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; margin: 5px; }
            button:hover { background: #005a8a; }
            .loading { color: #666; font-style: italic; }
            .release-title { color: #007cba; font-size: 1.2em; font-weight: bold; }
        </style>
    </head>
    <body>
        <h1>🚀 Release Defect Intelligence Dashboard</h1>
        <div class="release-title">📦 Cross-project defect analysis</div>
        
        <div class="card">
            <h2>Quick Actions</h2>
            <button onclick="analyzeDefects()">Analyze Current Release</button>
            <button onclick="getOpenAIInsights()" style="background: #28a745;">🤖 OpenAI Insights</button>
            <button onclick="compareReleases()">Compare with Previous Releases</button>
            <button onclick="trainModels()">Train ML Models</button>
            <button onclick="getRecommendations()">Get Recommendations</button>
        </div>
        
        <div id="results" class="card" style="display:none;">
            <h2>Analysis Results</h2>
            <div id="results-content"></div>
        </div>
        
        <script>
            async function compareReleases() {
                document.getElementById('results').style.display = 'block';
                document.getElementById('results-content').innerHTML = '<div class="loading">Comparing releases...</div>';
                
                try {
                    const response = await fetch('/compare-releases');
                    const data = await response.json();
                    displayReleaseComparison(data);
                } catch (error) {
                    document.getElementById('results-content').innerHTML = 'Error: ' + error.message;
                }
            }
            
            function fmtPct(value) {
                if (value === null || value === undefined || isNaN(value)) return 'n/a';
                return Number(value).toFixed(1) + '%';
            }

            function displayResults(data) {
                let html = '<h3>📊 Comprehensive Analysis Summary</h3>';
                html += `<div class="metric">Total Defects: <strong>${data.summary.total_defects}</strong></div>`;
                html += `<div class="metric">Projects Affected: <strong>${data.summary.projects_affected}</strong></div>`;
                html += `<div class="metric">Open Defects: <strong>${data.summary.open_defects}</strong></div>`;
                html += `<div class="metric">Critical Count: <strong>${data.summary.critical_count}</strong></div>`;
                html += `<div class="metric">Resolution Rate: <strong>${fmtPct(data.summary.resolution_rate)}</strong></div>`;
                
                // Top Risk Defects
                if (data.top_risks && data.top_risks.length > 0) {
                    html += '<h3>🚨 Top Risk Defects</h3>';
                    data.top_risks.slice(0, 5).forEach((risk, index) => {
                        const riskClass = risk.risk_score > 0.3 ? 'risk-high' : risk.risk_score > 0.2 ? 'risk-medium' : 'risk-low';
                        html += `<div class="project-card ${riskClass}">
                            <strong>${index + 1}. ${risk.key}</strong> (${risk.project}) - Risk: ${risk.risk_score.toFixed(3)}<br>
                            ${risk.summary.substring(0, 80)}...<br>
                            <small>${risk.issue_type} | ${risk.priority} | ${risk.age_days} days | ${risk.assignee}</small>
                        </div>`;
                    });
                }
                
                // Project Analysis
                if (data.project_analysis) {
                    html += '<h3>📁 Project Health Analysis</h3>';
                    const topProjects = Object.entries(data.project_analysis)
                        .sort(([,a], [,b]) => b.health_score - a.health_score)
                        .slice(0, 5);
                    topProjects.forEach(([project, stats]) => {
                        const healthClass = stats.health_score > 0.7 ? 'risk-low' : stats.health_score > 0.5 ? 'risk-medium' : 'risk-high';
                        html += `<div class="project-card ${healthClass}">
                            <strong>${project}</strong>: Health Score ${stats.health_score.toFixed(3)}<br>
                            ${stats.total_defects} total, ${stats.open_defects} open, ${stats.critical_defects} critical
                            (Avg age: ${Math.round(stats.avg_age)} days)
                        </div>`;
                    });
                }
                
                // OpenAI Insights - NEW SECTION!
                if (data.openai_insights) {
                    html += '<h3>🤖 OpenAI Pattern Analysis</h3>';
                    const ai = data.openai_insights;
                    
                    // Root Causes
                    if (ai.root_causes && ai.root_causes.length > 0) {
                        html += '<h4>🔍 Top Root Causes</h4>';
                        ai.root_causes.slice(0, 3).forEach((cause, index) => {
                            html += `<div class="project-card">
                                <strong>${index + 1}. ${cause.cause || 'Unknown'}</strong><br>
                                <small>Evidence: ${cause.evidence || 'N/A'}</small>
                            </div>`;
                        });
                    }
                    
                    // High Priority Patterns
                    if (ai.high_priority_patterns && ai.high_priority_patterns.length > 0) {
                        html += '<h4>⚡ High Priority Patterns</h4>';
                        ai.high_priority_patterns.slice(0, 3).forEach(pattern => {
                            html += `<div class="project-card risk-high">
                                <strong>• ${pattern.pattern || 'Unknown'}</strong><br>
                                <small>Impact: ${pattern.impact || 'N/A'}</small>
                            </div>`;
                        });
                    }
                    
                    // Component Reliability
                    if (ai.component_reliability && ai.component_reliability.length > 0) {
                        html += '<h4>🔧 Component Reliability</h4>';
                        ai.component_reliability.slice(0, 3).forEach(comp => {
                            const scoreClass = comp.score > 7 ? 'risk-low' : comp.score > 4 ? 'risk-medium' : 'risk-high';
                            html += `<div class="project-card ${scoreClass}">
                                <strong>${comp.component || 'Unknown'}</strong>: Score ${comp.score || 'N/A'}<br>
                                <small>Issues: ${comp.issues || 'N/A'}</small>
                            </div>`;
                        });
                    }
                    
                    // AI Recommendations
                    if (ai.recommendations && ai.recommendations.length > 0) {
                        html += '<h4>💡 AI Recommendations</h4>';
                        ai.recommendations.slice(0, 3).forEach(rec => {
                            const priorityClass = rec.priority === 'High' ? 'risk-high' : rec.priority === 'Medium' ? 'risk-medium' : 'risk-low';
                            html += `<div class="project-card ${priorityClass}">
                                <strong>[${rec.priority || 'Medium'}] ${rec.action || 'Unknown'}</strong><br>
                                <small>Impact: ${rec.impact || 'N/A'}</small>
                            </div>`;
                        });
                    }
                }
                
                // Recommendations
                if (data.recommendations && data.recommendations.length > 0) {
                    html += '<h3>💡 Key Recommendations</h3>';
                    data.recommendations.slice(0, 5).forEach(rec => {
                        const priorityClass = rec.priority === 'Critical' ? 'risk-high' : rec.priority === 'High' ? 'risk-medium' : 'risk-low';
                        html += `<div class="project-card ${priorityClass}">
                            <strong>[${rec.priority}] ${rec.message}</strong><br>
                            <small>Action: ${rec.action} | Impact: ${rec.impact} | Count: ${rec.count}</small>
                        </div>`;
                    });
                }
                
                document.getElementById('results-content').innerHTML = html;
            }
            
            async function analyzeDefects() {
                document.getElementById('results').style.display = 'block';
                document.getElementById('results-content').innerHTML = '<div class="loading">Analyzing defects...</div>';
                
                try {
                    const response = await fetch('/analyze');
                    const data = await response.json();
                    displayResults(data);
                } catch (error) {
                    document.getElementById('results-content').innerHTML = 'Error: ' + error.message;
                }
            }
            
            async function getOpenAIInsights() {
                document.getElementById('results').style.display = 'block';
                document.getElementById('results-content').innerHTML = '<div class="loading">🤖 Getting OpenAI insights...</div>';
                
                try {
                    const response = await fetch('/openai-insights');
                    const data = await response.json();
                    displayOpenAIResults(data);
                } catch (error) {
                    document.getElementById('results-content').innerHTML = 'Error: ' + error.message;
                }
            }
            
            function displayOpenAIResults(data) {
                let html = '<h3>🤖 OpenAI-Powered Comprehensive Analysis</h3>';
                html += `<div class="metric">Total Defects Analyzed: <strong>${data.summary.total_defects}</strong></div>`;
                html += `<div class="metric">Projects: <strong>${data.summary.projects_affected}</strong></div>`;
                html += `<div class="metric">Resolution Rate: <strong>${fmtPct(data.summary.resolution_rate)}</strong></div>`;
                
                // OpenAI Insights Section
                if (data.openai_insights) {
                    const ai = data.openai_insights;
                    html += '<div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0;">';
                    html += '<h3>🧠 AI Pattern Analysis</h3>';
                    
                    // Root Causes
                    if (ai.root_causes && ai.root_causes.length > 0) {
                        html += '<h4>🔍 Top Root Causes</h4>';
                        ai.root_causes.slice(0, 3).forEach((cause, i) => {
                            html += `<div class="project-card"><strong>${i+1}. ${cause.cause || 'Unknown'}</strong><br><small>Impact: ${cause.impact || 'N/A'}</small></div>`;
                        });
                    }
                    
                    // High Priority Patterns
                    if (ai.high_priority_patterns && ai.high_priority_patterns.length > 0) {
                        html += '<h4>⚡ High Priority Patterns</h4>';
                        ai.high_priority_patterns.forEach(pattern => {
                            html += `<div class="project-card risk-high"><strong>${pattern.pattern || 'Unknown'}</strong><br><small>Severity: ${pattern.severity || 'N/A'}</small></div>`;
                        });
                    }
                    
                    // Component Reliability
                    if (ai.component_reliability && ai.component_reliability.length > 0) {
                        html += '<h4>🔧 Component Reliability</h4>';
                        ai.component_reliability.slice(0, 3).forEach(comp => {
                            const scoreClass = comp.score > 0.8 ? 'risk-low' : comp.score > 0.6 ? 'risk-medium' : 'risk-high';
                            html += `<div class="project-card ${scoreClass}"><strong>${comp.component || 'Unknown'}</strong><br>Reliability Score: ${comp.score || 'N/A'}</div>`;
                        });
                    }
                    
                    // AI Recommendations
                    if (ai.recommendations && ai.recommendations.length > 0) {
                        html += '<h4>💡 AI Recommendations</h4>';
                        ai.recommendations.slice(0, 3).forEach(rec => {
                            const priorityClass = rec.priority === 'High' ? 'risk-high' : rec.priority === 'Medium' ? 'risk-medium' : 'risk-low';
                            html += `<div class="project-card ${priorityClass}"><strong>[${rec.priority || 'Medium'}] ${rec.action || 'Unknown'}</strong><br><small>Impact: ${rec.impact || 'N/A'}</small></div>`;
                        });
                    }
                    
                    html += '</div>';
                }
                
                // Top Risk Defects
                if (data.top_risks && data.top_risks.length > 0) {
                    html += '<h3>🚨 Top Risk Defects</h3>';
                    data.top_risks.slice(0, 5).forEach(defect => {
                        const riskClass = defect.risk_score > 0.7 ? 'risk-high' : defect.risk_score > 0.4 ? 'risk-medium' : 'risk-low';
                        html += `<div class="project-card ${riskClass}"><strong>${defect.key}</strong> - Risk: ${defect.risk_score.toFixed(3)}<br><small>${defect.summary || 'No summary'}</small></div>`;
                    });
                }
                
                document.getElementById('results-content').innerHTML = html;
            }
            
            async function trainModels() {
                document.getElementById('results').style.display = 'block';
                document.getElementById('results-content').innerHTML = '<div class="loading">Training models...</div>';
                
                try {
                    const response = await fetch('/train', { method: 'POST' });
                    const data = await response.json();
                    document.getElementById('results-content').innerHTML = '<h3>✅ ' + data.message + '</h3>';
                } catch (error) {
                    document.getElementById('results-content').innerHTML = 'Error: ' + error.message;
                }
            }
            
            async function getRecommendations() {
                document.getElementById('results').style.display = 'block';
                document.getElementById('results-content').innerHTML = '<div class="loading">Getting recommendations...</div>';
                
                try {
                    const response = await fetch('/recommendations');
                    const data = await response.json();
                    let html = '<h3>💡 AI Recommendations</h3>';
                    if (data.recommendations && data.recommendations.length > 0) {
                        data.recommendations.forEach(rec => {
                            const priorityClass = rec.priority === 'Critical' ? 'risk-high' : rec.priority === 'High' ? 'risk-medium' : 'risk-low';
                            html += `<div class="project-card ${priorityClass}"><strong>[${rec.priority}] ${rec.message}</strong><br><small>Action: ${rec.action} | Impact: ${rec.impact}</small></div>`;
                        });
                    } else {
                        html += '<p>No recommendations available. Train models first.</p>';
                    }
                    document.getElementById('results-content').innerHTML = html;
                } catch (error) {
                    document.getElementById('results-content').innerHTML = 'Error: ' + error.message;
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/compare-releases")
async def compare_releases():
    """Compare current release with previous releases"""
    try:
        df = collector.get_release_comparison()
        if df.empty:
            return {"error": "No data for release comparison"}
        
        # Analyze by release
        release_comparison = {}
        for release in df['affected_version'].unique():
            release_df = df[df['affected_version'] == release]
            release_comparison[release] = analyzer.analyze_defects(release_df)
        
        return {"release_comparison": release_comparison}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    """Simple HTML dashboard"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Defect Intelligence Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .card { border: 1px solid #ddd; padding: 20px; margin: 10px 0; border-radius: 8px; }
            .metric { display: inline-block; margin: 10px 20px 10px 0; }
            .risk-high { color: red; font-weight: bold; }
            .risk-medium { color: orange; font-weight: bold; }
            .risk-low { color: green; }
            button { background: #007cba; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
            button:hover { background: #005a8a; }
            .loading { color: #666; font-style: italic; }
        </style>
    </head>
    <body>
        <h1>🚀 Defect Intelligence Dashboard</h1>
        
        <div class="card">
            <h2>Quick Actions</h2>
            <button onclick="analyzeDefects()">Analyze Current Release</button>
            <button onclick="trainModels()">Train ML Models</button>
            <button onclick="getRecommendations()">Get Recommendations</button>
        </div>
        
        <div id="results" class="card" style="display:none;">
            <h2>Analysis Results</h2>
            <div id="results-content"></div>
        </div>
        
        <script>
            async function analyzeDefects() {
                document.getElementById('results').style.display = 'block';
                document.getElementById('results-content').innerHTML = '<div class="loading">Analyzing defects...</div>';
                
                try {
                    const response = await fetch('/analyze');
                    const data = await response.json();
                    displayResults(data);
                } catch (error) {
                    document.getElementById('results-content').innerHTML = 'Error: ' + error.message;
                }
            }
            
            async function trainModels() {
                document.getElementById('results-content').innerHTML = '<div class="loading">Training models...</div>';
                
                try {
                    const response = await fetch('/train', {method: 'POST'});
                    const data = await response.json();
                    document.getElementById('results-content').innerHTML = '<div>✅ ' + data.message + '</div>';
                } catch (error) {
                    document.getElementById('results-content').innerHTML = 'Error: ' + error.message;
                }
            }
            
            async function getRecommendations() {
                document.getElementById('results-content').innerHTML = '<div class="loading">Getting recommendations...</div>';
                
                try {
                    const response = await fetch('/recommendations');
                    const data = await response.json();
                    displayRecommendations(data);
                } catch (error) {
                    document.getElementById('results-content').innerHTML = 'Error: ' + error.message;
                }
            }
            
            function fmtPct(value) {
                if (value === null || value === undefined || isNaN(value)) return 'n/a';
                return Number(value).toFixed(1) + '%';
            }

            function displayResults(data) {
                let html = '<h3>📊 Summary Statistics</h3>';
                html += `<div class="metric">Total Defects: <strong>${data.summary.total_defects}</strong></div>`;
                html += `<div class="metric">Open Defects: <strong>${data.summary.open_defects}</strong></div>`;
                html += `<div class="metric">Critical Count: <strong>${data.summary.critical_count}</strong></div>`;
                html += `<div class="metric">Average Age: <strong>${Math.round(data.summary.avg_age_days)} days</strong></div>`;
                
                html += '<h3>🔥 Top Risk Defects</h3>';
                if (data.top_risks.length > 0) {
                    html += '<ul>';
                    data.top_risks.slice(0, 5).forEach(defect => {
                        const riskClass = defect.overall_risk_score > 0.7 ? 'risk-high' : 
                                         defect.overall_risk_score > 0.4 ? 'risk-medium' : 'risk-low';
                        html += `<li class="${riskClass}">
                            <strong>${defect.key}</strong>: ${defect.summary.substring(0, 80)}...
                            (Risk: ${Math.round(defect.overall_risk_score * 100)}%, Age: ${defect.age_days} days)
                        </li>`;
                    });
                    html += '</ul>';
                } else {
                    html += '<div>No high-risk defects found</div>';
                }
                
                document.getElementById('results-content').innerHTML = html;
            }
            
            function displayRecommendations(data) {
                let html = '<h3>💡 Recommendations</h3>';
                if (data.recommendations.length > 0) {
                    html += '<ul>';
                    data.recommendations.forEach(rec => {
                        html += `<li><strong>${rec.message}</strong><br>Action: ${rec.action}</li>`;
                    });
                    html += '</ul>';
                } else {
                    html += '<div>✅ No immediate recommendations</div>';
                }
                document.getElementById('results-content').innerHTML = html;
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/analyze")
async def analyze_defects():
    """Analyze defects from JIRA"""
    try:
        # Get defects
        df = collector.get_defects_quick()
        if df.empty:
            return {"error": "No defects found"}
        
        # Prepare data
        df = predictor.prepare_data_quick(df)
        
        # Make predictions if models are trained
        if predictor.models:
            df = predictor.predict_defect_risk(df)
        
        # Analyze
        analysis = analyzer.analyze_defects(df)
        
        return analysis
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/openai-insights")
async def get_openai_insights():
    """Get comprehensive OpenAI-powered defect analysis"""
    try:
        # Get ALL defects for comprehensive analysis
        df = comprehensive_analyzer.get_all_release_defects()
        if df.empty:
            return {"error": "No defects found"}
        
        # Perform comprehensive analysis with OpenAI insights
        analysis = comprehensive_analyzer.comprehensive_analysis(df)
        
        return analysis
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/train")
async def train_models():
    """Train ML models"""
    try:
        df = collector.get_defects_quick()
        if df.empty:
            return {"error": "No data for training"}
        
        df = predictor.prepare_data_quick(df)
        predictor.train_quick_models(df)
        
        return {"message": f"Models trained successfully with {len(df)} defects"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/recommendations")
async def get_recommendations():
    """Get AI recommendations"""
    try:
        df = collector.get_defects_quick()
        if df.empty:
            return {"recommendations": []}
        
        df = predictor.prepare_data_quick(df)
        if predictor.models:
            df = predictor.predict_defect_risk(df)
        
        analysis = analyzer.analyze_defects(df)
        return {"recommendations": analysis.get('recommendations', [])}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)