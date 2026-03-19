"""
charts.py — Matplotlib charts and interactive vis.js network graph.
"""
import json
import math
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from config import (ACCENT, ACCENT2, PURPLE, WARN, DANGER,
                    TEXT, DARK, CARD, BORDER, MUTED, BG)


def hbar_chart(labels, values, color, title, xlabel):
    fig, ax = plt.subplots(figsize=(7, max(2.5, len(labels) * 0.42)))
    bars = ax.barh(labels[::-1], values[::-1],
                   color=color if isinstance(color, list) else [color] * len(labels),
                   height=0.65)
    for bar, val in zip(bars, values[::-1]):
        ax.text(bar.get_width() + max(values) * 0.01,
                bar.get_y() + bar.get_height() / 2,
                str(val), va="center", color=TEXT, fontsize=8)
    ax.set_xlabel(xlabel)
    ax.set_title(title, fontsize=11, fontweight="bold", color=TEXT, pad=10)
    ax.set_xlim(0, max(values) * 1.2)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    return fig


def time_series_chart(df):
    if "visit_date" not in df.columns:
        return None
    s = df["visit_date"].dropna()
    if len(s) < 2:
        return None
    monthly = s.dt.to_period("M").value_counts().sort_index()
    dates, vals = [str(p) for p in monthly.index], monthly.values
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.fill_between(range(len(vals)), vals, alpha=0.2, color=ACCENT)
    ax.plot(range(len(vals)), vals, color=ACCENT, linewidth=2, marker="o", markersize=4)
    step = max(1, len(dates) // 12)
    ax.set_xticks(range(0, len(dates), step))
    ax.set_xticklabels(dates[::step], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Visits")
    ax.set_title("Monthly Visit Volume", fontsize=11, fontweight="bold", color=TEXT, pad=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    return fig


def rapid_histogram(rapid):
    if not rapid:
        return None
    days = [r["days_apart"] for r in rapid]
    fig, ax = plt.subplots(figsize=(6, 3))
    bins = list(range(1, max(days) + 2))
    _, bins_out, patches = ax.hist(days, bins=bins, color=WARN, edgecolor=CARD, rwidth=0.8)
    for patch, left in zip(patches, bins_out):
        if left <= 2:
            patch.set_facecolor(DANGER)
    ax.set_xlabel("Days Between Visits")
    ax.set_ylabel("Cases")
    ax.set_title("Rapid Revisit Distribution", fontsize=11, fontweight="bold", color=TEXT, pad=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(handles=[mpatches.Patch(color=DANGER, label="≤2 days"),
                        mpatches.Patch(color=WARN,   label="3+ days")],
              fontsize=8, facecolor=CARD, edgecolor=BORDER, labelcolor=TEXT)
    fig.tight_layout()
    return fig


def build_network_data(df: pd.DataFrame, col_a: str, col_b: str,
                       max_nodes: int, min_edge_weight: int):
    """
    Build graph data for vis.js interactive rendering.
    Returns (vis_nodes, vis_edges, stats) or (None, None, {}).
    """
    sub = df[[col_a, col_b]].dropna()
    if len(sub) == 0:
        return None, None, {}

    G = nx.Graph()
    edge_w: dict = {}
    for _, row in sub.iterrows():
        a, b = str(row[col_a]), str(row[col_b])
        G.add_node(a, side="A")
        G.add_node(b, side="B")
        key = (a, b)
        edge_w[key] = edge_w.get(key, 0) + 1

    for (a, b), w in edge_w.items():
        if w >= min_edge_weight:
            G.add_edge(a, b, weight=w)

    G.remove_nodes_from(list(nx.isolates(G)))

    if len(G.nodes) == 0:
        return None, None, {}

    # Prune to top nodes by degree
    if len(G.nodes) > max_nodes:
        top = sorted(G.degree(), key=lambda x: x[1], reverse=True)[:max_nodes]
        G = G.subgraph([n for n, _ in top]).copy()

    nodes_a = [n for n, d in G.nodes(data=True) if d.get("side") == "A"]
    nodes_b = [n for n, d in G.nodes(data=True) if d.get("side") == "B"]
    degrees = dict(G.degree())
    max_deg = max(degrees.values()) if degrees else 1

    col_a_lbl = col_a.replace("_", " ").title()
    col_b_lbl = col_b.replace("_", " ").title()

    # Build vis.js nodes list
    vis_nodes = []
    for n, data in G.nodes(data=True):
        deg = degrees.get(n, 1)
        is_a = data.get("side") == "A"
        size = max(14, min(50, 10 + deg * 4)) if is_a else max(8, min(30, 6 + deg * 2))
        vis_nodes.append({
            "id":    n,
            "label": str(n)[:20] + ("…" if len(str(n)) > 20 else ""),
            "title": f"<b>{n}</b><br>Type: {col_a_lbl if is_a else col_b_lbl}<br>Connections: {deg}",
            "color": {
                "background":  "#00e5a0" if is_a else "#0ea5e9",
                "border":      "#00b87a" if is_a else "#0284c7",
                "highlight":   {"background": "#ffffff", "border": "#00e5a0" if is_a else "#0ea5e9"},
                "hover":       {"background": "#f0fdf4" if is_a else "#e0f2fe",
                                "border":     "#00e5a0" if is_a else "#0ea5e9"},
            },
            "shape": "diamond" if is_a else "dot",
            "size":  size,
            "font":  {"color": "#e2e8f0", "size": 11, "face": "DM Mono, monospace"},
            "group": "A" if is_a else "B",
            "degree": deg,
        })

    # Build vis.js edges list
    max_w = max((G[u][v].get("weight", 1) for u, v in G.edges()), default=1)
    vis_edges = []
    for i, (u, v, data) in enumerate(G.edges(data=True)):
        w = data.get("weight", 1)
        vis_edges.append({
            "id":     i,
            "from":   u,
            "to":     v,
            "weight": w,
            "width":  max(0.5, min(6, 0.5 + 4 * (w / max_w))),
            "color":  {
                "color":     "rgba(100,116,139,0.35)",
                "highlight": "#00e5a0",
                "hover":     "#f59e0b",
            },
            "title":  f"Co-occurrences: {w}",
            "smooth": {"type": "dynamic"},
        })

    stats = {
        "nodes_a":    len(nodes_a),
        "nodes_b":    len(nodes_b),
        "edges":      len(vis_edges),
        "density":    round(nx.density(G), 4),
        "avg_degree": round(sum(degrees.values()) / max(1, len(degrees)), 2),
        "top_a": sorted([(n, degrees[n]) for n in nodes_a], key=lambda x: -x[1])[:10],
        "top_b": sorted([(n, degrees[n]) for n in nodes_b], key=lambda x: -x[1])[:10],
        "col_a_lbl": col_a_lbl,
        "col_b_lbl": col_b_lbl,
    }
    return vis_nodes, vis_edges, stats


def render_vis_network(vis_nodes, vis_edges, stats, physics_mode: str, height: int = 680):
    """Render an interactive vis.js network via st.components.v1.html()."""
    import json
    import streamlit.components.v1 as components

    nodes_json = json.dumps(vis_nodes)
    edges_json = json.dumps(vis_edges)
    col_a_lbl  = stats.get("col_a_lbl", "Node A")
    col_b_lbl  = stats.get("col_b_lbl", "Node B")
    n_a = stats.get("nodes_a", 0)
    n_b = stats.get("nodes_b", 0)

    physics_opts = {
        "Force Atlas 2": json.dumps({
            "solver": "forceAtlas2Based",
            "forceAtlas2Based": {"gravitationalConstant": -60, "centralGravity": 0.01,
                                  "springLength": 120, "springConstant": 0.08, "damping": 0.4},
            "stabilization": {"iterations": 150},
        }),
        "Barnes-Hut": json.dumps({
            "solver": "barnesHut",
            "barnesHut": {"gravitationalConstant": -8000, "centralGravity": 0.3,
                           "springLength": 140, "springConstant": 0.04, "damping": 0.09},
            "stabilization": {"iterations": 150},
        }),
        "Repulsion": json.dumps({
            "solver": "repulsion",
            "repulsion": {"centralGravity": 0.2, "springLength": 200,
                           "springConstant": 0.05, "nodeDistance": 150, "damping": 0.09},
            "stabilization": {"iterations": 150},
        }),
        "None (static)": json.dumps({"enabled": False}),
    }
    physics_json = physics_opts.get(physics_mode, physics_opts["Force Atlas 2"])

    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.js"></script>
<link  href="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.css" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #080c10; font-family: 'DM Mono', monospace; color: #e2e8f0; overflow: hidden; }}

  #net-wrap {{ position: relative; width: 100%; height: {height}px; background: #0d1117;
               border: 1px solid #1e2a38; border-radius: 12px; overflow: hidden; }}
  #network  {{ width: 100%; height: 100%; }}

  /* Toolbar */
  #toolbar {{
    position: absolute; top: 12px; left: 12px; z-index: 10;
    display: flex; gap: 8px; flex-wrap: wrap; align-items: center;
  }}
  .tb-btn {{
    background: rgba(17,23,32,.92); border: 1px solid #1e2a38;
    color: #e2e8f0; border-radius: 7px; padding: 6px 12px;
    font-size: 11px; font-family: monospace; cursor: pointer;
    transition: all .15s; backdrop-filter: blur(4px);
  }}
  .tb-btn:hover {{ border-color: #00e5a0; color: #00e5a0; }}
  .tb-btn.active {{ background: rgba(0,229,160,.12); border-color: #00e5a0; color: #00e5a0; }}
  .tb-sep {{ width: 1px; height: 22px; background: #1e2a38; }}

  /* Search box */
  #search-wrap {{ position: absolute; top: 12px; right: 12px; z-index: 10; display: flex; gap: 6px; }}
  #node-search {{
    background: rgba(17,23,32,.92); border: 1px solid #1e2a38;
    color: #e2e8f0; border-radius: 7px; padding: 6px 12px;
    font-size: 11px; font-family: monospace; width: 180px; outline: none;
    backdrop-filter: blur(4px);
  }}
  #node-search:focus {{ border-color: #00e5a0; }}
  #node-search::placeholder {{ color: #64748b; }}

  /* Legend */
  #legend {{
    position: absolute; bottom: 14px; left: 14px; z-index: 10;
    background: rgba(13,17,23,.88); border: 1px solid #1e2a38;
    border-radius: 10px; padding: 10px 14px; backdrop-filter: blur(4px);
    font-size: 11px;
  }}
  .leg-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }}
  .leg-row:last-child {{ margin-bottom: 0; }}
  .leg-dot {{ width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0; }}
  .leg-dia {{ width: 10px; height: 10px; transform: rotate(45deg); flex-shrink: 0; border-radius: 1px; }}

  /* Stats bar */
  #stats-bar {{
    position: absolute; bottom: 14px; right: 14px; z-index: 10;
    background: rgba(13,17,23,.88); border: 1px solid #1e2a38;
    border-radius: 10px; padding: 10px 14px; backdrop-filter: blur(4px);
    font-size: 11px; color: #64748b; line-height: 1.7;
  }}
  #stats-bar b {{ color: #e2e8f0; }}

  /* Tooltip override */
  .vis-tooltip {{
    background: #111720 !important; border: 1px solid #1e2a38 !important;
    color: #e2e8f0 !important; border-radius: 8px !important;
    font-family: 'DM Mono', monospace !important; font-size: 12px !important;
    padding: 8px 12px !important; box-shadow: 0 4px 20px rgba(0,0,0,.4) !important;
  }}

  /* Selected info panel */
  #info-panel {{
    display: none; position: absolute; top: 56px; right: 12px; z-index: 10;
    background: rgba(13,17,23,.95); border: 1px solid #1e2a38;
    border-radius: 10px; padding: 14px 16px; font-size: 12px;
    min-width: 200px; max-width: 260px; backdrop-filter: blur(4px);
  }}
  #info-panel .ip-name {{ font-size: 14px; font-weight: 700; color: #e2e8f0; margin-bottom: 6px; word-break: break-all; }}
  #info-panel .ip-row  {{ display: flex; justify-content: space-between; margin-bottom: 3px; }}
  #info-panel .ip-lbl  {{ color: #64748b; }}
  #info-panel .ip-val  {{ color: #e2e8f0; font-weight: 600; }}
  #info-panel .ip-close {{ float: right; cursor: pointer; color: #64748b; font-size: 14px; margin-left: 8px; }}
  #info-panel .ip-close:hover {{ color: #ef4444; }}
  #info-panel .ip-nbrs {{ margin-top: 8px; border-top: 1px solid #1e2a38; padding-top: 8px; }}
  #info-panel .ip-nbr  {{ color: #64748b; font-size: 11px; margin-bottom: 2px; }}

  #stabilizing {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%);
    background: rgba(13,17,23,.9); border: 1px solid #1e2a38; border-radius: 10px;
    padding: 16px 24px; font-size: 13px; color: #00e5a0; z-index: 20;
    display: flex; align-items: center; gap: 10px; }}
  .spin {{ width: 16px; height: 16px; border: 2px solid rgba(0,229,160,.2);
    border-top-color: #00e5a0; border-radius: 50%; animation: spin .7s linear infinite; }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
</style>
</head>
<body>

<div id="net-wrap">
  <div id="stabilizing"><div class="spin"></div> Laying out graph…</div>

  <div id="toolbar">
    <button class="tb-btn" onclick="zoomIn()">＋</button>
    <button class="tb-btn" onclick="zoomOut()">－</button>
    <button class="tb-btn" onclick="fitAll()">⊡ Fit</button>
    <div class="tb-sep"></div>
    <button class="tb-btn" id="btn-physics" onclick="togglePhysics()">⏸ Freeze</button>
    <button class="tb-btn" onclick="highlightHubs()">★ Hubs</button>
    <button class="tb-btn" onclick="resetHighlight()">↺ Reset</button>
    <div class="tb-sep"></div>
    <button class="tb-btn" id="btn-labels" onclick="toggleLabels()">🏷 Labels</button>
  </div>

  <div id="search-wrap">
    <input id="node-search" placeholder="🔍 Search node…" oninput="searchNode(this.value)">
  </div>

  <div id="network"></div>

  <div id="info-panel">
    <div><span class="ip-close" onclick="closeInfo()">✕</span><div class="ip-name" id="ip-name"></div></div>
    <div class="ip-row"><span class="ip-lbl">Type</span><span class="ip-val" id="ip-type"></span></div>
    <div class="ip-row"><span class="ip-lbl">Connections</span><span class="ip-val" id="ip-deg"></span></div>
    <div class="ip-nbrs"><div style="color:#64748b;font-size:10px;margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px">Connected to</div>
      <div id="ip-nbr-list"></div>
    </div>
  </div>

  <div id="legend">
    <div class="leg-row"><div class="leg-dia" style="background:#00e5a0"></div><span>{col_a_lbl} ({n_a})</span></div>
    <div class="leg-row"><div class="leg-dot" style="background:#0ea5e9"></div><span>{col_b_lbl} ({n_b})</span></div>
  </div>

  <div id="stats-bar">
    <div><b>{stats["nodes_a"] + stats["nodes_b"]}</b> nodes</div>
    <div><b>{stats["edges"]}</b> edges</div>
    <div>avg degree <b>{stats["avg_degree"]}</b></div>
    <div>density <b>{stats["density"]}</b></div>
  </div>
</div>

<script>
const nodesData = {nodes_json};
const edgesData = {edges_json};

// Build lookup maps
const nodeMap = {{}};
nodesData.forEach(n => nodeMap[n.id] = n);

const adjMap = {{}};
edgesData.forEach(e => {{
  if (!adjMap[e.from]) adjMap[e.from] = [];
  if (!adjMap[e.to])   adjMap[e.to]   = [];
  adjMap[e.from].push({{id: e.to,   w: e.weight}});
  adjMap[e.to].push(  {{id: e.from, w: e.weight}});
}});

const nodes = new vis.DataSet(nodesData);
const edges = new vis.DataSet(edgesData);

const container = document.getElementById('network');
const physicsConfig = {physics_json};

const options = {{
  nodes: {{ borderWidth: 1.5, shadow: {{ enabled: true, color: 'rgba(0,0,0,.5)', x: 2, y: 2, size: 8 }} }},
  edges: {{ smooth: {{ type: 'dynamic' }}, shadow: false, selectionWidth: 3 }},
  physics: physicsConfig,
  interaction: {{
    hover: true, tooltipDelay: 150,
    navigationButtons: false,
    keyboard: true,
    multiselect: true,
    zoomView: true,
  }},
  layout: {{ improvedLayout: true }},
}};

const network = new vis.Network(container, {{ nodes, edges }}, options);

// Hide spinner once stabilised
network.on('stabilizationIterationsDone', () => {{
  document.getElementById('stabilizing').style.display = 'none';
  network.setOptions({{ physics: {{ enabled: false }} }});
  document.getElementById('btn-physics').textContent = '▶ Unfreeze';
  physicsRunning = false;
}});
network.on('stabilized', () => {{
  document.getElementById('stabilizing').style.display = 'none';
}});

// State
let physicsRunning = true;
let labelsVisible  = true;
let hubsHighlighted = false;

// ── Controls ──
function zoomIn()  {{ network.moveTo({{ scale: network.getScale() * 1.3, animation: true }}); }}
function zoomOut() {{ network.moveTo({{ scale: network.getScale() * 0.77, animation: true }}); }}
function fitAll()  {{ network.fit({{ animation: {{ duration: 600, easingFunction: 'easeInOutQuad' }} }}); }}

function togglePhysics() {{
  physicsRunning = !physicsRunning;
  network.setOptions({{ physics: {{ enabled: physicsRunning }} }});
  document.getElementById('btn-physics').textContent = physicsRunning ? '⏸ Freeze' : '▶ Unfreeze';
  document.getElementById('btn-physics').classList.toggle('active', physicsRunning);
}}

function toggleLabels() {{
  labelsVisible = !labelsVisible;
  const update = nodesData.map(n => ({{
    id: n.id,
    font: {{ ...n.font, color: labelsVisible ? '#e2e8f0' : 'rgba(0,0,0,0)' }}
  }}));
  nodes.update(update);
  document.getElementById('btn-labels').classList.toggle('active', labelsVisible);
}}

function highlightHubs() {{
  hubsHighlighted = !hubsHighlighted;
  if (hubsHighlighted) {{
    const maxDeg = Math.max(...nodesData.map(n => n.degree));
    const thresh = maxDeg * 0.5;
    const update = nodesData.map(n => ({{
      id: n.id,
      opacity: n.degree >= thresh ? 1.0 : 0.15,
    }}));
    nodes.update(update);
  }} else {{
    resetHighlight();
  }}
}}

function resetHighlight() {{
  hubsHighlighted = false;
  nodes.update(nodesData.map(n => ({{ id: n.id, opacity: 1.0 }})));
  document.getElementById('node-search').value = '';
}}

function searchNode(q) {{
  q = q.trim().toLowerCase();
  if (!q) {{ resetHighlight(); return; }}
  const update = nodesData.map(n => ({{
    id: n.id,
    opacity: n.id.toLowerCase().includes(q) ? 1.0 : 0.1,
  }}));
  nodes.update(update);
  // Focus first match
  const match = nodesData.find(n => n.id.toLowerCase().includes(q));
  if (match) {{
    network.focus(match.id, {{ scale: 1.4, animation: {{ duration: 600, easingFunction: 'easeInOutQuad' }} }});
  }}
}}

// ── Click → info panel ──
network.on('click', params => {{
  if (params.nodes.length === 1) {{
    const nid = params.nodes[0];
    const nd  = nodeMap[nid];
    if (!nd) return;
    document.getElementById('ip-name').textContent = nid;
    document.getElementById('ip-type').textContent = nd.group === 'A' ? '{col_a_lbl}' : '{col_b_lbl}';
    document.getElementById('ip-deg').textContent  = nd.degree;
    const nbrs = (adjMap[nid] || []).sort((a,b) => b.w - a.w).slice(0, 10);
    document.getElementById('ip-nbr-list').innerHTML =
      nbrs.map(n => `<div class="ip-nbr">• ${{n.id.length > 24 ? n.id.slice(0,24)+'…' : n.id}} <span style="color:#00e5a0">×${{n.w}}</span></div>`).join('');
    document.getElementById('info-panel').style.display = 'block';

    // Dim non-neighbours
    const connectedIds = new Set([nid, ...nbrs.map(n => n.id)]);
    nodes.update(nodesData.map(n => ({{ id: n.id, opacity: connectedIds.has(n.id) ? 1.0 : 0.1 }})));
    edges.update(edgesData.map(e => ({{
      id: e.id,
      color: {{
        color: (e.from === nid || e.to === nid) ? '#00e5a0' : 'rgba(100,116,139,0.06)',
        highlight: '#00e5a0', hover: '#f59e0b',
      }},
    }})));
  }} else {{
    closeInfo();
    resetHighlight();
  }}
}});

// ── Double-click → zoom to node ──
network.on('doubleClick', params => {{
  if (params.nodes.length === 1) {{
    network.focus(params.nodes[0], {{ scale: 2.0, animation: {{ duration: 500, easingFunction: 'easeInOutQuad' }} }});
  }}
}});

// ── Hover ──
network.on('hoverNode', params => {{
  container.style.cursor = 'pointer';
}});
network.on('blurNode',  () => {{ container.style.cursor = 'default'; }});

function closeInfo() {{
  document.getElementById('info-panel').style.display = 'none';
  resetHighlight();
}}
</script>
</body>
</html>"""

    components.html(html, height=height + 10, scrolling=False)


