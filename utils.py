"""
utils.py — Logging, audit trail, constants, pagination helper, sidebar panel.
"""
import logging as _logging
import math as _math
import time as _time
import streamlit as st
import pandas as pd

# ── Logger ────────────────────────────────────────────────────────────────────
LOG = _logging.getLogger("pharmascan")
if not LOG.handlers:
    _h = _logging.StreamHandler()
    _h.setFormatter(_logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    LOG.addHandler(_h)
    LOG.setLevel(_logging.INFO)

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_FILE_MB       = 250
CHUNK_ROWS        = 100_000
PAGE_SIZE_DEFAULT = 500
CLUSTER_MAX_NAMES = 5_000
RULES_VERSION     = "2.0.0"


def audit(action: str, detail: str = "", rows: int = 0, ms: float = 0.0):
    """Append an entry to st.session_state audit log and write to logger."""
    entry = {
        "ts":     _time.strftime("%H:%M:%S"),
        "action": action,
        "detail": str(detail)[:200],
        "rows":   rows,
        "ms":     round(ms, 1),
    }
    if "_audit_log" not in st.session_state:
        st.session_state["_audit_log"] = []
    st.session_state["_audit_log"].append(entry)
    LOG.info("[%s] %s — %s (rows=%d, %.1fms)",
             entry["ts"], action, detail, rows, ms)


def fmt_number(n: float) -> str:
    """Format large numbers as 1.2B / 3.4M / 5.6K / 7,890."""
    if n >= 1e9:  return f"{n/1e9:.1f}B"
    if n >= 1e6:  return f"{n/1e6:.1f}M"
    if n >= 1e3:  return f"{n/1e3:.1f}K"
    return f"{n:,.0f}"


def paginate_df(
    df: pd.DataFrame,
    key: str,
    page_size: int = PAGE_SIZE_DEFAULT,
    height: int = 480,
    search_placeholder: str = "Search…",
    extra_filters: dict | None = None,
) -> None:
    """Render a paginated, searchable dataframe with download button."""
    filtered = df.copy()

    srch = st.text_input("🔍 Search", key=f"{key}_srch",
                         placeholder=search_placeholder)
    if srch:
        mask = filtered.apply(
            lambda col: col.astype(str).str.contains(srch, case=False, na=False)
        ).any(axis=1)
        filtered = filtered[mask]

    if extra_filters:
        for col, choices in extra_filters.items():
            if col in filtered.columns and choices:
                filtered = filtered[filtered[col].isin(choices)]

    total   = len(filtered)
    n_pages = max(1, _math.ceil(total / page_size))

    pg_col, info_col = st.columns([1, 3])
    with pg_col:
        page = st.number_input("Page", min_value=1, max_value=n_pages,
                               value=1, step=1, key=f"{key}_page")
    with info_col:
        st.markdown(
            f'<p style="font-size:11px;color:#64748b;font-family:monospace;margin-top:28px">' +
            f'Showing {min((page-1)*page_size+1, total):,}–' +
            f'{min(page*page_size, total):,} of ' +
            f'<b style="color:#e2e8f0">{total:,}</b> rows ' +
            f'({n_pages} page{"s" if n_pages!=1 else ""})</p>',
            unsafe_allow_html=True,
        )

    start = (page - 1) * page_size
    st.dataframe(filtered.iloc[start:start + page_size],
                 use_container_width=True, height=height)

    if total > 0:
        st.download_button(
            f"⬇️ Download all {total:,} rows (CSV)",
            data=filtered.to_csv(index=False).encode(),
            file_name=f"{key}_export.csv",
            mime="text/csv",
            key=f"{key}_dl",
        )


def render_sidebar_perf(s: dict, df: pd.DataFrame) -> None:
    """Render data quality metrics and audit log in the sidebar."""
    st.markdown("---")
    st.markdown("**📊 Data Quality**")
    mb       = s.get("source_mb", 0)
    rows     = s.get("total_rows", len(df))
    mem_mb   = df.memory_usage(deep=True).sum() / 1_048_576
    null_pct = df.isna().mean().mean() * 100

    q1, q2 = st.columns(2)
    q1.metric("Rows",    f"{rows:,}")
    q2.metric("Cols",    f"{len(df.columns)}")
    q1.metric("File MB", f"{mb:.1f}")
    q2.metric("RAM MB",  f"{mem_mb:.1f}")

    nc = "#ef4444" if null_pct > 20 else "#f59e0b" if null_pct > 5 else "#00e5a0"
    st.markdown(
        f'<div style="font-size:11px;font-family:monospace;color:{nc};margin:4px 0">' +
        f'Null rate: {null_pct:.1f}%</div>',
        unsafe_allow_html=True,
    )

    if rows > 200_000:
        st.warning(f"⚠️ Large dataset ({rows:,} rows). Some charts sampled.")
    elif rows > 50_000:
        st.info(f"ℹ️ {rows:,} rows — paginated views active.")

    audit_log = st.session_state.get("_audit_log", [])
    if audit_log:
        with st.expander(f"🪵 Audit log ({len(audit_log)} events)", expanded=False):
            for entry in reversed(audit_log[-20:]):
                st.markdown(
                    f'<div style="font-family:monospace;font-size:10px;color:#64748b;padding:2px 0">' +
                    f'<span style="color:#0ea5e9">{entry["ts"]}</span> ' +
                    f'<b style="color:#e2e8f0">{entry["action"]}</b> ' +
                    entry["detail"] +
                    (f' ({entry["rows"]:,} rows)' if entry["rows"] else "") +
                    (f' — {entry["ms"]:.0f}ms' if entry["ms"] else "") +
                    '</div>',
                    unsafe_allow_html=True,
                )
