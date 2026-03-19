""" tab_network.py — Interactive vis.js bipartite network graph. """
import pandas as pd
import streamlit as st
from charts import build_network_data, render_vis_network


def render(tab, df):
    with tab:
        with tab_network:

            # All text / categorical columns available for network nodes
            cat_cols = [c for c in df.columns
                        if df[c].dtype == object or str(df[c].dtype).startswith("string")]
            if not cat_cols:
                cat_cols = list(df.columns)

            def col_idx(candidates):
                for name in candidates:
                    if name in cat_cols:
                        return cat_cols.index(name)
                return 0

            st.markdown('<div class="sec-head">🔧 Network Configuration</div>', unsafe_allow_html=True)

            cfg1, cfg2, cfg3, cfg4, cfg5 = st.columns([2, 2, 1.8, 1.4, 1.4])

            with cfg1:
                col_a = st.selectbox(
                    "◆ Node A (diamonds)",
                    options=cat_cols,
                    index=col_idx(["doctor_name", "doctor_type", "doctor_id"]),
                    help="Each unique value in this column becomes a diamond-shaped node",
                )
            with cfg2:
                b_default = col_idx(["patient_name", "patient_id", "gender", "patient_type"])
                if cat_cols[b_default] == col_a and len(cat_cols) > 1:
                    b_default = (b_default + 1) % len(cat_cols)
                col_b = st.selectbox(
                    "● Node B (circles)",
                    options=cat_cols,
                    index=b_default,
                    help="Each unique value in this column becomes a circle-shaped node",
                )
            with cfg3:
                physics_mode = st.selectbox(
                    "Physics / layout",
                    options=["Force Atlas 2", "Barnes-Hut", "Repulsion", "None (static)"],
                    help="Force simulation used to position nodes",
                )
            with cfg4:
                max_nodes = st.slider("Max nodes", 20, 400, 150)
            with cfg5:
                min_edge  = st.slider("Min edge weight", 1, 10, 1,
                                      help="Hide edges with fewer shared visits than this")

            net_height = st.slider("Canvas height (px)", 400, 900, 680, step=40)

            # Quick preset combos
            st.markdown("""
        <div style='font-size:11px;color:#64748b;margin-bottom:14px;font-family:monospace'>
          💡 Try: <b style='color:#e2e8f0'>Practitioner Name ↔ Patient Name</b> &nbsp;·&nbsp;
          <b style='color:#e2e8f0'>Practitioner Type ↔ Patient Type</b> &nbsp;·&nbsp;
          <b style='color:#e2e8f0'>Practitioner Name ↔ Gender</b> &nbsp;·&nbsp;
          <b style='color:#e2e8f0'>Practitioner Name ↔ Patient Type</b>
        </div>""", unsafe_allow_html=True)

            if col_a == col_b:
                st.warning("⚠️ Node A and Node B must be different columns.")
            else:
                card_a = df[col_a].nunique()
                card_b = df[col_b].nunique()
                st.markdown(
                    f'<p style="font-size:12px;color:#64748b;font-family:monospace;margin-bottom:16px">'
                    f'◆ <b style="color:#00e5a0">{col_a.replace("_"," ").title()}</b>: {card_a} unique values'
                    f'&nbsp;|&nbsp;'
                    f'● <b style="color:#0ea5e9">{col_b.replace("_"," ").title()}</b>: {card_b} unique values'
                    f'&nbsp;|&nbsp; {len(df):,} rows total</p>',
                    unsafe_allow_html=True,
                )

                with st.spinner("Building network…"):
                    vis_nodes, vis_edges, stats = build_network_data(
                        df, col_a, col_b, max_nodes, min_edge
                    )

                if vis_nodes is None:
                    st.warning("No edges found. Try lowering the minimum edge weight or choosing different columns.")
                else:
                    # Stats row
                    mc = st.columns(5)
                    mc[0].metric(f"◆ {col_a.replace('_',' ').title()[:14]}", stats["nodes_a"])
                    mc[1].metric(f"● {col_b.replace('_',' ').title()[:14]}", stats["nodes_b"])
                    mc[2].metric("Edges",      stats["edges"])
                    mc[3].metric("Avg Degree", stats["avg_degree"])
                    mc[4].metric("Density",    stats["density"])

                    # Controls hint
                    st.markdown("""
        <div style='font-size:11px;color:#64748b;margin:8px 0 6px;font-family:monospace'>
          🖱 <b style='color:#e2e8f0'>Drag</b> nodes to reposition &nbsp;·&nbsp;
          <b style='color:#e2e8f0'>Scroll</b> to zoom &nbsp;·&nbsp;
          <b style='color:#e2e8f0'>Click</b> a node to highlight its neighbours &nbsp;·&nbsp;
          <b style='color:#e2e8f0'>Double-click</b> to zoom in &nbsp;·&nbsp;
          <b style='color:#e2e8f0'>Search</b> any node by name
        </div>""", unsafe_allow_html=True)

                    # ── Render interactive vis.js network ──
                    render_vis_network(vis_nodes, vis_edges, stats, physics_mode, height=net_height)

                    # Top connected nodes tables below the canvas
                    st.markdown("<br>", unsafe_allow_html=True)
                    if stats["top_a"] or stats["top_b"]:
                        ta, tb = st.columns(2)
                        with ta:
                            st.markdown(
                                f'<div class="sec-head">◆ Top {col_a.replace("_"," ").title()} by connections</div>',
                                unsafe_allow_html=True,
                            )
                            st.dataframe(
                                pd.DataFrame(stats["top_a"], columns=["node", "connections"])
                                  .style.background_gradient(subset=["connections"], cmap="Greens"),
                                use_container_width=True, height=320,
                            )
                        with tb:
                            st.markdown(
                                f'<div class="sec-head">● Top {col_b.replace("_"," ").title()} by connections</div>',
                                unsafe_allow_html=True,
                            )
                            st.dataframe(
                                pd.DataFrame(stats["top_b"], columns=["node", "connections"])
                                  .style.background_gradient(subset=["connections"], cmap="Blues"),
                                use_container_width=True, height=320,
                            )

