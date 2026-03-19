""" tab_rapid.py — Rapid revisit (same-patient short-gap) fraud detector. """
import pandas as pd
import streamlit as st
from charts import rapid_histogram
import matplotlib.pyplot as plt


def render(tab, rapid, rapid_days):
    with tab:
        with tab_rapid:
            if not rapid:
                st.success(f"✅ No rapid revisits detected within {rapid_days} days.")
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Rapid Cases", len(rapid))
                critical = sum(1 for r in rapid if r["days_apart"] <= 2)
                c2.metric("Critical (≤2 days)", critical)
                avg_d = sum(r["days_apart"] for r in rapid) / len(rapid)
                c3.metric("Avg Days Apart", f"{avg_d:.1f}")

                fig_h = rapid_histogram(rapid)
                if fig_h:
                    st.pyplot(fig_h, use_container_width=True); plt.close(fig_h)

                st.markdown(f'<div class="sec-head">⚠️ {len(rapid)} cases — window ≤{rapid_days} days</div>',
                            unsafe_allow_html=True)
                for i in range(0, len(rapid), 3):
                    batch = rapid[i:i + 3]
                    cols = st.columns(len(batch))
                    for col, r in zip(cols, batch):
                        crit = r["days_apart"] <= 2
                        col.markdown(f"""
        <div class="rapid-card {'crit' if crit else ''}">
          <div class="rc-head">
            <div>
              <div class="rc-name">{r['patient_name'][:24]}</div>
              <div class="rc-id">{r['patient_id']}</div>
            </div>
            <div class="rc-days">{r['days_apart']}<small> d</small></div>
          </div>
          <div class="rc-meta">📅 {r['visit_1']} → {r['visit_2']}</div>
          <div class="rc-meta">👨‍⚕️ {r['doctor'][:28]}</div>
        </div>""", unsafe_allow_html=True)

                st.markdown('<div class="sec-head" style="margin-top:24px">Full Table</div>',
                            unsafe_allow_html=True)
                st.dataframe(pd.DataFrame(rapid), use_container_width=True, height=360)

