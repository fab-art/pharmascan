""" tab_summary.py — Summary dashboard with KPIs, time series, and charts. """
import matplotlib.pyplot as plt
import streamlit as st
from config import ACCENT, ACCENT2, PURPLE, WARN, DANGER, TEXT, CARD
from charts import hbar_chart, time_series_chart
from utils  import fmt_number


def render(tab, df, s, rapid, rapid_days, top_n):
    with tab:
        with tab_summary:
            c = st.columns(4)
            c[0].metric("Total Records",         f"{s['total_rows']:,}")
            c[1].metric("Unique Patients",       f"{s['unique_patients']:,}" if "unique_patients" in s else "—")
            c[2].metric("Repeat Patients",       f"{s['repeat_patients']:,}" if "repeat_patients" in s else "—")
            c[3].metric("Rapid Revisits",        str(len(rapid)), delta=f"≤{rapid_days} day window")

            c2 = st.columns(4)
            c2[0].metric("Unique Practitioners", f"{s['unique_doctors']:,}" if "unique_doctors" in s else "—")
            c2[1].metric("Max Visits / Patient", str(s.get("max_visits", "—")))
            c2[2].metric("Total Cost (RWF)",     fmt_number(s["total_amount"]) if "total_amount" in s else "—")
            c2[3].metric("Avg Cost / Visit",     fmt_number(s["avg_amount"])   if "avg_amount"   in s else "—")

            if "date_min" in s:
                st.markdown(
                    f'<p style="font-size:12px;color:#64748b;font-family:monospace;margin:8px 0 20px">'
                    f'📅 {s["date_min"]} — {s["date_max"]}</p>',
                    unsafe_allow_html=True,
                )

            fig_t = time_series_chart(df)
            if fig_t:
                st.pyplot(fig_t, use_container_width=True); plt.close(fig_t)

            left, right = st.columns(2)
            with left:
                if "top_patients" in s:
                    td = s["top_patients"].head(top_n)
                    colors = [DANGER if v >= 10 else WARN if v >= 5 else ACCENT for v in td["visits"]]
                    fig = hbar_chart([str(x)[:22] for x in td["id"]], td["visits"].tolist(),
                                     colors, "Top Patients (RAMA No.) by Visit Count", "Visits")
                    st.pyplot(fig, use_container_width=True); plt.close(fig)
            with right:
                if "top_doctors" in s:
                    td = s["top_doctors"].head(top_n)
                    fig = hbar_chart([str(x)[:22] for x in td["doctor"]], td["visits"].tolist(),
                                     ACCENT2, "Top Practitioners by Visit Volume", "Visits")
                    st.pyplot(fig, use_container_width=True); plt.close(fig)

            # Practitioner type breakdown
            if "doctor_type" in df.columns:
                dt_vc = df["doctor_type"].value_counts().head(top_n)
                fig = hbar_chart(
                    [str(x)[:30] for x in dt_vc.index],
                    dt_vc.values.tolist(),
                    PURPLE, "Visits by Practitioner Type", "Visits",
                )
                st.pyplot(fig, use_container_width=True); plt.close(fig)

            # Gender & patient type pie charts
            gc1, gc2 = st.columns(2)
            for target_col, label, target_col_obj in [
                (gc1, "Gender Breakdown",       "gender"),
                (gc2, "Patient Type Breakdown", "patient_type"),
            ]:
                if target_col_obj in df.columns:
                    vc = df[target_col_obj].value_counts()
                    fig, ax = plt.subplots(figsize=(4, 3))
                    ax.pie(vc.values, labels=vc.index,
                           colors=[ACCENT, ACCENT2, PURPLE, WARN, DANGER][:len(vc)],
                           autopct="%1.1f%%", pctdistance=0.8,
                           textprops={"color": TEXT, "fontsize": 9},
                           wedgeprops={"linewidth": 1.5, "edgecolor": CARD})
                    ax.set_title(label, fontsize=11, fontweight="bold", color=TEXT, pad=10)
                    with target_col:
                        st.pyplot(fig, use_container_width=True); plt.close(fig)

