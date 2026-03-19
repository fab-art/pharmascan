""" tab_normalise.py — Fuzzy doctor/patient name normalisation with approval UI. """
import pandas as pd
import streamlit as st
from name_normaliser import detect_name_clusters, apply_name_normalisation


def render(tab, df, show_raw):
    with tab:
        with tab_norm:

            st.markdown('<div class="sec-head">✏️ Doctor / Practitioner Name Normalisation</div>',
                        unsafe_allow_html=True)

            # Pick which column to normalise
            str_cols = [c for c in df.columns
                        if df[c].dtype == object or str(df[c].dtype).startswith("string")]

            norm_col = st.selectbox(
                "Column to normalise",
                options=str_cols,
                index=str_cols.index("doctor_name") if "doctor_name" in str_cols else 0,
                help="Fuzzy-match similar names within this column and merge variants into one canonical form",
            )

            with st.spinner("Detecting name clusters…"):
                col_counts = df[norm_col].value_counts().to_dict()
                col_names  = sorted(df[norm_col].dropna().unique().tolist(), key=str)
                clusters   = detect_name_clusters(col_names, col_counts)

            n_clusters   = len(clusters)
            n_suspicious = sum(1 for c in clusters if c["suspicious"])
            n_variants   = sum(len(c["variants"]) for c in clusters)

            # ── Summary metrics ──
            mc = st.columns(4)
            mc[0].metric("Unique raw names",   len(col_names))
            mc[1].metric("Variant clusters",   n_clusters)
            mc[2].metric("Total variants",     n_variants,
                         delta=f"→ {len(col_names) - n_variants} after merge")
            mc[3].metric("⚠️ Needs review",    n_suspicious)

            st.markdown("""
        <div style='font-size:11px;color:#64748b;margin:8px 0 16px;font-family:monospace'>
          Below are proposed name merges. <b style='color:#e2e8f0'>✅ Check</b> clusters to approve them,
          then click <b style='color:#00e5a0'>Apply Selected</b>. Suspicious clusters (no shared tokens)
          are shown in amber — review carefully before approving.
        </div>""", unsafe_allow_html=True)

            if not clusters:
                st.success("✅ No similar names detected — the column looks clean.")
            else:
                # ── Quick select helpers ──
                qc1, qc2, qc3 = st.columns([1, 1, 4])
                with qc1:
                    if st.button("✅ Select all"):
                        for c in clusters:
                            st.session_state[f"norm_{c['canonical']}"] = True
                with qc2:
                    if st.button("❌ Deselect all"):
                        for c in clusters:
                            st.session_state[f"norm_{c['canonical']}"] = False

                # ── Cluster review cards ──
                approved = []
                for cluster in clusters:
                    key      = f"norm_{cluster['canonical']}"
                    default  = not cluster["suspicious"]    # auto-select non-suspicious
                    checked  = st.session_state.get(key, default)

                    conf_pct = int(cluster["confidence"] * 100)
                    if cluster["suspicious"]:
                        border = "#f59e0b"
                        conf_badge = f'<span style="background:rgba(245,158,11,.15);color:#f59e0b;border-radius:5px;padding:2px 8px;font-size:10px">⚠️ {conf_pct}% — review</span>'
                    elif conf_pct >= 90:
                        border = "#00e5a0"
                        conf_badge = f'<span style="background:rgba(0,229,160,.1);color:#00e5a0;border-radius:5px;padding:2px 8px;font-size:10px">✓ {conf_pct}%</span>'
                    else:
                        border = "#0ea5e9"
                        conf_badge = f'<span style="background:rgba(14,165,233,.1);color:#0ea5e9;border-radius:5px;padding:2px 8px;font-size:10px">{conf_pct}%</span>'

                    # Variant pills
                    freq_total = sum(col_counts.get(v, 0) for v in cluster["variants"])
                    canon_freq = col_counts.get(cluster["canonical"], 0)
                    variant_pills = " ".join(
                        f'<span style="background:#1e2a38;border-radius:5px;padding:2px 8px;font-size:11px;'
                        f'font-family:monospace;color:#94a3b8;margin:2px">'
                        f'{v} <span style="color:#64748b">×{col_counts.get(v,0)}</span></span>'
                        for v in cluster["variants"]
                    )

                    st.markdown(f"""
        <div style="background:#111720;border:1px solid {border};border-left:3px solid {border};
             border-radius:10px;padding:14px 16px;margin-bottom:10px">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap">
            <div style="flex:1;min-width:200px">
              <div style="font-size:13px;font-weight:700;color:#e2e8f0;margin-bottom:4px">
                → <span style="color:#00e5a0">{cluster['canonical']}</span>
                <span style="color:#64748b;font-size:11px;margin-left:6px">×{canon_freq} occurrences</span>
              </div>
              <div style="font-size:11px;color:#64748b;margin-bottom:8px;font-family:monospace">
                {len(cluster['variants'])} variant(s) · {freq_total} rows affected
              </div>
              <div style="display:flex;flex-wrap:wrap;gap:4px">{variant_pills}</div>
            </div>
            <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px;flex-shrink:0">
              {conf_badge}
            </div>
          </div>
        </div>""", unsafe_allow_html=True)

                    checked = st.checkbox(
                        f"Approve merge → {cluster['canonical']}",
                        value=checked,
                        key=key,
                    )
                    if checked:
                        approved.append(cluster)

                # ── Apply button ──
                st.markdown("<br>", unsafe_allow_html=True)
                col_apply, col_preview = st.columns([1, 2])

                with col_apply:
                    st.markdown(
                        f'<p style="font-size:12px;color:#64748b;font-family:monospace">'
                        f'{len(approved)} cluster(s) selected · '
                        f'{sum(len(c["variants"]) for c in approved)} variant(s) will be merged</p>',
                        unsafe_allow_html=True,
                    )
                    do_apply = st.button("⚡ Apply Selected Normalisations",
                                         type="primary", disabled=len(approved) == 0)

                if do_apply:
                    st.session_state["normalised_df"]  = apply_name_normalisation(df, norm_col, approved)
                    st.session_state["normalised_col"] = norm_col
                    st.session_state["normalised_map"] = {
                        v: c["canonical"]
                        for c in approved for v in c["variants"]
                    }

                # ── Show result ──
                if "normalised_df" in st.session_state and st.session_state.get("normalised_col") == norm_col:
                    ndf = st.session_state["normalised_df"]
                    nmap = st.session_state["normalised_map"]

                    st.success(f"✅ Applied! {len(nmap)} variant names merged in column **{norm_col}**.")

                    before_unique = df[norm_col].nunique()
                    after_unique  = ndf[norm_col].nunique()

                    rc1, rc2, rc3 = st.columns(3)
                    rc1.metric("Before: unique names", before_unique)
                    rc2.metric("After: unique names",  after_unique,
                               delta=f"−{before_unique - after_unique}")
                    rc3.metric("Rows updated", len(nmap))

                    # Rename map table
                    st.markdown('<div class="sec-head">Applied Rename Map</div>', unsafe_allow_html=True)
                    map_df = pd.DataFrame(
                        [(k, v) for k, v in sorted(nmap.items())],
                        columns=["Original variant", "→ Canonical name"]
                    )
                    st.dataframe(map_df, use_container_width=True, height=300)

                    # Updated data preview
                    st.markdown('<div class="sec-head">Updated Data Preview</div>', unsafe_allow_html=True)
                    srch_n = st.text_input("🔍 Filter", key="norm_srch", placeholder="Search any column…")
                    show_df = ndf.copy()
                    if not show_raw:
                        show_df.columns = [c.replace("_", " ").title() for c in show_df.columns]
                    if srch_n:
                        mask = show_df.apply(lambda c: c.astype(str).str.contains(srch_n, case=False, na=False)).any(axis=1)
                        show_df = show_df[mask]
                    st.dataframe(show_df, use_container_width=True, height=480)

                    # Download
                    csv_bytes = ndf.to_csv(index=False).encode()
                    st.download_button(
                        "⬇️ Download normalised CSV",
                        data=csv_bytes,
                        file_name=f"pharmascan_normalised_{norm_col}.csv",
                        mime="text/csv",
                    )

