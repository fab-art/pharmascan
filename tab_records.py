""" tab_records.py — Paginated all-records viewer with full-text search. """
import streamlit as st
from utils import paginate_df


def render(tab, df, show_raw):
    with tab:
        with tab_records:
            st.markdown(f'<div class="sec-head">All Records — {len(df):,} rows</div>', unsafe_allow_html=True)
            search = st.text_input("🔍 Filter rows", key="rec_search", placeholder="Type to search any column…")
            display_df = df.copy()
            if not show_raw:
                display_df.columns = [c.replace("_", " ").title() for c in display_df.columns]
            if search:
                mask = display_df.apply(lambda col: col.astype(str).str.contains(search, case=False, na=False)).any(axis=1)
                display_df = display_df[mask]
                st.caption(f"{len(display_df):,} matching rows")
            paginate_df(display_df, key="all_records", page_size=500, height=520, search_placeholder="Search any column...")

