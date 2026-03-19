""" tab_repeat.py — Repeat patient detection and visit-group explorer. """
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from config import ACCENT, WARN, DANGER, TEXT, CARD


def render(tab, repeat_groups, repeat_detail, s):
    with tab:
        with tab_repeat:
            if not repeat_groups:
                st.success("✅ No patients with multiple visits detected.")
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("Repeat Patients", len(repeat_groups))
                c2.metric("Max Visits",      s.get("max_visits", "—"))
                heavy = sum(1 for g in repeat_groups if g["visits"] >= 5)
                c3.metric("High-frequency (≥5)", heavy)

                visit_counts = [g["visits"] for g in repeat_groups]
                if len(set(visit_counts)) > 1:
                    fig, ax = plt.subplots(figsize=(8, 3))
                    bins = list(range(2, max(visit_counts) + 2))
                    _, bins_out, patches = ax.hist(visit_counts, bins=bins,
                                                   color=ACCENT, edgecolor=CARD, rwidth=0.8)
                    for patch, left in zip(patches, bins_out[:-1]):
                        if left >= 10: patch.set_facecolor(DANGER)
                        elif left >= 5: patch.set_facecolor(WARN)
                    ax.set_xlabel("Visits per Patient"); ax.set_ylabel("Patients")
                    ax.set_title("Distribution of Repeat Visit Counts", fontsize=11,
                                 fontweight="bold", color=TEXT, pad=10)
                    ax.spines[["top", "right"]].set_visible(False)
                    ax.grid(axis="y", alpha=0.3); fig.tight_layout()
                    st.pyplot(fig, use_container_width=True); plt.close(fig)

                st.markdown('<div class="sec-head">Patient Visit Groups</div>', unsafe_allow_html=True)
                grp_df = pd.DataFrame(repeat_groups)
                srch = st.text_input("🔍 Filter", key="rep_search", placeholder="Name or RAMA number…")
                if srch:
                    mask = grp_df.apply(lambda c: c.astype(str).str.contains(srch, case=False, na=False)).any(axis=1)
                    grp_df = grp_df[mask]

                def highlight_v(val):
                    try:
                        v = int(val)
                        if v >= 10: return "color:#ef4444;font-weight:bold"
                        if v >= 5:  return "color:#f59e0b;font-weight:bold"
                    except Exception:
                        pass
                    return ""

                st.dataframe(grp_df.style.map(highlight_v, subset=["visits"]),
                             use_container_width=True, height=360)

                st.markdown('<div class="sec-head">Detailed Repeat Visit Records</div>', unsafe_allow_html=True)
                st.dataframe(repeat_detail, use_container_width=True, height=380)

