"""
PharmaScan — Pharmacy Voucher Intelligence
==========================================
Entry point. Run with:  streamlit run app.py

Module layout
─────────────
app.py                   ← You are here (entry, sidebar, tabs)
config.py                ← Colours, CSS, COLUMN_MAP
utils.py                 ← Logger, audit, pagination, fmt_number
loader.py                ← File loading, column normalisation
drug_reference.py        ← Embedded 1,534-drug RHIA reference
rules_engine.py          ← 15 vectorized fraud rules
name_normaliser.py       ← Fuzzy name clustering
charts.py                ← Matplotlib + vis.js network
data_prep.py             ← Column mapping wizard
exporter.py              ← Excel report generation
tabs/
  tab_summary.py
  tab_records.py
  tab_repeat.py
  tab_rapid.py
  tab_network.py
  tab_normalise.py
  tab_counter_verification.py
  tab_cross_facility.py
  tab_data_prep.py
  tab_rules.py
"""

import streamlit as st

# ── Local modules ──────────────────────────────────────────────────────────────
from config  import APP_CSS
from utils   import audit, fmt_number, paginate_df, render_sidebar_perf
from loader  import load_and_process
import tabs.tab_summary              as _t_summary
import tabs.tab_records              as _t_records
import tabs.tab_repeat               as _t_repeat
import tabs.tab_rapid                as _t_rapid
import tabs.tab_network              as _t_network
import tabs.tab_normalise            as _t_normalise
import tabs.tab_counter_verification as _t_cv
import tabs.tab_cross_facility       as _t_xfac
import tabs.tab_data_prep            as _t_dataprep
import tabs.tab_rules                as _t_rules

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PharmaScan",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(APP_CSS, unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="sidebar-title">💊 PharmaScan</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-sub">Pharmacy Voucher Intelligence</div>', unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "Upload voucher report",
        type=["csv", "xlsx", "xls", "ods"],
        help="Supports CSV, Excel (.xlsx/.xls), and ODS",
    )

    st.markdown("---")
    st.markdown("**⚙️ Analysis Settings**")
    rapid_days = st.slider("Rapid revisit window (days)", 1, 30, 7)
    top_n      = st.slider("Top N for charts", 5, 25, 15)
    show_raw   = st.checkbox("Show raw column names in tables", value=False)

    st.markdown("---")
    st.markdown("""**📋 Detected columns**
<small style='color:#64748b;font-family:monospace;line-height:2'>
<b style='color:#0ea5e9'>Patient</b><br>
RAMA Number → patient_id<br>
Patient Name → patient_name<br>
Patient Type · Gender · Is Newborn<br><br>
<b style='color:#0ea5e9'>Practitioner</b><br>
Practitioner Name → doctor_name<br>
Practitioner Type → doctor_type<br><br>
<b style='color:#0ea5e9'>Visit</b><br>
Dispensing Date → visit_date<br>
Paper Code → voucher_id<br><br>
<b style='color:#0ea5e9'>Financials</b><br>
Total Cost → amount<br>
Medicine Cost · Patient Co-payment<br>
Insurance Co-payment
</small>""", unsafe_allow_html=True)

# ── Landing page ──────────────────────────────────────────────────────────────
if uploaded is None:
    st.markdown("""
<div style='text-align:center;padding:80px 20px 40px'>
  <div style='font-size:56px;margin-bottom:16px'>💊</div>
  <div style='font-family:Syne,sans-serif;font-size:36px;font-weight:800;
       color:#e2e8f0;margin-bottom:8px'>
    Pharma<span style='color:#00e5a0'>Scan</span></div>
  <div style='color:#64748b;font-size:16px;margin-bottom:32px'>
    Pharmacy Voucher Intelligence</div>
</div>""", unsafe_allow_html=True)

    for col, icon, title, desc in zip(
        st.columns(4),
        ["🔧", "🔁", "⚡", "🛡️"],
        ["Auto Column Fix", "Repeat Detection", "Rapid Revisits", "Rules Engine"],
        [
            "Maps RAMA Number, Dispensing Date, Practitioner Name and 30+ variants automatically",
            "Finds patients with multiple vouchers and ranks them by frequency",
            "Flags same patient returning within your chosen day window",
            "15 vectorized fraud rules: clinical, statistical, and behavioural",
        ],
    ):
        with col:
            st.markdown(f"""
<div style='background:#111720;border:1px solid #1e2a38;border-radius:12px;
     padding:20px;text-align:center;min-height:150px'>
  <div style='font-size:28px;margin-bottom:8px'>{icon}</div>
  <div style='font-weight:700;color:#e2e8f0;margin-bottom:4px'>{title}</div>
  <div style='font-size:12px;color:#64748b'>{desc}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.info("👈 Upload a pharmacy voucher file in the sidebar to begin")
    st.stop()

# ── Load and process ──────────────────────────────────────────────────────────
file_bytes = uploaded.read()
with st.spinner("Analysing voucher data…"):
    try:
        df, col_map, s, repeat_groups, repeat_detail, rapid = load_and_process(
            file_bytes, uploaded.name, rapid_days
        )
    except Exception as e:
        st.error(f"❌ Could not process file: {e}")
        st.stop()

# ── Sidebar quality panel (after df is loaded) ────────────────────────────────
with st.sidebar:
    render_sidebar_perf(s, df)

# ── Column normalisation banner ───────────────────────────────────────────────
changed = {k: v for k, v in col_map.items() if k != v}
if changed:
    chips = "".join(f'<span class="chip">{k} → {v}</span>' for k, v in changed.items())
    st.markdown(f"""
<div class="info-banner">
  <b>🔧 Columns auto-normalised</b> — {len(changed)} name(s) mapped:
  <div class="chip-row">{chips}</div>
</div>""", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
(tab_summary, tab_records, tab_repeat, tab_rapid, tab_network,
 tab_norm, tab_cv, tab_xfac, tab_dataprep, tab_rules) = st.tabs([
    "📊 Summary",
    "📋 All Records",
    f"🔁 Repeat Patients  {'🟡' if repeat_groups else '🟢'}  {len(repeat_groups)}",
    f"⚡ Rapid Revisits  {'🔴' if rapid else '🟢'}  {len(rapid)}",
    "🕸️ Network Graph",
    "✏️ Normalise Names",
    "📄 Counter-Verification Report",
    "🏥 Cross-Facility Match",
    "🗂️ Data Prep",
    "🛡️ Rules Engine",
])

# ── Render each tab ───────────────────────────────────────────────────────────
_t_summary.render(tab_summary, df, s, rapid, rapid_days, top_n)
_t_records.render(tab_records, df, show_raw)
_t_repeat.render(tab_repeat, repeat_groups, repeat_detail, s)
_t_rapid.render(tab_rapid, rapid, rapid_days)
_t_network.render(tab_network, df)
_t_normalise.render(tab_norm, df, show_raw)
_t_cv.render(tab_cv, df, col_map)
_t_xfac.render(tab_xfac, df, s, col_map)
_t_dataprep.render(tab_dataprep)
_t_rules.render(tab_rules, df, show_raw)
