import json
import os

def generate_html_report(report_path, output_html):
    with open(report_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    metrics = data['metrics']
    agents = data['agents']
    
    # Calculate Chart.js data
    metric_labels = list(metrics.keys())
    metric_values = [metrics[k] for k in metric_labels]

    agent_cards = ""
    for agent in agents:
        keywords = "".join([f'<span class="badge bg-secondary me-1">{k}</span>' for k in agent['spatial_keywords']])
        agent_cards += f"""
        <div class="col-md-4 mb-3">
            <div class="card h-100 shadow-sm">
                <div class="card-header bg-light">
                    <h6 class="mb-0 text-primary">Agent {agent['id']}: {agent['paradigm'].split('(')[0]}</h6>
                </div>
                <div class="card-body">
                    <p class="small text-muted mb-2">"{agent['narrative'][:120]}..."</p>
                    <div class="mb-2">{keywords}</div>
                </div>
            </div>
        </div>
        """

    mood_items = "".join([f'<li class="list-group-item small text-muted italic">"{mood}"</li>' for mood in data['mood_board']])

    # Deliberation Log rendering
    deliberation_rows = ""
    for log in data.get('deliberation_log', []):
        deliberation_rows += f"""
        <tr>
            <td class="fw-bold">{log['topic']}</td>
            <td class="text-danger small">{log['conflict']}</td>
            <td class="text-success small">{log['resolution']}</td>
        </tr>
        """
    
    deliberation_section = f"""
    <div class="card shadow-sm mb-5">
        <div class="card-body">
            <h4 class="card-title pb-2 border-bottom text-primary">Deliberation Process: Expert Consensus Negotiation</h4>
            <div class="table-responsive">
                <table class="table table-hover mt-3">
                    <thead class="table-light">
                        <tr>
                            <th style="width: 20%">Topic</th>
                            <th style="width: 40%">Conflict / Tension</th>
                            <th style="width: 40%">Consensus Resolution</th>
                        </tr>
                    </thead>
                    <tbody>
                        {deliberation_rows}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    """

    # Site Statistics rendering
    site_info = data.get('spatial_metadata', {}).get('site_info', {})
    site_stats_html = ""
    if site_info:
        site_stats_html = f"""
        <div class="mt-4 p-3 bg-light rounded border">
            <h6 class="text-secondary border-bottom pb-1">Site Context Analysis</h6>
            <div class="row small">
                <div class="col-6">Buildings: <strong>{site_info.get('building_count')}</strong></div>
                <div class="col-6">Roads: <strong>{site_info.get('road_count')}</strong></div>
                <div class="col-12 mt-1">Total Build Area: <strong>{site_info.get('total_building_area', 0):,.0f} m²</strong></div>
            </div>
        </div>
        """

    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>DeGIM Project Evaluation Report</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ background-color: #f8f9fa; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
            .metric-card {{ border-left: 5px solid #0d6efd; }}
            .svg-container {{ background: #f8f9fa; padding: 10px; border-radius: 8px; border: 1px solid #ddd; }}
            .svg-container svg {{ width: 100%; height: auto; max-height: 500px; }}
            .shared-narrative {{ line-height: 1.6; text-align: justify; font-style: italic; color: #444; }}
            .badge {{ font-size: 0.75rem; font-weight: normal; }}
            tr:hover {{ background-color: rgba(13, 110, 253, 0.05); }}
        </style>
    </head>
    <body>
        <div class="container py-5">
            <header class="mb-5 text-center">
                <h1 class="display-4 fw-bold text-dark">DeGIM</h1>
                <p class="lead text-muted">Design Group Intelligence Modeling Report</p>
                <div class="badge bg-primary px-3 py-2">Task: {data['task']}</div>
            </header>

            <div class="row mb-5">
                <div class="col-lg-7">
                    <div class="card shadow-sm h-100">
                        <div class="card-body">
                            <h4 class="card-title pb-2 border-bottom">Layer 2: Spatial Topology</h4>
                            <div class="svg-container text-center mt-3">
                                {data['svg_xml']}
                            </div>
                            <p class="mt-3 text-muted small">Generated Strategic Constraint Graph reflecting synthesized spatial logic.</p>
                        </div>
                    </div>
                </div>
                <div class="col-lg-5">
                    <div class="card shadow-sm h-100">
                        <div class="card-body">
                            <h4 class="card-title pb-2 border-bottom">Performance Metrics</h4>
                            <div style="max-width: 300px; margin: 0 auto;">
                                <canvas id="radarChart"></canvas>
                            </div>
                            <div class="mt-4 row text-center">
                                <div class="col-6 mb-3">
                                    <div class="p-2 border rounded metric-card">
                                        <div class="small text-muted">CD (Consensus)</div>
                                        <div class="h4 mb-0">{metrics['CD']:.2f}</div>
                                    </div>
                                </div>
                                <div class="col-6 mb-3">
                                    <div class="p-2 border rounded metric-card" style="border-left-color: #198754;">
                                        <div class="small text-muted">CS (Coherence)</div>
                                        <div class="h4 mb-0">{metrics['CS']:.2f}</div>
                                    </div>
                                </div>
                                <div class="col-6">
                                    <div class="p-2 border rounded metric-card" style="border-left-color: #ffc107;">
                                        <div class="small text-muted">PD (Diversity)</div>
                                        <div class="h4 mb-0">{metrics['PD']:.2f}</div>
                                    </div>
                                </div>
                                <div class="col-6">
                                    <div class="p-2 border rounded metric-card" style="border-left-color: #dc3545;">
                                        <div class="small text-muted">CLC (Overall)</div>
                                        <div class="h4 mb-0 fw-bold">{metrics['CLC']:.2f}</div>
                                    </div>
                                </div>
                            </div>
                            {site_stats_html}
                        </div>
                    </div>
                </div>
            </div>

            {deliberation_section}

            <div class="row mb-5">
                <div class="col-md-6">
                    <div class="card shadow-sm h-100">
                        <div class="card-body">
                            <h4 class="card-title pb-2 border-bottom">Layer 1: Shared Narrative</h4>
                            <div class="shared-narrative p-3 bg-white rounded border mt-3">
                                {data['shared_narrative']}
                            </div>
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="card shadow-sm h-100">
                        <div class="card-body">
                            <h4 class="card-title pb-2 border-bottom">Layer 3: Collective Mood Board</h4>
                            <ul class="list-group list-group-flush mt-3">
                                {mood_items}
                            </ul>
                        </div>
                    </div>
                </div>
            </div>

            <h4 class="mb-4 border-bottom pb-2 text-dark">Heterogeneous Agent Gallery (N=12)</h4>
            <div class="row">
                {agent_cards}
            </div>
            
            <footer class="mt-5 pt-4 border-top text-center text-muted">
                <p>DeGIM | Collaborative AI Design Framework v1.0</p>
            </footer>
        </div>

        <script>
            const ctx = document.getElementById('radarChart').getContext('2d');
            new Chart(ctx, {{
                type: 'radar',
                data: {{
                    labels: {json.dumps(metric_labels)},
                    datasets: [{{
                        label: 'Metrics Score',
                        data: {json.dumps(metric_values)},
                        fill: true,
                        backgroundColor: 'rgba(13, 110, 253, 0.2)',
                        borderColor: 'rgb(13, 110, 253)',
                        pointBackgroundColor: 'rgb(13, 110, 253)',
                        pointBorderColor: '#fff',
                        pointHoverBackgroundColor: '#fff',
                        pointHoverBorderColor: 'rgb(13, 110, 253)'
                    }}]
                }},
                options: {{
                    scales: {{
                        r: {{
                            angleLines: {{ display: true }},
                            suggestedMin: 0,
                            suggestedMax: 1
                        }}
                    }},
                    plugins: {{ legend: {{ display: false }} }}
                }}
            }});
        </script>
    </body>
    </html>
    """
    
    with open(output_html, 'w', encoding='utf-8') as f:
        f.write(html_template)
    print(f"Visualization report generated at: {output_html}")

if __name__ == "__main__":
    report_file = "d:/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/outputs/degim_report.json"
    output_file = "d:/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/outputs/visualization.html"
    generate_html_report(report_file, output_file)
