""" tab_rules.py — 15-rule vectorized fraud rules engine UI. """
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from config import ACCENT, ACCENT2, WARN, DANGER, TEXT, DARK, CARD
from rules_engine import run_rules_engine
from exporter    import export_rules_excel
from utils       import paginate_df


def render(tab, df, show_raw):
    with tab:


        # ══════════════════════════════════════════════════════════════════════════════
        # PRODUCTION SIDEBAR ADDITIONS
        # ══════════════════════════════════════════════════════════════════════════════

        # ══════════════════════════════════════════════════════════════════════════════
        # UPGRADED RULES ENGINE TAB  — production UI with 15 rules + paginated results
        # ══════════════════════════════════════════════════════════════════════════════

        with tab_rules:
            _banner = (
                '<div style="background:#111720;border:1px solid #1e2a38;' +
                'border-left:3px solid #ef4444;border-radius:10px;padding:14px 18px;margin-bottom:20px">' +
                '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">' +
                '<div>' +
                '<b style="color:#ef4444;font-size:15px">🛡️ Fraud Rules Engine</b>' +
                '<span style="font-size:11px;color:#64748b;font-family:monospace;margin-left:12px">' +
                'v2.0 · 15 rules · vectorized · RHIA Jan 2025 · UCG 2023 · BNF · FDA · WHO · GINA' +
                '</span></div></div></div>'
            )
            st.markdown(_banner, unsafe_allow_html=True)

            _chip_defs = [
                ("drug_code",   "Drug Code",  "drug_code"   in df.columns),
                ("quantity",    "Quantity",   "quantity"    in df.columns),
                ("diagnosis",   "Diagnosis",  "diagnosis"   in df.columns),
                ("doc",         "Prescriber", any(c in df.columns for c in ["doctor_type","doctor_name"])),
                ("pid",         "Patient ID", any(c in df.columns for c in ["patient_id","patient_name"])),
                ("visit_date",  "Date",       "visit_date"  in df.columns),
                ("amt",         "Amount",     any(c in df.columns for c in ["insurance_copay","amount"])),
                ("facility",    "Facility",   "facility"    in df.columns),
            ]
            _chips_parts = []
            for _, lbl, ok in _chip_defs:
                _c = "#00e5a0" if ok else "#ef4444"
                _i = "✓" if ok else "✗"
                _chips_parts.append(
                    f'<span style="background:rgba({"0,229,160" if ok else "239,68,68"},0.1);' +
                    f'border:1px solid {_c};border-radius:6px;padding:3px 10px;' +
                    f'font-size:11px;font-family:monospace;color:{_c};margin:2px">{_i} {lbl}</span>'
                )
            st.markdown(
                '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:16px">' +
                '<span style="font-size:11px;color:#64748b;font-family:monospace;margin-right:6px;line-height:28px">Columns:</span>' +
                "".join(_chips_parts) + '</div>',
                unsafe_allow_html=True,
            )

            if not any(c in df.columns for c in ["drug_code","drug_name"]):
                st.warning(
                    "⚠️ No **drug_code** column detected. "
                    "Use **🗂️ Data Prep** to map your columns first."
                )
            else:
                st.markdown('<div class="sec-head">⚙️ Run Configuration</div>', unsafe_allow_html=True)
                _re_c1, _re_c2, _re_c3, _re_c4 = st.columns([2, 2, 2, 1.5])
                with _re_c1:
                    _re_min_score = st.slider("Min score to display", 0, 100, 0, key="re_min_score",
                        help="0=all | 30=FLAG+ | 50=HOLD+ | 75=BLOCK only")
                with _re_c2:
                    _re_decision_filter = st.multiselect(
                        "Decision filter", ["APPROVE","FLAG","HOLD","BLOCK"],
                        default=["FLAG","HOLD","BLOCK"], key="re_decision_filter")
                with _re_c3:
                    _re_page_size = st.selectbox("Rows per page", [100,250,500,1000,2500],
                        index=2, key="re_page_size")
                with _re_c4:
                    st.markdown("<br>", unsafe_allow_html=True)
                    _re_run = st.button("🔍 Run Engine", type="primary",
                        key="re_run", use_container_width=True)

                with st.expander("📋 All 15 Rules Reference", expanded=False):
                    _rref = pd.DataFrame([
                        ("R01","Drug-Prescriber Mismatch",        "Clinical",    "20-35","HIGH",   "RHIA prescriber restrictions + provider type"),
                        ("R02","Diagnosis-Drug Blacklist",         "Clinical",    "20-60","HIGH",   "UCG 2023 (39 ICD prefix x ATC class pairs)"),
                        ("R03","Quantity Excess",                  "Pharmacy",    "25-60","HIGH",   "UCG dosing + BNF + FDA limits (1534 drugs)"),
                        ("R04","High-Value Drug + Unrelated Dx",   "Financial",   "30",   "HIGH",   "RHIA price >50k RWF + ICD chapter check"),
                        ("R05","Antineoplastic Without Cancer Dx", "Oncology",    "25",   "MEDIUM", "L01 ATC + ICD C00-D49"),
                        ("R06","Psych Drug Without Mental Dx",     "Psychiatry",  "20",   "MEDIUM", "PSYCH restriction + ICD F/G4x"),
                        ("R07","Early Refill / Duplicate Claim",   "Pharmacy",    "40",   "HIGH",   "Min refill days per drug (1534 drugs)"),
                        ("R08","Unlisted RHIC Procedure Code",     "Tariff",      "15",   "LOW",    "RAMA tariff 2025-2027 cross-reference"),
                        ("R09","Malaria + Antibiotic Combo",       "Clinical",    "20",   "MEDIUM", "UCG: ACT first-line, J01 not indicated"),
                        ("R10","Immunosuppressant No Indication",  "Immunology",  "20",   "MEDIUM", "L04 + transplant/autoimmune ICD"),
                        ("R11","Provider Volume Spike (z-score)",  "Statistical", "20-35","HIGH",   "Provider claims >=3 sigma above peer mean"),
                        ("R12","Patient Frequency Spike",          "Statistical", "20",   "MEDIUM", "Patient visits >=4 sigma above cohort mean"),
                        ("R13","Suspiciously Round Amount",        "Financial",   "15",   "LOW",    "Amount >=50k RWF and multiple of 500/1000"),
                        ("R14","Weekend/Off-Hours Dispensing",     "Operational", "10-15","LOW",    "Saturday, Sunday, or 22:00-06:00 dispense"),
                        ("R15","Same-Day Multi-Drug High-Value",   "Behavioural", "25-45","HIGH",   ">=3 claims >=10k RWF same patient same day"),
                    ], columns=["ID","Rule","Category","Score","Severity","Evidence Base"])
                    def _sev_c(v):
                        return {"HIGH":"color:#ef4444;font-weight:bold","MEDIUM":"color:#f59e0b;font-weight:bold"}.get(v,"color:#64748b")
                    st.dataframe(_rref.style.map(_sev_c, subset=["Severity"]),
                        use_container_width=True, height=480)

                if _re_run or "re_results" in st.session_state:
                    if _re_run:
                        _prog = st.progress(0, text=f"Evaluating {len(df):,} claims against 15 rules...")
                        try:
                            _prog.progress(15, text="Expanding drug reference and merging...")
                            _re_out, _re_summary = run_rules_engine(df)
                            _prog.progress(90, text="Computing provider statistics...")
                            st.session_state["re_results"] = _re_out
                            st.session_state["re_summary"] = _re_summary
                            _prog.progress(100, text="Complete")
                            _prog.empty()
                            st.success(
                                f"✅ Completed in {_re_summary.get('elapsed_ms',0):.0f} ms "
                                f"· {_re_summary.get('flagged_count',0):,} of {len(df):,} claims flagged"
                            )
                        except Exception as _re_err:
                            _prog.empty()
                            st.error(f"❌ Rules engine error: {_re_err}")
                            st.stop()

                    _re_out     = st.session_state.get("re_results")
                    _re_summary = st.session_state.get("re_summary", {})

                    if _re_out is not None:
                        st.markdown('<div class="sec-head">📊 Results</div>', unsafe_allow_html=True)
                        _d   = _re_summary.get("decisions", {})
                        _tot = max(_re_summary.get("total", 1), 1)
                        _k1,_k2,_k3,_k4,_k5,_k6 = st.columns(6)
                        _k1.metric("Claims",       f"{_tot:,}")
                        _k2.metric("✅ Approve", f"{_d.get('APPROVE',0):,}")
                        _k3.metric("🟡 Flag", f"{_d.get('FLAG',0):,}",
                            f"{100*_d.get('FLAG',0)/_tot:.1f}%", delta_color="off")
                        _k4.metric("🟠 Hold", f"{_d.get('HOLD',0):,}", delta_color="inverse")
                        _k5.metric("🔴 Block",f"{_d.get('BLOCK',0):,}", delta_color="inverse")
                        _k6.metric("⏱ ms",       f"{_re_summary.get('elapsed_ms',0):.0f}")

                        _kr1, _kr2 = st.columns(2)
                        _kr1.metric("Total Flagged",
                            f"{_re_summary.get('flagged_count',0):,}",
                            f"{100*_re_summary.get('flagged_count',0)/_tot:.1f}% flag rate",
                            delta_color="inverse")
                        _kr2.metric("At-Risk Amount (RWF)",
                            f"{_re_summary.get('total_flagged_amount',0):,.0f}")

                        _ba = 100*_d.get("APPROVE",0)/_tot
                        _bf = 100*_d.get("FLAG",0)/_tot
                        _bh = 100*_d.get("HOLD",0)/_tot
                        _bb = 100*_d.get("BLOCK",0)/_tot
                        st.markdown(
                            f'<div style="margin:14px 0 8px"><div style="font-size:11px;color:#64748b;font-family:monospace;margin-bottom:5px">Decision breakdown</div>' +
                            f'<div style="display:flex;height:20px;border-radius:10px;overflow:hidden;width:100%">' +
                            f'<div style="width:{_ba:.1f}%;background:#22c55e" title="Approve"></div>' +
                            f'<div style="width:{_bf:.1f}%;background:#3b82f6" title="Flag"></div>' +
                            f'<div style="width:{_bh:.1f}%;background:#f59e0b" title="Hold"></div>' +
                            f'<div style="width:{_bb:.1f}%;background:#ef4444" title="Block"></div>' +
                            f'</div><div style="display:flex;gap:16px;margin-top:5px;font-size:11px;font-family:monospace">' +
                            f'<span style="color:#22c55e">■ Approve {_ba:.1f}%</span>' +
                            f'<span style="color:#3b82f6">■ Flag {_bf:.1f}%</span>' +
                            f'<span style="color:#f59e0b">■ Hold {_bh:.1f}%</span>' +
                            f'<span style="color:#ef4444">■ Block {_bb:.1f}%</span></div></div>',
                            unsafe_allow_html=True,
                        )

                        _ch1, _ch2 = st.columns(2)
                        with _ch1:
                            _all_counts = _re_summary.get("rule_counts", {})
                            _rfk = sorted(_all_counts.keys())
                            _rfv = [_all_counts.get(k, 0) for k in _rfk]
                            _fig_r, _ax_r = plt.subplots(figsize=(6, 3.5))
                            _bc = [DANGER if v >= 50 else WARN if v >= 10 else ACCENT for v in _rfv]
                            _bars = _ax_r.bar(_rfk, _rfv, color=_bc, edgecolor=CARD, width=0.7)
                            for _b, _v in zip(_bars, _rfv):
                                if _v > 0:
                                    _ax_r.text(_b.get_x()+_b.get_width()/2,
                                        _b.get_height()+max(_rfv or [1])*0.01,
                                        str(_v), ha="center", va="bottom", fontsize=7, color=TEXT)
                            _ax_r.set_title("Fires per Rule (15 rules)", color=TEXT,
                                fontsize=10, fontweight="bold", pad=8)
                            _ax_r.spines[["top","right"]].set_visible(False)
                            _ax_r.tick_params(axis="x", rotation=40, labelsize=7, colors=TEXT)
                            _ax_r.tick_params(axis="y", colors=TEXT)
                            _fig_r.patch.set_facecolor(CARD); _ax_r.set_facecolor(DARK)
                            _fig_r.tight_layout()
                            st.pyplot(_fig_r, use_container_width=True); plt.close(_fig_r)

                        with _ch2:
                            _sc_pos = _re_out["_score"][_re_out["_score"] > 0]
                            if len(_sc_pos) > 0:
                                _fig_s, _ax_s = plt.subplots(figsize=(6, 3.5))
                                _ax_s.hist(_sc_pos, bins=min(40, max(2,len(_sc_pos.unique()))),
                                    color="#1e3a5f", edgecolor=CARD, linewidth=0.4)
                                for _thr, _col, _lbl in [(30,ACCENT2,"FLAG"),(50,WARN,"HOLD"),(75,DANGER,"BLOCK")]:
                                    _ax_s.axvline(_thr, color=_col, linewidth=1.2,
                                        linestyle="--", alpha=0.7, label=f"{_lbl}≥{_thr}")
                                _ax_s.set_xlabel("Risk Score", color=TEXT)
                                _ax_s.set_ylabel("Claims", color=TEXT)
                                _ax_s.set_title("Risk Score Distribution", color=TEXT,
                                    fontsize=10, fontweight="bold", pad=8)
                                _ax_s.spines[["top","right"]].set_visible(False)
                                _ax_s.legend(fontsize=8, framealpha=0.2, labelcolor=TEXT)
                                _ax_s.tick_params(colors=TEXT)
                                _fig_s.patch.set_facecolor(CARD); _ax_s.set_facecolor(DARK)
                                _fig_s.tight_layout()
                                st.pyplot(_fig_s, use_container_width=True); plt.close(_fig_s)
                            else:
                                st.info("All claims scored 0 — no indicators found with available columns.")

                        st.markdown('<div class="sec-head">Claim-Level Results</div>', unsafe_allow_html=True)
                        _filt_re = _re_out[
                            (_re_out["_score"] >= _re_min_score) &
                            (_re_out["_decision"].isin(
                                _re_decision_filter if _re_decision_filter
                                else ["APPROVE","FLAG","HOLD","BLOCK"]))
                        ].copy().sort_values("_score", ascending=False)

                        _sc_cols   = ["_score","_risk","_decision","_n_rules","_rules_fired","_reasons"]
                        _orig_disp = [c for c in _re_out.columns
                            if not c.startswith("_") and c not in ("name","generic_description")][:10]

                        paginate_df(
                            _filt_re[[c for c in _sc_cols + _orig_disp if c in _filt_re.columns]],
                            key="re_claims", page_size=int(_re_page_size), height=500,
                            search_placeholder="Patient ID, drug code, voucher, rule ID...",
                        )

                        st.markdown('<div class="sec-head">⬇️ Export</div>', unsafe_allow_html=True)
                        _ex1, _ex2, _ex3 = st.columns(3)
                        with _ex1:
                            _fl = _re_out[_re_out["_decision"].isin(["FLAG","HOLD","BLOCK"])]
                            st.download_button(
                                f"⬇️ Flagged claims CSV ({len(_fl):,})",
                                data=_fl.to_csv(index=False).encode(),
                                file_name="pharmascan_flagged.csv",
                                mime="text/csv", key="re_dl_flag",
                            )
                        with _ex2:
                            st.download_button(
                                f"⬇️ All {len(_re_out):,} claims + scores",
                                data=_re_out.to_csv(index=False).encode(),
                                file_name="pharmascan_all_scored.csv",
                                mime="text/csv", key="re_dl_all",
                            )
                        with _ex3:
                            if st.button("📊 Generate Excel Report (5 sheets)",
                                key="re_gen_xlsx", type="primary"):
                                with st.spinner("Generating professional Excel report..."):
                                    try:
                                        _xb = export_rules_excel(_re_out, _re_summary)
                                        st.session_state["re_xlsx"] = _xb
                                    except Exception as _xe:
                                        st.error(f"Export error: {_xe}")
                            if "re_xlsx" in st.session_state:
                                st.download_button(
                                    "⬇️ Download Excel Report (.xlsx)",
                                    data=st.session_state["re_xlsx"],
                                    file_name="pharmascan_fraud_report.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    key="re_dl_xlsx",
                                )

                        _doc_col_re = next((c for c in ["doctor_type","doctor_name"]
                            if c in _re_out.columns), None)
                        if _doc_col_re:
                            st.markdown('<div class="sec-head">Provider Risk Ranking</div>',
                                unsafe_allow_html=True)
                            _amt_re = next((c for c in ["insurance_copay","amount"]
                                if c in _re_out.columns), None)
                            _prov_agg = _re_out.groupby(_doc_col_re).agg(
                                total_claims = ("_score","count"),
                                avg_score    = ("_score","mean"),
                                max_score    = ("_score","max"),
                                flagged      = ("_decision", lambda x: x.isin(["FLAG","HOLD","BLOCK"]).sum()),
                                blocked      = ("_decision", lambda x: (x == "BLOCK").sum()),
                            ).reset_index()
                            if _amt_re:
                                _prov_agg["total_ins_rwf"] = _re_out.groupby(_doc_col_re)[_amt_re].sum().values
                            _prov_agg["flag_rate_%"] = (
                                100 * _prov_agg["flagged"] /
                                _prov_agg["total_claims"].clip(lower=1)
                            ).round(1)
                            _prov_agg["avg_score"] = _prov_agg["avg_score"].round(1)
                            _prov_agg = _prov_agg.sort_values("flag_rate_%", ascending=False)
                            def _prov_sty(v):
                                try:
                                    n = float(str(v).replace("%",""))
                                    if n >= 60: return "color:#ef4444;font-weight:bold"
                                    if n >= 30: return "color:#f59e0b;font-weight:bold"
                                except Exception: pass
                                return ""
                            paginate_df(_prov_agg, key="re_prov", page_size=50, height=380,
                                search_placeholder="Provider name...")
