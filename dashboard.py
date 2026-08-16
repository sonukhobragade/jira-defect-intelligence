# dashboard.py - Defect Intelligence Dashboard
from fastapi import FastAPI, HTTPException, Request, status, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import numpy as np
from defect_analyzer import DefectAnalyzer
import pandas as pd
import logging
import traceback
from typing import Dict, List, Any
from datetime import datetime
from config import Config
from database import DefectDatabase

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("defect-ai-dashboard")

app = FastAPI(title="Defect Intelligence Dashboard", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
try:
    # Initialize database
    db = DefectDatabase(Config.DB_PATH)
    logger.info(f"Successfully initialized database at {Config.DB_PATH}")
    
    # Initialize analyzer
    analyzer = DefectAnalyzer()
    logger.info("Successfully initialized DefectAnalyzer")
    
    # Cache for temporary data
    cached_data: Dict[str, Any] = {}
    
    # Ensure we have at least one release in the database
    for release in Config.DEFAULT_RELEASES:
        db.add_release(release, f"Default release {release}")
        logger.info(f"Ensured release {release} exists in database")
        
except Exception as e:
    logger.error(f"Failed to initialize components: {str(e)}")
    logger.error(traceback.format_exc())
    raise

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please try again later."}
    )

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Main dashboard interface"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Defect Intelligence Dashboard</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                color: #333;
            }
            .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
            .header { 
                text-align: center; 
                color: white; 
                margin-bottom: 30px;
                background: rgba(0,0,0,0.1);
                padding: 20px;
                border-radius: 15px;
            }
            .header h1 { font-size: 2.5em; margin-bottom: 10px; }
            .header p { font-size: 1.2em; opacity: 0.9; }
            
            .release-selector {
                background: white;
                padding: 15px;
                border-radius: 10px;
                margin-bottom: 20px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            }
            .release-selector h3 {
                margin-top: 0;
                color: #667eea;
                margin-bottom: 10px;
            }
            .release-selector select {
                width: 100%;
                padding: 8px;
                border-radius: 5px;
                border: 1px solid #ddd;
                margin-bottom: 10px;
            }
            .release-selector button {
                background: linear-gradient(45deg, #667eea, #764ba2);
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 5px;
                cursor: pointer;
            }
            
            .trendline-chart {
                background: white;
                padding: 20px;
                border-radius: 10px;
                margin-bottom: 20px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            }
            
            .cards { 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); 
                gap: 20px; 
                margin-bottom: 30px; 
            }
            .card { 
                background: white; 
                padding: 25px; 
                border-radius: 15px; 
                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                transition: transform 0.3s ease;
            }
            .card:hover { transform: translateY(-5px); }
            .card h3 { 
                color: #667eea; 
                margin-bottom: 15px; 
                font-size: 1.3em;
                display: flex;
                align-items: center;
            }
            .card h3::before {
                content: "";
                display: inline-block;
                width: 4px;
                height: 20px;
                background: #667eea;
                margin-right: 10px;
                border-radius: 2px;
            }
            
            .actions { 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); 
                gap: 15px; 
                margin-bottom: 30px; 
            }
            .action-btn { 
                background: linear-gradient(45deg, #667eea, #764ba2);
                color: white; 
                border: none; 
                padding: 15px 25px; 
                border-radius: 10px; 
                cursor: pointer; 
                font-size: 1em;
                font-weight: 600;
                transition: all 0.3s ease;
                box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            }
            .action-btn:hover { 
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(0,0,0,0.3);
            }
            .openai-btn {
                background: linear-gradient(45deg, #28a745, #20c997) !important;
                position: relative;
                overflow: hidden;
            }
            .openai-btn:hover {
                background: linear-gradient(45deg, #218838, #1ea085) !important;
            }
            .openai-btn::before {
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
                transition: left 0.5s;
            }
            .openai-btn:hover::before {
                left: 100%;
            }
            
            .results { 
                background: white; 
                border-radius: 15px; 
                padding: 25px; 
                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                display: none; 
            }
            .results h2 { 
                color: #667eea; 
                margin-bottom: 20px; 
                font-size: 1.8em;
            }
            
            .metric { 
                display: inline-block; 
                margin: 10px 20px 10px 0; 
                padding: 10px 15px;
                background: #f8f9ff;
                border-radius: 8px;
                border-left: 4px solid #667eea;
            }
            .metric strong { color: #667eea; font-size: 1.2em; }
            
            .risk-high { color: #e74c3c; font-weight: bold; }
            .risk-medium { color: #f39c12; font-weight: bold; }
            .risk-low { color: #27ae60; }
            
            .loading { 
                color: #667eea; 
                font-style: italic; 
                text-align: center;
                padding: 20px;
            }
            .loading::after {
                content: "...";
                animation: dots 1.5s steps(5, end) infinite;
            }
            @keyframes dots {
                0%, 20% { color: rgba(0,0,0,0); text-shadow: .25em 0 0 rgba(0,0,0,0), .5em 0 0 rgba(0,0,0,0); }
                40% { color: #667eea; text-shadow: .25em 0 0 rgba(0,0,0,0), .5em 0 0 rgba(0,0,0,0); }
                60% { text-shadow: .25em 0 0 #667eea, .5em 0 0 rgba(0,0,0,0); }
                80%, 100% { text-shadow: .25em 0 0 #667eea, .5em 0 0 #667eea; }
            }
            
            .project-card { 
                border-left: 4px solid #667eea; 
                margin: 10px 0; 
                padding: 15px; 
                background: #f8f9ff;
                border-radius: 0 8px 8px 0;
            }
            .recommendation { 
                padding: 15px; 
                margin: 10px 0; 
                border-radius: 8px;
                border-left: 4px solid #f39c12;
                background: #fef9e7;
            }
            .risk-item {
                padding: 12px;
                margin: 8px 0;
                border-radius: 8px;
                background: #fff5f5;
                border-left: 4px solid #e74c3c;
            }
        </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 Defect Intelligence</h1>
                <p>AI-Powered Release Quality Analysis</p>
            </div>
            
            <div class="release-selector">
                <h3>📊 Select Releases to Analyze</h3>
                <select id="release-select" multiple size="3">
                    <!-- Will be populated from API -->
                </select>
                <button id="update-btn" onclick="updateAnalysis()">Update Analysis</button>
            </div>
            
            <div class="trendline-chart">
                <h3>📈 Defect Trend Analysis</h3>
                <canvas id="trendline-chart"></canvas>
            </div>
            
            <div class="actions">
                <button class="action-btn" onclick="analyzeDefects()">🔍 Analyze Selected Releases</button>
                <button class="action-btn openai-btn" onclick="getOpenAIInsights()">🧠 OpenAI Insights</button>
                <button class="action-btn" onclick="trainAI()">🤖 Train AI Models</button>
                <h2>Analysis Results</h2>
                <div id="results-content"></div>
            </div>
        </div>
        
        <script>
            // Initialize on page load
            document.addEventListener('DOMContentLoaded', async () => {
                await loadReleases();
                await loadTrendlineData();
            });
            
            // Load available releases
            async function loadReleases() {
                try {
                    const response = await fetch('/releases');
                    const data = await response.json();
                    
                    const selectElement = document.getElementById('release-select');
                    selectElement.innerHTML = '';
                    
                    if (data.releases && data.releases.length > 0) {
                        data.releases.forEach(release => {
                            const option = document.createElement('option');
                            option.value = release.name;
                            option.textContent = release.name;
                            option.selected = true; // Select all by default
                            selectElement.appendChild(option);
                        });
                    } else {
                        const option = document.createElement('option');
                        option.textContent = 'No releases available';
                        option.disabled = true;
                        selectElement.appendChild(option);
                    }
                } catch (error) {
                    console.error('Error loading releases:', error);
                }
            }
            
            // Load and display trendline chart
            async function loadTrendlineData() {
                try {
                    const selectedReleases = getSelectedReleases();
                    const queryParams = selectedReleases.map(r => `releases=${encodeURIComponent(r)}`).join('&');
                    
                    const response = await fetch(`/trendline?${queryParams}`);
                    const data = await response.json();
                    
                    renderTrendlineChart(data.data);
                } catch (error) {
                    console.error('Error loading trendline data:', error);
                }
            }
            
            // Render trendline chart using Chart.js
            function renderTrendlineChart(trendlineData) {
                const ctx = document.getElementById('trendline-chart').getContext('2d');
                
                // Clear any existing chart
                if (window.trendlineChart) {
                    window.trendlineChart.destroy();
                }
                
                if (!trendlineData || trendlineData.length === 0) {
                    ctx.font = '16px Arial';
                    ctx.fillStyle = '#667eea';
                    ctx.textAlign = 'center';
                    ctx.fillText('No trendline data available', ctx.canvas.width / 2, ctx.canvas.height / 2);
                    return;
                }
                
                const datasets = trendlineData.map((releaseData, index) => {
                    // Generate a color based on index
                    const hue = (index * 137) % 360; // Golden angle approximation for good distribution
                    const color = `hsl(${hue}, 70%, 60%)`;
                    
                    return {
                        label: `Release ${releaseData.release}`,
                        data: releaseData.counts,
                        borderColor: color,
                        backgroundColor: color + '20', // 20% opacity
                        fill: true,
                        tension: 0.4
                    };
                });
                
                // Get all dates from all releases
                const allDates = trendlineData.flatMap(d => d.dates);
                
                window.trendlineChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: allDates.length > 0 ? [...new Set(allDates)].sort() : [],
                        datasets: datasets
                    },
                    options: {
                        responsive: true,
                        plugins: {
                            title: {
                                display: true,
                                text: 'Cumulative Defects Over Time'
                            },
                            tooltip: {
                                mode: 'index',
                                intersect: false
                            },
                        },
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: 'Date'
                                }
                            },
                            y: {
                                title: {
                                    display: true,
                                    text: 'Cumulative Defect Count'
                                },
                                beginAtZero: true
                            }
                        }
                    }
                });
            }
            
            // Get selected releases from the multi-select
            function getSelectedReleases() {
                const selectElement = document.getElementById('release-select');
                return Array.from(selectElement.selectedOptions).map(option => option.value);
            }
            
            // Update analysis based on selected releases
            async function updateAnalysis() {
                await loadTrendlineData();
                analyzeDefects();
            }
            
            async function analyzeDefects() {
                showResults();
                setLoading('Fetching and analyzing defects from JIRA...');
                
                try {
                    const selectedReleases = getSelectedReleases();
                    const queryParams = selectedReleases.map(r => `releases=${encodeURIComponent(r)}`).join('&');
                    
                    const response = await fetch(`/analyze?${queryParams}`);
                    const data = await response.json();
                    displayAnalysisResults(data);
                } catch (error) {
                    showError('Error: ' + error.message);
                }
            }
            
            async function getOpenAIInsights() {
                showResults();
                setLoading('🧠 Getting comprehensive OpenAI insights...');
                
                try {
                    const response = await fetch('/openai-insights');
                    const data = await response.json();
                    displayOpenAIResults(data.analysis);
                } catch (error) {
                    showError('Error: ' + error.message);
                }
            }
            
            async function trainAI() {
                showResults();
                setLoading('Training AI models on defect data...');
                
                try {
                    const response = await fetch('/train', {method: 'POST'});
                    const data = await response.json();
                    showSuccess('✅ ' + data.message);
                } catch (error) {
                    showError('Error: ' + error.message);
                }
            }
            
            async function getRecommendations() {
                showResults();
                setLoading('Generating AI recommendations...');
                
                try {
                    const response = await fetch('/recommendations');
                    const data = await response.json();
                    displayRecommendations(data);
                } catch (error) {
                    showError('Error: ' + error.message);
                }
            }
            
            async function exportData() {
                showResults();
                setLoading('Exporting analysis data...');
                
                try {
                    const response = await fetch('/export');
                    const data = await response.json();
                    showSuccess('✅ Data exported: ' + data.filename);
                } catch (error) {
                    showError('Error: ' + error.message);
                }
            }
            
            function showResults() {
                document.getElementById('results').style.display = 'block';
            }
            
            function setLoading(message) {
                document.getElementById('results-content').innerHTML = 
                    `<div class="loading">${message}</div>`;
            }
            
            function showError(message) {
                document.getElementById('results-content').innerHTML = 
                    `<div style="color: #e74c3c; text-align: center; padding: 20px;">${message}</div>`;
            }
            
            function showSuccess(message) {
                document.getElementById('results-content').innerHTML = 
                    `<div style="color: #27ae60; text-align: center; padding: 20px;">${message}</div>`;
            }
            
            function displayAnalysisResults(data) {
                // Validate data object
                if (!data) {
                    showError('Error: No analysis data received');
                    return;
                }
                
                const summary = data.summary || {};
                const projects = data.projects || {};
                const priorities = data.priorities || {};
                const components = data.components || {};
                const releases = data.releases || {};
                const defects = data.defects || [];
                const aging = data.aging_analysis || {};
                
                let html = '<div class="cards">';
                
                // Summary card
                html += `
                    <div class="card">
                        <h3>📊 Analysis Summary</h3>
                        <div class="metric">Total Defects: <strong>${summary.total_defects || 0}</strong></div>
                        <div class="metric">Resolved: <strong>${summary.resolved_defects || 0}</strong></div>
                        <div class="metric">Resolution Rate: <strong>${summary.resolution_rate || 0}%</strong></div>
                        <div class="metric">Critical Open: <strong>${summary.critical_open || 0}</strong></div>
                        <div class="metric">Releases: <strong>${Array.isArray(summary.releases) ? summary.releases.join(', ') : 'Unknown'}</strong></div>
                    </div>
                `;
                
                // Aging Analysis
                html += `
                    <div class="card">
                        <h3>⏰ Aging Analysis</h3>
                        <div class="metric">Open Issues: <strong>${aging.total_open || 0}</strong></div>
                        <div class="metric">Over 30 days: <strong>${aging.defects_over_30_days || 0}</strong></div>
                        <div class="metric">Over 14 days: <strong>${aging.defects_over_14_days || 0}</strong></div>
                        <div class="metric">Over 7 days: <strong>${aging.defects_over_7_days || 0}</strong></div>
                        <div class="metric">Avg Age (Open): <strong>${Math.round(aging.avg_age_open || 0)} days</strong></div>
                    </div>
                `;
                
                html += '</div>';
                
                // Project breakdown with null checks
                html += '<h3>🏗️ Project Breakdown</h3>';
                if (data.project_breakdown && typeof data.project_breakdown === 'object') {
                    Object.entries(data.project_breakdown).forEach(([project, stats]) => {
                        if (stats) {
                            html += `
                                <div class="project-card">
                                    <strong>${project}</strong>: ${stats.total_defects || 0} total, 
                                    ${stats.open_defects || 0} open, ${stats.critical_defects || 0} critical
                                    (Avg age: ${Math.round(stats.avg_age_days || 0)} days)
                                </div>
                            `;
                        }
                    });
                } else {
                    html += '<div class="project-card">No project breakdown data available</div>';
                }
                
                // Top risks with null checks
                html += '<h3>🚨 Top Risk Defects</h3>';
                if (data.top_risks && Array.isArray(data.top_risks) && data.top_risks.length > 0) {
                    data.top_risks.slice(0, 10).forEach((risk, i) => {
                        if (risk) {
                            const riskScore = risk.ai_risk_score || risk.manual_risk || 0;
                            const riskClass = riskScore > 0.7 ? 'risk-high' : riskScore > 0.4 ? 'risk-medium' : 'risk-low';
                            const summary = risk.summary || 'No summary available';
                            
                            html += `
                                <div class="risk-item">
                                    <div class="${riskClass}">
                                        ${i+1}. <strong>${risk.key || 'Unknown'}</strong> (${risk.project || 'Unknown'}) - Risk: ${(riskScore * 100).toFixed(0)}%
                                    </div>
                                    <div>${summary.substring(0, 80)}${summary.length > 80 ? '...' : ''}</div>
                                    <small>${risk.issue_type || 'Unknown'} | ${risk.priority || 'Unknown'} Priority | ${risk.age_days || 0} days old | ${risk.status || 'Unknown'}</small>
                                </div>
                            `;
                        }
                    });
                } else {
                    html += '<div class="risk-item">No risk data available</div>';
                }
                
                document.getElementById('results-content').innerHTML = html;
            }
            
            function displayOpenAIResults(data) {
                if (!data) {
                    showError('Error: No OpenAI analysis data received');
                    return;
                }
                
                let html = '<div class="cards">';
                
                // Summary metrics
                const summary = data.summary || {};
                html += `
                    <div class="card">
                        <h3>🧠 OpenAI Analysis Summary</h3>
                        <div class="metric">Total Defects Analyzed: <strong>${summary.total_defects || 0}</strong></div>
                        <div class="metric">Projects Affected: <strong>${summary.projects_affected || 0}</strong></div>
                        <div class="metric">Open Defects: <strong>${summary.open_defects || 0}</strong></div>
                        <div class="metric">Critical Issues: <strong>${summary.critical_defects || 0}</strong></div>
                        <div class="metric">Resolution Rate: <strong>${(summary.resolution_rate || 0).toFixed(1)}%</strong></div>
                    </div>
                `;
                
                // OpenAI Insights
                if (data.openai_insights) {
                    const insights = data.openai_insights;
                    
                    // Root Causes
                    if (insights.root_causes && insights.root_causes.length > 0) {
                        html += `
                            <div class="card">
                                <h3>🔍 Root Cause Analysis</h3>
                        `;
                        insights.root_causes.forEach((cause, i) => {
                            html += `
                                <div class="recommendation">
                                    <strong>${i+1}. ${cause.cause || 'Unknown'}</strong><br>
                                    <small>Impact: ${cause.impact || 'Not specified'}</small>
                                </div>
                            `;
                        });
                        html += '</div>';
                    }
                    
                    // High Priority Patterns
                    if (insights.high_priority_patterns && insights.high_priority_patterns.length > 0) {
                        html += `
                            <div class="card">
                                <h3>⚡ High Priority Patterns</h3>
                        `;
                        insights.high_priority_patterns.forEach((pattern, i) => {
                            html += `
                                <div class="recommendation">
                                    <strong>${i+1}. ${pattern.pattern || 'Unknown'}</strong><br>
                                    <small>Severity: ${pattern.severity || 'Not specified'}</small>
                                </div>
                            `;
                        });
                        html += '</div>';
                    }
                    
                    // Component Reliability
                    if (insights.component_reliability && Object.keys(insights.component_reliability).length > 0) {
                        html += `
                            <div class="card">
                                <h3>🔧 Component Reliability</h3>
                        `;
                        Object.entries(insights.component_reliability).forEach(([component, score]) => {
                            const scoreNum = parseFloat(score) || 0;
                            const color = scoreNum > 0.8 ? '#28a745' : scoreNum > 0.6 ? '#ffc107' : '#dc3545';
                            const status = scoreNum > 0.8 ? '🟢 Excellent' : scoreNum > 0.6 ? '🟡 Good' : '🔴 Needs Attention';
                            html += `
                                <div class="metric">
                                    <strong>${component}</strong>: 
                                    <span style="color: ${color}">${(scoreNum * 100).toFixed(1)}% ${status}</span>
                                </div>
                            `;
                        });
                        html += '</div>';
                    }
                    
                    // AI Recommendations
                    if (insights.ai_recommendations && insights.ai_recommendations.length > 0) {
                        html += `
                            <div class="card">
                                <h3>💡 AI Recommendations</h3>
                        `;
                        insights.ai_recommendations.forEach((rec, i) => {
                            html += `
                                <div class="recommendation">
                                    <strong>${i+1}. ${rec.recommendation || 'Unknown'}</strong><br>
                                    <small>Priority: ${rec.priority || 'Not specified'} | Impact: ${rec.impact || 'Not specified'}</small>
                                </div>
                            `;
                        });
                        html += '</div>';
                    }
                }
                
                html += '</div>';
                
                // Enhanced Top Risks
                html += '<h3>🚨 AI-Enhanced Risk Assessment</h3>';
                if (data.top_risks && Array.isArray(data.top_risks) && data.top_risks.length > 0) {
                    data.top_risks.slice(0, 5).forEach((risk, i) => {
                        if (risk) {
                            const riskScore = risk.ai_risk_score || risk.manual_risk || 0;
                            const riskClass = riskScore > 0.7 ? 'risk-high' : riskScore > 0.4 ? 'risk-medium' : 'risk-low';
                            const summary = risk.summary || 'No summary available';
                            
                            html += `
                                <div class="risk-item">
                                    <div class="${riskClass}">
                                        ${i+1}. <strong>${risk.key || 'Unknown'}</strong> (${risk.project || 'Unknown'}) - AI Risk: ${(riskScore * 100).toFixed(0)}%
                                    </div>
                                    <div>${summary.substring(0, 100)}${summary.length > 100 ? '...' : ''}</div>
                                    <small>${risk.issue_type || 'Unknown'} | ${risk.priority || 'Unknown'} Priority | ${risk.age_days || 0} days old | ${risk.status || 'Unknown'}</small>
                                </div>
                            `;
                        }
                    });
                } else {
                    html += '<div class="risk-item">No enhanced risk data available</div>';
                }
                
                document.getElementById('results-content').innerHTML = html;
            }
            
            function displayRecommendations(data) {
                // Validate data object
                if (!data) {
                    showError('Error: No recommendation data received');
                    return;
                }
                
                let html = '<h3>💡 AI Recommendations</h3>';
                
                if (data.recommendations && Array.isArray(data.recommendations) && data.recommendations.length > 0) {
                    data.recommendations.forEach((rec, i) => {
                        if (!rec) return; // Skip null/undefined recommendations
                        
                        const priority = rec.priority || 'Low';
                        const priorityColor = priority === 'High' ? '#e74c3c' : 
                                           priority === 'Medium' ? '#f39c12' : '#27ae60';
                        
                        html += `
                            <div class="recommendation" style="border-left-color: ${priorityColor}">
                                <strong>${priority} Priority:</strong> ${rec.message || 'No message provided'}<br>
                                <strong>Action:</strong> ${rec.action || 'No action specified'}
                                ${rec.count ? `<br><strong>Count:</strong> ${rec.count}` : ''}
                            </div>
                        `;
                    });
                } else {
                    html += '<div style="text-align: center; padding: 20px;">✅ No immediate recommendations</div>';
                }
                
                document.getElementById('results-content').innerHTML = html;
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/analyze")
@app.post("/analyze")
async def analyze_defects(releases: List[str] = Query(None)):
    """Analyze defects from JIRA for specified releases"""
    try:
        # If no releases specified, use default releases
        if not releases:
            releases = Config.DEFAULT_RELEASES
        
        logger.info(f"Starting defect analysis for releases: {releases}")
        
        # Check if analyzer is properly initialized
        if not hasattr(analyzer, 'get_all_release_defects'):
            logger.error("Analyzer not properly initialized")
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"error": "Analyzer not properly initialized"}
            )
        
        # Check if we have data in the database first
        df = db.get_defects(release_names=releases)
        
        if df.empty:
            logger.info("No data in database, fetching from JIRA")
            # For each release, fetch and store defects
            all_defects = []
            
            for release in releases:
                logger.info(f"Fetching defects for release {release}")
                # Temporarily set the analyzer's current release
                analyzer.current_release = release
                
                # Get defects with timeout handling
                try:
                    release_df = analyzer.get_all_release_defects()
                    
                    # Add release column if not present
                    if 'release_name' not in release_df.columns:
                        release_df['release_name'] = release
                    
                    # Store in database.
                    #
                    # This called db.add_defect() row by row. That method does
                    # not exist on DefectDatabase — the name is store_defects
                    # and it takes the whole frame — so the first analysis
                    # against a fresh database raised AttributeError and the
                    # handler below turned it into a 502. The documented
                    # dashboard path could never have worked.
                    db.store_defects(release_df, release)
                    
                    all_defects.append(release_df)
                except Exception as e:
                    logger.error(f"Error fetching defects for release {release}: {str(e)}")
                    return JSONResponse(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        content={"error": f"Failed to fetch defects for release {release}: {str(e)}"}
                    )
            
            # Combine all release dataframes
            if all_defects:
                df = pd.concat(all_defects, ignore_index=True)
            else:
                logger.warning("No defects found in analysis")
                return {"error": "No defects found", "status": "empty_result"}
        else:
            logger.info(f"Using {len(df)} defects from database for {len(releases)} releases")
        
        # Perform comprehensive analysis
        try:
            # Reset analyzer to first release for compatibility with existing code
            if releases:
                analyzer.current_release = releases[0]
                
            analysis = analyzer.comprehensive_analysis(df)
            cached_data['dataframe'] = df
            logger.info(f"Analysis completed successfully with {len(df)} defects")
            
            # Store analysis results in database
            for release in releases:
                release_df = df[df['release_name'] == release] if 'release_name' in df.columns else df
                if not release_df.empty:
                    # Same again: the method is store_analysis_results, and it
                    # takes the results dict rather than pre-counted columns.
                    # The counts here also hard-coded their own idea of which
                    # statuses are finished, disagreeing with Config.
                    db.store_analysis_results(
                        release_name=release,
                        analysis_type="comprehensive",
                        results=analysis,
                    )
        except Exception as e:
            logger.error(f"Error in comprehensive analysis: {str(e)}")
            logger.error(traceback.format_exc())
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": f"Analysis failed: {str(e)}"}
            )
        
        # Handle NaN values for JSON serialization
        def clean_nan(obj):
            if isinstance(obj, dict):
                return {k: clean_nan(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_nan(item) for item in obj]
            elif isinstance(obj, float) and np.isnan(obj):
                return None
            else:
                return obj
        
        # Prepare response with analysis results
        try:
            # Get summary statistics
            total_defects = len(df)
            resolved_defects = len(df[df['status'].isin(['Closed', 'Resolved'])])
            resolution_rate = round((resolved_defects / total_defects * 100), 1) if total_defects > 0 else 0
            
            # Get project statistics
            project_counts = df['project'].value_counts().to_dict()
            
            # Get priority statistics
            priority_counts = df['priority'].value_counts().to_dict()
            
            # Get open critical and blocker bugs
            critical_open = len(df[(df['priority'].isin(['Critical', 'Blocker'])) & 
                                (~df['status'].isin(['Closed', 'Resolved']))])
            
            # Get component statistics
            component_counts = {}
            if 'component' in df.columns:
                component_counts = df['component'].value_counts().to_dict()
            
            # Get release statistics
            release_counts = {}
            if 'release_name' in df.columns:
                release_counts = df['release_name'].value_counts().to_dict()
            
            # Prepare response
            response = {
                "summary": {
                    "total_defects": total_defects,
                    "resolved_defects": resolved_defects,
                    "resolution_rate": resolution_rate,
                    "critical_open": critical_open,
                    "releases": releases
                },
                "projects": project_counts,
                "priorities": priority_counts,
                "components": component_counts,
                "releases": release_counts,
                "defects": clean_nan(df.head(100).to_dict(orient='records')),
                "analysis": clean_nan(analysis)
            }
            
            return response
        except Exception as e:
            logger.error(f"Error preparing response: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "Failed to process analysis results"}
            )
        
    except Exception as e:
        logger.error(f"Unhandled exception in analyze_defects: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/train")
@app.post("/train")
async def train_models():
    """Train AI models"""
    try:
        logger.info("Starting model training")
        
        # Get cached data or fetch new data
        df = cached_data.get('dataframe')
        if df is None or df.empty:
            logger.info("No cached data found, fetching fresh data")
            try:
                df = analyzer.get_all_release_defects()
            except Exception as e:
                logger.error(f"Error fetching defects for training: {str(e)}")
                return JSONResponse(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    content={"error": f"Failed to fetch training data: {str(e)}"}
                )
                
            if df is None or df.empty:
                logger.warning("No defects found for training")
                return {"error": "No defects found for training", "status": "empty_dataset"}
                
            cached_data['dataframe'] = df
        
        # Validate minimum data requirements
        if len(df) < 10:
            logger.warning(f"Insufficient data for training: only {len(df)} records")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "Insufficient data for training", "min_required": 10, "available": len(df)}
            )
        
        # The DefectAnalyzer handles ML training internally during comprehensive_analysis
        try:
            analyzer.comprehensive_analysis(df)  # trains the models in place
            logger.info(f"Model training completed successfully with {len(df)} defects")
            return {"message": f"AI models trained successfully with {len(df)} defects", "status": "success"}
        except Exception as e:
            logger.error(f"Error during model training: {str(e)}")
            logger.error(traceback.format_exc())
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": f"Model training failed: {str(e)}"}
            )
        
    except Exception as e:
        logger.error(f"Unhandled exception in train_models: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/recommendations")
async def get_recommendations():
    """Get AI recommendations"""
    try:
        logger.info("Fetching AI recommendations")
        
        # Get cached data or fetch new data
        df = cached_data.get('dataframe')
        if df is None or df.empty:
            logger.info("No cached data found, fetching fresh data for recommendations")
            try:
                df = analyzer.get_all_release_defects()
            except Exception as e:
                logger.error(f"Error fetching defects for recommendations: {str(e)}")
                return JSONResponse(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    content={"error": f"Failed to fetch data for recommendations: {str(e)}", "recommendations": []}
                )
                
            if df is None or df.empty:
                logger.warning("No defects found for generating recommendations")
                return {"recommendations": [], "status": "no_data"}
                
            cached_data['dataframe'] = df
        
        # Generate recommendations
        try:
            analysis = analyzer.comprehensive_analysis(df)
            logger.info("Comprehensive analysis completed for recommendations")
        except Exception as e:
            logger.error(f"Error generating recommendations: {str(e)}")
            logger.error(traceback.format_exc())
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": f"Failed to generate recommendations: {str(e)}", "recommendations": []}
            )
        
        # Handle NaN values for JSON serialization
        def clean_nan(obj):
            if isinstance(obj, dict):
                return {k: clean_nan(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_nan(item) for item in obj]
            elif isinstance(obj, float) and np.isnan(obj):
                return None
            else:
                return obj
        
        # Clean the recommendations
        try:
            recommendations = analysis.get('recommendations', [])
            if not recommendations:
                logger.warning("No recommendations found in analysis results")
                
            clean_recommendations = clean_nan(recommendations)
            logger.info(f"Successfully processed {len(clean_recommendations)} recommendations")
            
            return {"recommendations": clean_recommendations, "count": len(clean_recommendations)}
        except Exception as e:
            logger.error(f"Error processing recommendations: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "Failed to process recommendations", "recommendations": []}
            )
        
    except Exception as e:
        logger.error(f"Unhandled exception in get_recommendations: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/openai-insights")
async def get_openai_insights():
    """Get comprehensive OpenAI-powered defect analysis"""
    try:
        logger.info("Starting OpenAI comprehensive analysis")
        
        # Get ALL defects for comprehensive analysis
        df = analyzer.get_all_release_defects()
        if df.empty:
            logger.warning("No defects found for OpenAI analysis")
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": "No defects found", "status": "no_data"}
            )
        
        logger.info(f"Performing comprehensive OpenAI analysis on {len(df)} defects")
        
        # Perform comprehensive analysis with OpenAI insights
        analysis = analyzer.comprehensive_analysis(df)
        
        # Cache the results
        cached_data['openai_analysis'] = analysis
        cached_data['openai_timestamp'] = pd.Timestamp.now()
        
        logger.info("OpenAI analysis completed successfully")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "timestamp": pd.Timestamp.now().isoformat(),
                "analysis": analysis
            }
        )
        
    except Exception as e:
        logger.error(f"Unhandled exception in get_openai_insights: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/export")
async def export_data():
    """Export analysis data"""
    try:
        logger.info("Starting data export process")
        
        # Check for cached data
        df = cached_data.get('dataframe')
        if df is None or df.empty:
            logger.warning("No data available for export")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "No data to export", "status": "no_data"}
            )
        
        # Generate comprehensive analysis
        try:
            analysis = analyzer.comprehensive_analysis(df)
            logger.info("Comprehensive analysis completed for export")
        except Exception as e:
            logger.error(f"Error generating analysis for export: {str(e)}")
            logger.error(traceback.format_exc())
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": f"Failed to generate analysis for export: {str(e)}"}
            )
        
        # Handle NaN values for JSON serialization
        def clean_nan(obj):
            if isinstance(obj, dict):
                return {k: clean_nan(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_nan(item) for item in obj]
            elif isinstance(obj, float) and np.isnan(obj):
                return None
            else:
                return obj
        
        # Clean the analysis results
        try:
            clean_analysis = clean_nan(analysis)
            logger.info("Successfully cleaned analysis results for export")
        except Exception as e:
            logger.error(f"Error cleaning analysis for export: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "Failed to process analysis results for export"}
            )
        
        # Save the cleaned analysis
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"defect_analysis_{analyzer.current_release}_{timestamp}"
            
            analyzer.save_comprehensive_report(df, clean_analysis, filename)
            logger.info(f"Data successfully exported to {filename}")
            
            return {
                "message": "Data exported successfully", 
                "filename": filename,
                "records": len(df),
                "timestamp": timestamp
            }
        except Exception as e:
            logger.error(f"Error saving export files: {str(e)}")
            logger.error(traceback.format_exc())
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": f"Failed to save export files: {str(e)}"}
            )
        
    except Exception as e:
        logger.error(f"Unhandled exception in export_data: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/releases")
async def get_releases():
    """Get all available releases"""
    try:
        releases = db.get_releases(active_only=True)
        return {"releases": releases}
    except Exception as e:
        logger.error(f"Error getting releases: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/trendline")
async def get_trendline_data(releases: List[str] = Query(None)):
    """Get trendline data for specified releases"""
    try:
        if not releases:
            releases = Config.DEFAULT_RELEASES
        
        # Get defects for all specified releases
        df = db.get_defects(release_names=releases)
        
        if df.empty:
            return {"message": "No data available for the specified releases", "data": []}
        
        # Convert created_date to datetime if it's not already
        df['created_date'] = pd.to_datetime(df['created_date'])
        
        # Group by release and date, count defects
        trendline_data = []
        
        for release in releases:
            release_df = df[df['release_name'] == release]
            if not release_df.empty:
                # Group by date and count
                daily_counts = release_df.groupby(release_df['created_date'].dt.date).size()
                
                # Two series, because they answer different questions and one
                # of them was being asked to answer both.
                #
                # A cumulative count only ever rises — that is what cumulative
                # means — so reading a trend direction off it was meaningless:
                # every release "trended upward" including one where defect
                # discovery had stopped completely. `daily` is the series that
                # can actually fall.
                cumulative = daily_counts.cumsum()

                release_data = {
                    "release": release,
                    "dates": [d.strftime("%Y-%m-%d") for d in cumulative.index],
                    "counts": cumulative.tolist(),      # total found so far
                    "daily_counts": daily_counts.tolist(),  # found that day
                }
                trendline_data.append(release_data)
        
        return {"data": trendline_data}
    except Exception as e:
        logger.error(f"Error getting trendline data: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check if analyzer is properly initialized
        if not hasattr(analyzer, 'current_release'):
            logger.warning("Analyzer not properly initialized during health check")
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "degraded", "message": "Analyzer not properly initialized"}
            )
            
        # Check if we can access JIRA
        jira_status = "available"
        try:
            # Simple test to see if JIRA connection works
            _ = analyzer.jira.server_info()
        except Exception as e:
            logger.warning(f"JIRA connection issue during health check: {str(e)}")
            jira_status = "unavailable"
        
        # Check if ML predictor is initialized
        ml_status = "available" if hasattr(analyzer, 'ml_predictor') else "unavailable"
        
        # Check database status
        db_stats = db.get_database_stats()
        
        return {
            "status": "healthy",
            "release": analyzer.current_release,
            "services": {
                "jira": jira_status,
                "ml_predictor": ml_status,
                "database": "available"
            },
            "database": {
                "active_releases": db_stats['active_releases'],
                "total_defects": db_stats['total_defects']
            },
            "cache": {
                "has_data": cached_data.get('dataframe') is not None
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "unhealthy", "error": str(e)}
        )

if __name__ == "__main__":
    port = 8002  # Using a different port
    print("🚀 Starting Defect Intelligence Dashboard...")
    print(f"📊 Access dashboard at: http://localhost:{port}")
    print(f"🔗 API docs at: http://localhost:{port}/docs")
    
    try:
        uvicorn.run(app, host="0.0.0.0", port=port)
    except Exception as e:
        logger.critical(f"Failed to start server: {str(e)}")
        logger.critical(traceback.format_exc())
        print(f"❌ Critical error: {str(e)}")