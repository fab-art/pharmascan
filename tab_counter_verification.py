""" tab_counter_verification.py — RSSB counter-verification Excel report generator. """
import io
import re
import streamlit as st
import pandas as pd
from exporter import generate_counter_verification_xlsx


def render(tab, df, col_map):
    with tab:
        # ══ COUNTER-VERIFICATION REPORT TAB ══════════════════════════════════════════
        with tab_cv:
            st.markdown('<div class="sec-head">📄 Counter-Verification Report Generator</div>',
                        unsafe_allow_html=True)

            st.markdown("""
        <div class="info-banner">
          <b>How it works:</b><br>
          Upload the annotated voucher file — the same invoice report with two extra columns
          added by the verifier: <b style='color:#00e5a0'>Difference</b> (deduction amount in RWF)
          and <b style='color:#00e5a0'>Observation</b> (reason for deduction). Rows without a
          deduction are simply left blank in those columns.<br><br>
          The app reads those columns, matches records by Paper Code, and generates the
          official two-sheet counter-verification Excel report automatically.
        </div>""", unsafe_allow_html=True)

            # ── STEP 1 — Upload annotated file ────────────────────────────────────
            st.markdown('<div class="sec-head">📂 Step 1 — Upload Annotated Voucher File</div>',
                        unsafe_allow_html=True)

            cv_upload = st.file_uploader(
                "Upload annotated file (Excel / CSV)",
                type=["xlsx", "xls", "csv"],
                key="cv_upload",
                help="Must be the invoice report with Difference and Observation columns filled in for deducted rows.",
            )

            # ── Parse uploaded file ────────────────────────────────────────────────
            ann_df = None
            deduction_list = []

            if cv_upload is not None:
                try:
                    raw_bytes = cv_upload.read()
                    fname = cv_upload.name.lower()
                    if fname.endswith(".csv"):
                        raw_ann = pd.read_csv(io.BytesIO(raw_bytes), encoding="utf-8",
                                              on_bad_lines="skip")
                    else:
                        # Try each sheet — prefer one named Sheet1, or the one with most rows
                        xl_ann = pd.ExcelFile(io.BytesIO(raw_bytes))
                        sheet_candidates = []
                        for sn in xl_ann.sheet_names:
                            try:
                                tmp = xl_ann.parse(sn, header=0)
                                sheet_candidates.append((sn, tmp))
                            except Exception:
                                pass

                        # Prefer sheet whose columns contain "difference" or "observation"
                        # AND whose difference column contains meaningful deduction amounts
                        # (not just tiny rounding artifacts < 100 RWF).
                        def score_sheet(df_):
                            cols = " ".join(df_.columns.astype(str).str.lower())
                            if not ("diff" in cols or "observ" in cols or "remark" in cols):
                                return False
                            # Validate: difference column must have at least one value > 100
                            # to distinguish real deductions from rounding artifacts
                            for col in df_.columns:
                                if re.search(r"diff|deduct|deduit", str(col).lower()):
                                    vals = pd.to_numeric(df_[col], errors="coerce").dropna()
                                    if len(vals) > 0 and vals.abs().max() > 100:
                                        return True
                            # Has "observ"/"remark" column but no meaningful difference values —
                            # could still be a valid annotated sheet if observation is non-empty
                            for col in df_.columns:
                                if re.search(r"observ|remark|reason|explan", str(col).lower()):
                                    non_blank = df_[col].dropna()
                                    non_blank = non_blank[non_blank.astype(str).str.strip() != ""]
                                    if len(non_blank) > 0:
                                        return True
                            return False

                        preferred = next(
                            ((sn, d) for sn, d in sheet_candidates if score_sheet(d)),
                            None
                        )
                        # If no sheet passed validation, fall back to largest sheet by row count
                        if preferred is None:
                            preferred = max(sheet_candidates, key=lambda x: len(x[1]),
                                            default=(None, None))
                        chosen_sheet, raw_ann = preferred

                    # ── Auto-detect columns ──────────────────────────────────────
                    def _normalise_col(c):
                        import re as _re
                        return _re.sub(r"[^a-z0-9]", "_",
                                       str(c).lower().strip()).strip("_")

                    col_norm = {_normalise_col(c): c for c in raw_ann.columns}

                    def _find_col(patterns):
                        for pat in patterns:
                            for norm, orig in col_norm.items():
                                if re.search(pat, norm):
                                    return orig
                        return None

                    detected = {
                        "paper_code":  _find_col([r"paper_?code", r"voucher_?no", r"invoice_?no",
                                                  r"invoice_?id", r"id_?invoice", r"claim_?no",
                                                  r"ref_?no", r"receipt_?no", r"doc_?no"]),
                        "rama":        _find_col([r"rama", r"affil", r"member", r"benef"]),
                        "patient":     _find_col([r"patient_?name", r"beneficiary_?name",
                                                  r"client_?name", r"nom"]),
                        "difference":  _find_col([r"diff", r"deduct", r"deduit", r"montant_ded",
                                                  r"amount_ded", r"ded_amount"]),
                        "observation": _find_col([r"observ", r"remark", r"reason", r"explan",
                                                  r"comment", r"note", r"justif", r"motif"]),
                        "ins_copay":   _find_col([r"insurance_co", r"ins_cop", r"couverture",
                                                  r"rama_amount"]),
                        "total_cost":  _find_col([r"total_cost", r"total", r"amount", r"cout"]),
                        "visit_date":  _find_col([r"dispensing", r"visit_date", r"date"]),
                        "doctor":      _find_col([r"practitioner", r"prescriber", r"doctor",
                                                  r"medecin"]),
                    }

                    # ── Warn if file looks like a raw (un-annotated) voucher report ──
                    _diff_col = detected.get("difference")
                    _obs_col  = detected.get("observation")
                    _has_real_diffs = False
                    _has_real_obs   = False
                    if _diff_col and _diff_col in raw_ann.columns:
                        _diff_vals = pd.to_numeric(raw_ann[_diff_col], errors="coerce").dropna()
                        _has_real_diffs = len(_diff_vals) > 0 and _diff_vals.abs().max() > 100
                    if _obs_col and _obs_col in raw_ann.columns:
                        _obs_vals = raw_ann[_obs_col].dropna()
                        _obs_vals = _obs_vals[_obs_vals.astype(str).str.strip() != ""]
                        _has_real_obs = len(_obs_vals) > 0

                    if not _diff_col and not _obs_col:
                        st.warning(
                            "⚠️ No **Difference** or **Observation** columns detected in this file. "
                            "This looks like a raw voucher report that hasn't been annotated yet. "
                            "Please add a **Difference** column (deduction amount in RWF) and an "
                            "**Observation** column (reason for deduction) to each deducted row, "
                            "then re-upload."
                        )
                    elif _diff_col and not _has_real_diffs:
                        st.warning(
                            f"⚠️ The detected **Difference** column (*{_diff_col}*) contains only "
                            f"very small values (< 100 RWF). This is likely a rounding artifact, "
                            f"not real counter-verification deductions. "
                            f"Please fill in the actual deduction amounts (e.g. 20,000 RWF) "
                            f"in that column before generating the report."
                        )
                    if _diff_col and _has_real_diffs and not _has_real_obs:
                        st.warning(
                            f"⚠️ The **Observation** column (*{_obs_col or 'not found'}*) is empty. "
                            f"No deduction reasons will appear in the report. "
                            f"Please fill in the reason for each deduction."
                        )

                    st.session_state["ann_df"]       = raw_ann
                    st.session_state["ann_detected"] = detected

                except Exception as e:
                    st.error(f"❌ Could not read file: {e}")
                    import traceback; st.code(traceback.format_exc())

            # Load from session state if already uploaded
            if "ann_df" in st.session_state:
                raw_ann  = st.session_state["ann_df"]
                detected = st.session_state["ann_detected"]

                # ── STEP 2 — Confirm / override column mapping ─────────────────────
                st.markdown('<div class="sec-head">🔗 Step 2 — Confirm Column Mapping</div>',
                            unsafe_allow_html=True)
                st.markdown("""
        <div style='font-size:11px;color:#64748b;margin-bottom:10px;font-family:monospace'>
          Columns detected automatically. Correct any mismatches — only
          <b style='color:#e2e8f0'>Paper Code</b>, <b style='color:#e2e8f0'>Difference</b>
          and <b style='color:#e2e8f0'>Observation</b> are required.
        </div>""", unsafe_allow_html=True)

                col_opts = ["(none)"] + raw_ann.columns.tolist()
                def _sel_idx(col_name):
                    return col_opts.index(col_name) if col_name in col_opts else 0

                cc1, cc2, cc3 = st.columns(3)
                with cc1:
                    sel_pc  = st.selectbox("📄 Paper Code",
                                           col_opts, index=_sel_idx(detected["paper_code"]),
                                           key="cv_sel_pc")
                    sel_obs = st.selectbox("💬 Observation / Reason",
                                           col_opts, index=_sel_idx(detected["observation"]),
                                           key="cv_sel_obs")
                with cc2:
                    sel_dif = st.selectbox("💰 Difference (amount deducted)",
                                           col_opts, index=_sel_idx(detected["difference"]),
                                           key="cv_sel_dif")
                    sel_ins = st.selectbox("🏥 Insurance Co-payment",
                                           col_opts, index=_sel_idx(detected["ins_copay"]),
                                           key="cv_sel_ins")
                with cc3:
                    sel_tot = st.selectbox("💵 Total Cost",
                                           col_opts, index=_sel_idx(detected["total_cost"]),
                                           key="cv_sel_tot")
                    sel_pat = st.selectbox("👤 Patient Name",
                                           col_opts, index=_sel_idx(detected["patient"]),
                                           key="cv_sel_pat")

                # Preview
                with st.expander("🔍 Preview uploaded file", expanded=False):
                    st.dataframe(raw_ann.head(30), use_container_width=True, height=280)

                # ── Build deduction list ─────────────────────────────────────────
                if sel_pc != "(none)" and sel_dif != "(none)":

                    def _to_float(v):
                        if v is None or (isinstance(v, float) and pd.isna(v)):
                            return 0.0
                        try:
                            return float(str(v).replace(",", "").replace(" ", ""))
                        except ValueError:
                            return 0.0

                    ann_work = raw_ann.copy()
                    ann_work["_pc"]  = ann_work[sel_pc].astype(str).str.strip()
                    ann_work["_dif"] = ann_work[sel_dif].apply(_to_float)
                    ann_work["_obs"] = (ann_work[sel_obs].fillna("").astype(str).str.strip()
                                        if sel_obs != "(none)" else "")
                    ann_work["_ins"] = (ann_work[sel_ins].apply(_to_float)
                                        if sel_ins != "(none)" else 0.0)
                    ann_work["_tot"] = (ann_work[sel_tot].apply(_to_float)
                                        if sel_tot != "(none)" else 0.0)
                    ann_work["_pat"] = (ann_work[sel_pat].fillna("").astype(str).str.strip()
                                        if sel_pat != "(none)" else "")

                    # Identify real deduction rows.
                    # Handles both sign conventions (positive or negative = deducted).
                    # Keeps a row when EITHER:
                    #   • |difference| >= 100 RWF  (meaningful amount even if no note), OR
                    #   • observation is non-blank  (annotated by verifier, even if small)
                    # This discards sub-100-RWF rounding artifacts that have no annotation.
                    _has_obs   = ann_work["_obs"].str.strip() != ""
                    _big_amt   = ann_work["_dif"].abs() >= 100
                    deducted_rows = ann_work[_big_amt | _has_obs].copy()

                    # Pull RAMA from main loaded df if possible
                    rama_lookup = {}
                    vid_main = "voucher_id" if "voucher_id" in df.columns else None
                    pid_main = "patient_id" if "patient_id" in df.columns else None
                    if vid_main and pid_main:
                        for _, r in df[[vid_main, pid_main]].iterrows():
                            rama_lookup[str(r[vid_main]).strip()] = str(r[pid_main]).strip()

                    deduction_list = []
                    for _, r in deducted_rows.iterrows():
                        pc   = r["_pc"]
                        rama = rama_lookup.get(pc, "—")
                        deduction_list.append({
                            "paper_code":  pc,
                            "rama_no":     rama,
                            "patient":     r["_pat"],
                            "amount":      -abs(r["_dif"]),  # always negative regardless of source sign
                            "explanation": r["_obs"],
                            "ins_copay":   r["_ins"],
                            "total_cost":  r["_tot"],
                        })

                    # ── STEP 3 — Deduction summary ─────────────────────────────
                    st.markdown('<div class="sec-head">📊 Step 3 — Deduction Summary</div>',
                                unsafe_allow_html=True)

                    total_ded    = sum(d["amount"]   for d in deduction_list)
                    total_ins    = ann_work["_ins"].sum() if sel_ins != "(none)" else 0
                    net_payable  = total_ins - total_ded

                    sm1, sm2, sm3, sm4 = st.columns(4)
                    sm1.metric("Rows with deductions",    f"{len(deduction_list):,}")
                    sm2.metric("Total deducted (RWF)",    f"{total_ded:,.0f}")
                    sm3.metric("Total insurance claims",  f"{total_ins:,.0f}")
                    sm4.metric("Net payable (RWF)",       f"{net_payable:,.0f}")

                    # Observation breakdown
                    obs_counts = {}
                    for d in deduction_list:
                        key = d["explanation"].strip().lower()
                        obs_counts[key] = obs_counts.get(key, 0) + 1
                    if obs_counts:
                        st.markdown("""
        <div style='font-size:11px;color:#64748b;font-family:monospace;margin:8px 0 4px'>
          <b style='color:#e2e8f0'>Deduction reasons breakdown:</b>
        </div>""", unsafe_allow_html=True)
                        reason_cols = st.columns(min(len(obs_counts), 4))
                        for i, (reason, cnt) in enumerate(
                                sorted(obs_counts.items(), key=lambda x: -x[1])):
                            reason_cols[i % len(reason_cols)].metric(
                                reason[:40] or "(blank)", cnt)

                    # Deduction table
                    ded_tbl = pd.DataFrame([{
                        "#":             i + 1,
                        "Paper Code":    d["paper_code"],
                        "Patient":       d["patient"],
                        "RAMA No.":      d["rama_no"],
                        "Ins. Co-pay":   d["ins_copay"],
                        "Deducted (RWF)":d["amount"],
                        "Observation":   d["explanation"],
                    } for i, d in enumerate(deduction_list)])
                    st.dataframe(ded_tbl, use_container_width=True, height=320)

                else:
                    st.info("👆 Assign at least the **Paper Code** and **Difference** columns above to continue.")

                # ── STEP 4 — Report metadata ───────────────────────────────────────
                if deduction_list:
                    st.markdown('<div class="sec-head">📋 Step 4 — Report Metadata</div>',
                                unsafe_allow_html=True)

                    mc1, mc2 = st.columns(2)
                    with mc1:
                        cv_province = st.text_input("Province",                value="WESTERN PROVINCE", key="cv_prov")
                        cv_district = st.text_input("Administrative District", value="RUBAVU",            key="cv_dist")
                        cv_pharmacy = st.text_input("Pharmacy",
                            value="PHARMACIE VINCA GISENYI LTD", key="cv_pharm")
                    with mc2:
                        if "date_min" in s and "date_max" in s:
                            default_period = f"{s['date_min']} to {s['date_max']}"
                        else:
                            default_period = ""
                        cv_period  = st.text_input("Period",          value=default_period, key="cv_per")
                        cv_code    = st.text_input("Code",            value="",             key="cv_code")
                        cv_prep    = st.text_input("Prepared by",     value="",             key="cv_prep")

                    sc1, sc2 = st.columns(2)
                    with sc1:
                        cv_verified = st.text_input("Verified by",
                            value="Alphonsine MUKAKAYIBANDA", key="cv_verif")
                    with sc2:
                        cv_approved = st.text_input("Approved by", value="", key="cv_approv")

                    # ── STEP 5 — Generate ──────────────────────────────────────────
                    st.markdown('<div class="sec-head">⬇️ Step 5 — Generate Report</div>',
                                unsafe_allow_html=True)

                    if st.button("📊 Generate Counter-Verification Excel Report",
                                 type="primary", key="cv_gen_btn"):
                        meta = {
                            "province": cv_province,
                            "district": cv_district,
                            "pharmacy": cv_pharmacy,
                            "period":   cv_period,
                            "code":     cv_code,
                        }

                        # Merge annotated file into df for Sheet1 (use uploaded file rows)
                        # Build a combined df from ann_work so we have Difference + Observation
                        ann_for_report = ann_work.copy()

                        with st.spinner("Building Excel report…"):
                            try:
                                xlsx_bytes = generate_counter_verification_xlsx(
                                    df          = ann_for_report,
                                    deductions  = deduction_list,
                                    meta        = meta,
                                    prepared_by = cv_prep,
                                    verified_by = cv_verified,
                                    approved_by = cv_approved,
                                    pc_col      = sel_pc,
                                    ins_col     = sel_ins if sel_ins != "(none)" else None,
                                    tot_col     = sel_tot if sel_tot != "(none)" else None,
                                    obs_col     = sel_obs if sel_obs != "(none)" else None,
                                    dif_col     = sel_dif,
                                )
                                st.session_state["cv_xlsx"]      = xlsx_bytes
                                st.session_state["cv_generated"] = True
                                st.session_state["cv_fname_meta"] = (cv_pharmacy, cv_period)
                            except Exception as e:
                                st.error(f"❌ Failed to generate report: {e}")
                                import traceback; st.code(traceback.format_exc())

                    if st.session_state.get("cv_generated"):
                        pharm_s, period_s = st.session_state.get("cv_fname_meta", ("pharmacy", "period"))
                        fname = (f"counter_verification_"
                                 f"{pharm_s.replace(' ','_')[:25]}_"
                                 f"{period_s.replace(' ','_').replace('/','')[:15]}.xlsx")
                        st.success("✅ Report ready!")
                        st.download_button(
                            label     = "⬇️ Download Counter-Verification Report (.xlsx)",
                            data      = st.session_state["cv_xlsx"],
                            file_name = fname,
                            mime      = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key       = "cv_download",
                        )
                        st.markdown("""
        <div style='font-size:12px;color:#64748b;font-family:monospace;margin-top:8px'>
          <b style='color:#e2e8f0'>Sheet 1</b> — "After counter verification":
          full records table with 100% and 85% columns; deducted rows highlighted in amber.<br>
          <b style='color:#e2e8f0'>Sheet 2</b> — "Counter verification report":
          official summary with deduction list, totals, and signature block.
        </div>""", unsafe_allow_html=True)

            else:
                st.info("👆 Upload your annotated voucher file to get started.")

