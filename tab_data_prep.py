""" tab_data_prep.py — Intelligent column mapping wizard for any Excel/CSV. """
import io
import streamlit as st
import pandas as pd
from data_prep import (auto_map_columns, apply_column_mapping,
                       _SYSTEM_FIELDS, _GROUPS_ORDER, _GROUP_COLORS)


def render(tab):
    with tab:
        with tab_dataprep:
            st.markdown('''
        <div style="background:#111720;border:1px solid #1e2a38;border-left:3px solid #0ea5e9;
             border-radius:10px;padding:14px 18px;margin-bottom:20px">
          <b style="color:#0ea5e9">🗂️ Data Preparation Wizard</b><br>
          <span style="font-size:12px;color:#64748b">
          Upload <b>any</b> Excel or CSV. The system scans every column, fingerprints its content,
          and proposes a mapping to the 17 system fields used by the rules engine and analytics.
          Override any mapping, exclude columns, then export a clean ready-to-analyse file.
          </span>
        </div>''', unsafe_allow_html=True)

            dp_upload = st.file_uploader(
                "Upload file to prepare (Excel or CSV)",
                type=["csv","xlsx","xls","ods"],
                key="dp_upload",
            )

            _dp_df = None

            if dp_upload is not None:
                try:
                    _dp_bytes = dp_upload.read()
                    _dp_fname = dp_upload.name.lower()
                    if _dp_fname.endswith(".csv"):
                        _dp_df = pd.read_csv(io.BytesIO(_dp_bytes), encoding="utf-8",
                                             on_bad_lines="skip")
                    elif _dp_fname.endswith(".ods"):
                        _dp_df = pd.read_excel(io.BytesIO(_dp_bytes), engine="odf")
                    else:
                        _xl = pd.ExcelFile(io.BytesIO(_dp_bytes))
                        _best_sh = max(_xl.sheet_names,
                                       key=lambda s: len(_xl.parse(s, nrows=5).columns))
                        _dp_df = _xl.parse(_best_sh)
                except Exception as _e:
                    st.error(f"Could not load file: {_e}")

            if _dp_df is not None:
                # Run profiler
                with st.spinner("Profiling columns…"):
                    _dp_mapping, _dp_scores, _dp_profiles = auto_map_columns(_dp_df)

                # ── Summary metrics ─────────────────────────────────────────────────
                _n_mapped   = len(_dp_mapping)
                _n_required = sum(1 for f, d in _SYSTEM_FIELDS.items()
                                  if d["required"] and f in _dp_mapping)
                _n_req_total = sum(1 for d in _SYSTEM_FIELDS.values() if d["required"])
                _n_unmapped = len(_dp_df.columns) - _n_mapped

                _pm1, _pm2, _pm3, _pm4 = st.columns(4)
                _pm1.metric("Total columns",   len(_dp_df.columns))
                _pm2.metric("Auto-mapped",     _n_mapped)
                _pm3.metric("Required fields", f"{_n_required}/{_n_req_total}")
                _pm4.metric("Unmapped cols",   _n_unmapped)

                # ── Column profile table ─────────────────────────────────────────────
                st.markdown('<div class="sec-head">Column Profiles</div>', unsafe_allow_html=True)

                _profile_rows = []
                for col in _dp_df.columns:
                    prof = _dp_profiles.get(col, {})
                    mapped_to = _dp_mapping.get(
                        next((f for f, c in _dp_mapping.items() if c == col), ""), ""
                    )
                    # find field from reverse mapping
                    _mapped_field = next((f for f, c in _dp_mapping.items() if c == col), "—")
                    _field_label  = (_SYSTEM_FIELDS[_mapped_field]["label"]
                                     if _mapped_field in _SYSTEM_FIELDS else "—")
                    _group        = (_SYSTEM_FIELDS[_mapped_field]["group"]
                                     if _mapped_field in _SYSTEM_FIELDS else "—")
                    _best_score   = max(_dp_scores.get(col, {}).values(), default=0)

                    _profile_rows.append({
                        "Original Column": col,
                        "Dtype":          prof.get("dtype","?"),
                        "Non-null %":     f"{100-prof.get('null_pct',0):.0f}%",
                        "Unique":         prof.get("unique","?"),
                        "Sample":         " | ".join(prof.get("samples",[])[:3]),
                        "→ System Field": _field_label,
                        "Group":          _group,
                        "Confidence":     f"{_best_score*100:.0f}%",
                    })

                _prof_df = pd.DataFrame(_profile_rows)

                def _highlight_confidence(val):
                    try:
                        v = int(val.replace("%",""))
                        if v >= 70: return "color:#00e5a0;font-weight:bold"
                        if v >= 40: return "color:#f59e0b"
                        if v >  0:  return "color:#ef4444"
                    except Exception:
                        pass
                    return "color:#64748b"

                st.dataframe(
                    _prof_df.style.map(_highlight_confidence, subset=["Confidence"]),
                    use_container_width=True, height=320,
                )

                # ── Interactive mapping editor ────────────────────────────────────────
                st.markdown('<div class="sec-head">Edit Column Mapping</div>', unsafe_allow_html=True)
                st.markdown('''
        <div style="font-size:11px;color:#64748b;font-family:monospace;margin-bottom:12px">
          Review each column. Change the system field assignment or set to <b>Exclude</b> /
          <b>Keep as raw_</b>. Confident mappings (≥70%) are pre-selected.
        </div>''', unsafe_allow_html=True)

                # Build reverse mapping for current state
                _reverse = {c: f for f, c in _dp_mapping.items()}
                _sys_field_options = (
                    ["— (keep as raw_)", "× exclude"] +
                    [f"{d['group']} › {f} — {d['label']}"
                     for f, d in _SYSTEM_FIELDS.items()]
                )
                _field_from_opt = {
                    f"{d['group']} › {f} — {d['label']}": f
                    for f, d in _SYSTEM_FIELDS.items()
                }

                _user_mapping = {}   # system_field -> original_col (from UI)
                _exclude_cols = set()

                _grp_cols = {}
                for col in _dp_df.columns:
                    fld = _reverse.get(col, "")
                    grp = (_SYSTEM_FIELDS[fld]["group"] if fld in _SYSTEM_FIELDS else "Unmapped")
                    _grp_cols.setdefault(grp, []).append(col)

                _grp_order = _GROUPS_ORDER + ["Unmapped"]
                for _grp in _grp_order:
                    _gcols = _grp_cols.get(_grp, [])
                    if not _gcols:
                        continue
                    _gc = _GROUP_COLORS.get(_grp, "#64748b")
                    st.markdown(
                        f'<div style="font-size:11px;font-weight:700;color:{_gc};'
                        f'text-transform:uppercase;letter-spacing:.06em;'
                        f'margin:16px 0 8px">{_grp}</div>',
                        unsafe_allow_html=True,
                    )
                    _row_cols = st.columns(3)
                    for _ci, col in enumerate(_gcols):
                        fld = _reverse.get(col, "")
                        conf = max(_dp_scores.get(col, {}).values(), default=0)
                        # Default select option
                        if fld in _SYSTEM_FIELDS:
                            _default_opt = f"{_SYSTEM_FIELDS[fld]['group']} › {fld} — {_SYSTEM_FIELDS[fld]['label']}"
                        else:
                            _default_opt = "— (keep as raw_)"

                        _conf_color = "#00e5a0" if conf >= 0.7 else "#f59e0b" if conf >= 0.4 else "#64748b"
                        _row_cols[_ci % 3].markdown(
                            f'<div style="font-size:10px;color:{_conf_color};font-family:monospace;'
                            f'margin-bottom:2px">{col[:40]} — {conf*100:.0f}% confidence</div>',
                            unsafe_allow_html=True,
                        )
                        _sel = _row_cols[_ci % 3].selectbox(
                            col[:30],
                            options=_sys_field_options,
                            index=(_sys_field_options.index(_default_opt)
                                   if _default_opt in _sys_field_options else 0),
                            key=f"dp_map_{col}",
                            label_visibility="collapsed",
                        )
                        if _sel == "× exclude":
                            _exclude_cols.add(col)
                        elif _sel != "— (keep as raw_)":
                            _f = _field_from_opt.get(_sel)
                            if _f:
                                _user_mapping[_f] = col

                # ── Preview & Export ─────────────────────────────────────────────────
                st.markdown("<br>", unsafe_allow_html=True)
                _ec1, _ec2 = st.columns([1, 2])

                with _ec1:
                    st.markdown(
                        f'<p style="font-size:12px;color:#64748b;font-family:monospace">'
                        f'{len(_user_mapping)} system fields mapped · {len(_exclude_cols)} excluded</p>',
                        unsafe_allow_html=True,
                    )
                    _do_apply_dp = st.button("✅ Apply Mapping & Preview",
                                              type="primary", key="dp_apply")

                if _do_apply_dp or st.session_state.get("dp_result") is not None:
                    if _do_apply_dp:
                        _clean = apply_column_mapping(
                            _dp_df.drop(columns=list(_exclude_cols), errors="ignore"),
                            _user_mapping,
                        )
                        st.session_state["dp_result"] = _clean
                        st.session_state["dp_map_used"] = _user_mapping

                    _clean = st.session_state["dp_result"]
                    _map_used = st.session_state.get("dp_map_used", {})

                    # Summary
                    st.success(
                        f"✅ Mapping applied. {len(_map_used)} system fields · "
                        f"{len([c for c in _clean.columns if c.startswith('raw_')])} raw_ columns preserved."
                    )

                    # Show mapped field chips
                    _chips_html = "".join(
                        f'<span style="background:rgba({",".join(str(int(c[1:3],16)) + "," + str(int(c[3:5],16)) + "," + str(int(c[5:],16)) for c in [_GROUP_COLORS.get(_SYSTEM_FIELDS.get(f,{}).get('group','Financial'),'#64748b')])},0.12);'
                        f'border:1px solid {_GROUP_COLORS.get(_SYSTEM_FIELDS.get(f,{}).get('group','Financial'),'#64748b')};'
                        f'border-radius:6px;padding:3px 10px;font-size:11px;font-family:monospace;'
                        f'color:{_GROUP_COLORS.get(_SYSTEM_FIELDS.get(f,{}).get('group','Financial'),'#64748b')};'
                        f'margin:2px">{f}</span>'
                        for f in _map_used
                        if f in _SYSTEM_FIELDS
                    )
                    if _chips_html:
                        st.markdown(
                            f'<div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px">{_chips_html}</div>',
                            unsafe_allow_html=True,
                        )

                    # Preview table
                    st.markdown('<div class="sec-head">Prepared Data Preview</div>', unsafe_allow_html=True)
                    st.dataframe(_clean.head(100), use_container_width=True, height=380)

                    # Downloads
                    _dc1, _dc2 = st.columns(2)
                    with _dc1:
                        _csv_dp = _clean.to_csv(index=False).encode()
                        st.download_button(
                            "⬇️ Download prepared CSV",
                            data=_csv_dp,
                            file_name=f"pharmascan_prepared_{dp_upload.name.rsplit('.',1)[0]}.csv",
                            mime="text/csv",
                            key="dp_download_csv",
                        )
                    with _dc2:
                        _map_df = pd.DataFrame(
                            [(f, c, _SYSTEM_FIELDS.get(f,{}).get('label','—'))
                             for f,c in _map_used.items()],
                            columns=["System Field","Original Column","Description"]
                        )
                        _csv_map = _map_df.to_csv(index=False).encode()
                        st.download_button(
                            "⬇️ Download mapping report",
                            data=_csv_map,
                            file_name="column_mapping_report.csv",
                            mime="text/csv",
                            key="dp_download_map",
                        )

            else:
                st.info("👆 Upload any Excel or CSV file above to begin column profiling.")


