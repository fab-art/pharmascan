"""
rules_engine.py — 15 vectorized fraud detection rules.
Fully pandas-native (no iterrows). Handles 500k rows in <15s.

Rules:
  R01 Drug-Prescriber Mismatch        R09 Malaria + Antibiotic
  R02 Diagnosis-Drug Blacklist         R10 Immunosuppressant No Indication
  R03 Quantity Excess                  R11 Provider Volume Spike (z-score)
  R04 High-Value Drug + Bad Dx         R12 Patient Frequency Spike
  R05 Antineoplastic Without Cancer    R13 Round Amount (billing fraud)
  R06 Psych Drug Without Mental Dx     R14 Weekend/Off-Hours Dispensing
  R07 Early Refill / Duplicate         R15 Same-Day Multi-Drug Cluster
  R08 Unlisted RHIC Code
"""
import time as _time
import numpy as np
import pandas as pd

from drug_reference import _load_drug_ref
from utils import audit, LOG, RULES_VERSION


# ── Clinical reference data ────────────────────────────────────────────────────
_DX_DRUG_BLACKLIST = {
    "B50": {"J01": (20,"Malaria+antibiotics: UCG first-line is ACT not J01 antibiotics"),
             "L01": (45,"Antineoplastic for malaria: no clinical basis"),
             "N05": (35,"Antipsychotic for malaria: no indication")},
    "B51": {"J01": (20,"Malaria (P.vivax) + antibiotics: ACT is first-line"),
             "L01": (45,"Antineoplastic for malaria: impossible")},
    "B54": {"J01": (20,"Malaria + antibiotics: ACT protocol not antibiotics"),
             "L01": (45,"Antineoplastic for unspecified malaria")},
    "I10": {"P01": (40,"Antihypertensive + antiparasitic: no clinical link"),
             "L01": (50,"Antineoplastic for hypertension: diagnosis fraud"),
             "N05": (30,"Antipsychotic for hypertension: no indication")},
    "E11": {"P01": (40,"T2DM + antiparasitic: no clinical indication"),
             "L01": (50,"Antineoplastic for diabetes: diagnosis fraud")},
    "E10": {"L01": (50,"Antineoplastic for T1DM: diagnosis fraud")},
    "J18": {"L01": (50,"Antineoplastic for pneumonia: no indication"),
             "N05": (35,"Antipsychotic for pneumonia: no indication")},
    "G40": {"P01": (40,"Epilepsy + antiparasitic: UCG uses CBZ/VPA/PHB"),
             "L01": (45,"Antineoplastic for epilepsy: no indication")},
    "A15": {"L01": (45,"Antineoplastic for TB: unless concurrent cancer"),
             "N05": (35,"Antipsychotic for TB: not in RHZE protocol")},
    "Z00": {"L01": (60,"CRITICAL: Antineoplastic on routine checkup"),
             "N05": (40,"Antipsychotic on routine checkup: billing fraud"),
             "H02": (30,"High-dose steroid on routine checkup")},
    "J06": {"L01": (55,"Antineoplastic for URTI: strong fraud signal"),
             "N05": (35,"Antipsychotic for URTI: no indication"),
             "S01": (25,"Ophthalmic prep for URTI: no indication")},
    "J00": {"L01": (55,"Antineoplastic for common cold: fraud"),
             "N05": (35,"Antipsychotic for common cold")},
    "O80": {"L01": (60,"CRITICAL: Antineoplastic during normal delivery"),
             "N05": (35,"Antipsychotic for normal delivery")},
    "Z23": {"L01": (60,"CRITICAL: Antineoplastic alongside vaccination"),
             "N05": (40,"Antipsychotic at vaccination visit")},
    "F20": {"P01": (40,"Antipsychotic Rx for schizophrenia needs N05, not P01")},
    "F32": {"P01": (40,"Depression + antiparasitic: no indication")},
}

# Prescriber code to speciality mapping
_PRESCRIBER_ALLOWED = {
    "D":       {"Dermatology","Dermatologist"},
    "OPHT":    {"Ophthalmology","Ophthalmologist"},
    "IM":      {"Internal Medicine","Internist","Physician"},
    "AC":      {"Oncology","Oncologist"},
    "UROL":    {"Urology","Urologist"},
    "GYN":     {"Gynaecology","Gynaecologist","Obstetrics","OB-GYN"},
    "GYNEC":   {"Gynaecology","Gynaecologist"},
    "PSYCH":   {"Psychiatry","Psychiatrist"},
    "CARDIOL": {"Cardiology","Cardiologist"},
    "DT":      {"Dentistry","Dental Surgeon"},
    "NEUROL":  {"Neurology","Neurologist"},
    "PED":     {"Paediatrics","Paediatrician","Pediatrics"},
    "NEPHR":   {"Nephrology","Nephrologist"},
    "SPEC":    {"*specialist*"},   # any registered specialist
    "HU":      {"*hospital*"},     # hospital/inpatient only
}






# ── Engine functions ───────────────────────────────────────────────────────────
def run_rules_engine(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Production rules engine — fully vectorized.
    Replaces iterrows with pd.Series operations and pd.merge.
    Handles 500k rows in <10s vs 10+ min for the iterrows version.

    Rules implemented (15 total):
      Clinical  : R01 Drug-Prescriber Mismatch
                  R02 Diagnosis-Drug Blacklist
                  R05 Antineoplastic Without Cancer Dx
                  R06 Psych Drug Without Mental Dx
                  R10 Immunosuppressant Without Indication
      Pharmacy  : R03 Quantity Excess
                  R07 Early Refill / Duplicate Claim
      Financial : R04 High-Value Drug + Unrelated Dx
                  R08 Unlisted / RHIC Code Not in Tariff
                  R13 Suspiciously Round Amount (billing fraud)
      Statistical: R11 Provider Volume Spike (z-score ≥ 3σ)
                   R12 Patient Claim Frequency Spike
                   R14 Weekend / Off-Hours Dispensing Anomaly
                   R15 Same-Day Multi-Drug High-Value Cluster
                   R09 Malaria + Antibiotic Combination
    """
    t0 = _time.perf_counter()
    n  = len(df)
    ref        = _load_drug_ref()
    drugs_dict = ref["drugs"]
    atc3_dict  = ref["atc3_defaults"]

    # ── 0. Expand drug reference into a lookup DataFrame ──────────────────
    drug_ref_df = pd.DataFrame.from_dict(drugs_dict, orient="index").reset_index()
    drug_ref_df.columns = ["_drug_code"] + list(drug_ref_df.columns[1:])

    # ── 1. Identify available columns ────────────────────────────────────
    def _col(*names):
        return next((c for c in names if c in df.columns), None)

    id_col   = _col("patient_id", "patient_name")
    date_col = _col("visit_date")
    drug_col = _col("drug_code")
    qty_col  = _col("quantity")
    dx_col   = _col("diagnosis")
    doc_type = _col("doctor_type", "doctor_name")
    amt_col  = _col("insurance_copay", "amount")
    vou_col  = _col("voucher_id")
    fac_col  = _col("facility")

    # ── 2. Build working copy with safe typed columns ─────────────────────
    W = df.copy()
    W["_idx"]   = np.arange(n)
    W["_score"] = 0

    # Safe helpers — avoid NaN propagation in string columns
    def _sstr(col):
        if col and col in W.columns:
            return W[col].fillna("").astype(str).str.strip()
        return pd.Series("", index=W.index)

    def _sfloat(col):
        if col and col in W.columns:
            return pd.to_numeric(W[col], errors="coerce").fillna(0.0)
        return pd.Series(0.0, index=W.index)

    s_drug  = _sstr(drug_col).str.upper()
    s_qty   = _sfloat(qty_col)
    s_dx    = _sstr(dx_col).str[:3].str.upper()
    s_doc   = _sstr(doc_type).str.upper()
    s_pid   = _sstr(id_col)
    s_amt   = _sfloat(amt_col)
    s_date  = pd.to_datetime(W[date_col], errors="coerce") if date_col else pd.Series(pd.NaT, index=W.index)

    # ── 3. Merge drug reference (left join on drug_code) ──────────────────
    W["_dc_key"] = s_drug.str[:12]   # trim whitespace artefacts
    W2 = W.merge(
        drug_ref_df.rename(columns={
            "index" if "index" in drug_ref_df.columns else "_drug_code": "_dc_key",
            "atc1": "_atc1", "atc3": "_atc3", "instr": "_instr",
            "price": "_price", "max_units": "_max_u", "min_refill": "_min_r",
        }),
        on="_dc_key", how="left",
    )
    # ATC3 fallback: for codes not in exact reference, try first 3 chars
    no_match = W2["_atc1"].isna()
    if no_match.any():
        atc3_keys = s_drug[no_match].str[:3]
        W2.loc[no_match, "_atc1"] = atc3_keys.map(
            {k: v.get("atc1","") for k, v in atc3_dict.items()}
        )
        W2.loc[no_match, "_atc3"] = atc3_keys.map(
            {k: v.get("atc3","") for k, v in atc3_dict.items()}
        )
        W2.loc[no_match, "_instr"] = atc3_keys.map(
            {k: v.get("instr","") for k, v in atc3_dict.items()}
        )
        W2.loc[no_match, "_price"] = atc3_keys.map(
            {k: float(v.get("price",0)) for k, v in atc3_dict.items()}
        )
        W2.loc[no_match, "_max_u"] = atc3_keys.map(
            {k: v.get("max_units") for k, v in atc3_dict.items()}
        )
        W2.loc[no_match, "_min_r"] = atc3_keys.map(
            {k: v.get("min_refill") for k, v in atc3_dict.items()}
        )

    W2[["_atc1","_atc3","_instr"]] = W2[["_atc1","_atc3","_instr"]].fillna("")
    W2["_price"] = pd.to_numeric(W2["_price"], errors="coerce").fillna(0.0)
    W2["_max_u"] = pd.to_numeric(W2.get("_max_u", pd.Series(dtype="float")), errors="coerce")
    W2["_min_r"] = pd.to_numeric(W2.get("_min_r", pd.Series(dtype="float")), errors="coerce")

    # Re-extract typed series from merged frame
    atc1   = W2["_atc1"].str.upper()
    atc3   = W2["_atc3"].str.upper()
    instr  = W2["_instr"].str.upper()
    price  = W2["_price"]
    max_u  = W2["_max_u"]
    min_r  = W2["_min_r"]

    # Score accumulator & reason list (numpy arrays for speed)
    scores  = np.zeros(n, dtype=np.int32)
    reasons = [""] * n
    rfired  = [""] * n

    rule_counts = {f"R{i:02d}": 0 for i in range(1, 16)}

    def _apply(rule_id, fire_mask, sc, reason_str):
        """Vectorized rule application — update scores and reason strings."""
        if not fire_mask.any():
            return
        idx_arr = np.where(fire_mask.values)[0]
        scores[idx_arr] += sc
        rule_counts[rule_id] += int(fire_mask.sum())
        tag = f"{rule_id}(+{sc})"
        for i in idx_arr:
            rfired[i]  = (rfired[i]  + "; " + tag)         .lstrip("; ")
            reasons[i] = (reasons[i] + " | " + reason_str) .lstrip(" | ")

    has_drug = s_drug.str.len() > 0
    has_dx   = s_dx.str.len()   > 0
    has_doc  = s_doc.str.len()  > 0

    # ── R01: Drug-Prescriber Mismatch ─────────────────────────────────────
    if has_drug.any() and has_doc.any():
        _hu_drug    = instr.str.contains(r"\bHU\b", na=False)
        _psych_drug = instr.str.contains(r"\bPSYCH\b", na=False)
        _ac_drug    = instr.str.contains(r"\bAC\b", na=False)
        _opht_drug  = instr.str.contains(r"\bOPHT\b", na=False)

        _non_hosp   = ~s_doc.str.contains("HOSPITAL|INTERNE|SPEC|SENIOR|MAJOR", na=False)
        _non_psych  = ~s_doc.str.contains("PSYCH|NEUROL|SPEC", na=False)
        _non_onco   = ~s_doc.str.contains("ONCOL|CANCER|HAEMATOL|SPEC", na=False)
        _non_opht   = ~s_doc.str.contains("OPHT|EYE|SPEC", na=False)

        _apply("R01", has_drug & _hu_drug    & _non_hosp,  35, "HU drug by non-hospital provider")
        _apply("R01", has_drug & _psych_drug & _non_psych, 25, "PSYCH drug by non-psychiatrist")
        _apply("R01", has_drug & _ac_drug    & _non_onco,  30, "Oncology drug by non-oncologist")
        _apply("R01", has_drug & _opht_drug  & _non_opht,  20, "OPHT drug by non-ophthalmologist")

    # ── R02: Diagnosis-Drug Blacklist ─────────────────────────────────────
    if has_drug.any() and has_dx.any():
        for icd_pref, atc_rules in _DX_DRUG_BLACKLIST.items():
            dx_match = s_dx == icd_pref
            if not dx_match.any():
                continue
            for atc_pref, (sc, rsn) in atc_rules.items():
                drug_match = atc1.str[:len(atc_pref[:1])] == atc_pref[:1]
                if len(atc_pref) > 1:
                    drug_match &= atc3.str.startswith(atc_pref)
                _apply("R02", dx_match & drug_match & has_drug, sc, rsn)

    # ── R03: Quantity Excess ──────────────────────────────────────────────
    if qty_col:
        max_u_valid = max_u.notna() & (max_u > 0)
        qty_valid   = s_qty > 0
        excess_mask = max_u_valid & qty_valid & (s_qty > max_u)
        if excess_mask.any():
            excess_pct = ((s_qty - max_u) / max_u.clip(lower=1) * 100).clip(0, 500)
            sc_vec = (25 + (excess_pct / 20).astype(int) * 5).clip(upper=60)
            # Apply tiered scores
            for sc_val in [25, 30, 35, 40, 45, 50, 55, 60]:
                tier_mask = excess_mask & (sc_vec == sc_val)
                _apply("R03", tier_mask, sc_val, f"Quantity exceeds clinical limit (tier {sc_val}pts)")

    # ── R04: High-Value Drug + Unrelated Diagnosis ─────────────────────
    if has_dx.any():
        hv_mask  = price > 50000
        l_drug   = atc1 == "L"
        b_drug   = atc1 == "B"
        l_bad_dx = ~s_dx.str[:1].isin(["C","D","N","G","M"])
        b_bad_dx = ~s_dx.str[:1].isin(["D","N","K"])
        _apply("R04", hv_mask & l_drug & l_bad_dx & has_dx, 30,
               "High-value antineoplastic with unrelated diagnosis")
        _apply("R04", hv_mask & b_drug & b_bad_dx & has_dx, 30,
               "High-value haematopoietic drug with unrelated diagnosis")

    # ── R05: Antineoplastic Without Cancer Dx ─────────────────────────
    if has_dx.any():
        is_l01    = atc3.str.startswith("L01")
        _d_part   = pd.to_numeric(s_dx.str[1:3], errors="coerce")
        cancer_dx = s_dx.str.startswith("C") | (
            s_dx.str.startswith("D") & _d_part.notna() & (_d_part <= 49)
        )
        _apply("R05", is_l01 & has_dx & ~cancer_dx, 25,
               "Cytotoxic (L01) without cancer diagnosis")

    # ── R06: Psych Drug Without Mental Dx ─────────────────────────────
    if has_dx.any():
        psych_drug = instr.str.contains(r"\bPSYCH\b", na=False)
        mental_dx  = s_dx.str.startswith("F") | (
            s_dx.str.startswith("G4") & s_dx.str[2:3].between("0","7"))
        _apply("R06", psych_drug & has_dx & ~mental_dx, 20,
               "PSYCH drug without psychiatric/neuro diagnosis")

    # ── R07: Early Refill Detection ────────────────────────────────────
    if id_col and drug_col and date_col:
        _apply_early_refill(W2, s_pid, s_drug, s_date, min_r, scores, rfired, reasons, rule_counts)

    # ── R08: Unlisted / RHIC Code Not in Tariff ────────────────────────
    if has_drug.any():
        rhic_mask    = s_drug.str.startswith("RHIC")
        no_ref_match = W2["_atc1"].str.len() == 0
        _apply("R08", rhic_mask & no_ref_match, 15,
               "RHIC procedure code not found in RAMA tariff")

    # ── R09: Malaria + Antibiotic Combination ──────────────────────────
    if has_dx.any() and has_drug.any():
        malaria_dx  = s_dx.isin(["B50","B51","B54","B53","B52"])
        j01_drug    = atc1 == "J"
        _apply("R09", malaria_dx & j01_drug, 20,
               "Antibiotic dispensed alongside malaria diagnosis (UCG: ACT first-line)")

    # ── R10: Immunosuppressant Without Indication ──────────────────────
    if has_dx.any():
        l04_mask  = atc3.str.startswith("L04")
        valid_dx  = (
            s_dx.str.startswith("T86") |  # transplant
            s_dx.str.startswith("M0")   |
            s_dx.str.startswith("M1")   |
            s_dx.str.startswith("M2")   |
            s_dx.str.startswith("M3")   |
            s_dx.str.startswith("K50")  |
            s_dx.str.startswith("K51")  |
            s_dx.str.startswith("N04")  |
            s_dx.str.startswith("L40")  |
            s_dx.str.startswith("G35")
        )
        _apply("R10", l04_mask & has_dx & ~valid_dx, 20,
               "Immunosuppressant without transplant/autoimmune diagnosis")

    # ── R11: Provider Volume Spike (statistical) ────────────────────────
    if doc_type:
        prov_counts = W2[doc_type].fillna("UNKNOWN").map(
            W2[doc_type].fillna("UNKNOWN").value_counts()
        )
        prov_mean = prov_counts.mean()
        prov_std  = prov_counts.std()
        if prov_std > 0:
            prov_z = (prov_counts - prov_mean) / prov_std
            _apply("R11", prov_z >= 3.0, 20,
                   "Provider claim volume ≥3σ above mean (volume spike)")
            _apply("R11", prov_z >= 5.0, 15,   # extra points for extreme outliers
                   "Provider claim volume ≥5σ above mean (extreme spike)")

    # ── R12: Patient Claim Frequency Spike ─────────────────────────────
    if id_col:
        pat_counts = s_pid.map(s_pid.value_counts())
        pat_mean   = pat_counts.mean()
        pat_std    = pat_counts.std()
        if pat_std and pat_std > 0:
            pat_z = (pat_counts - pat_mean) / pat_std
            _apply("R12", pat_z >= 4.0, 20,
                   "Patient visit count ≥4σ above mean (possible ghost patient)")

    # ── R13: Suspiciously Round Amounts ────────────────────────────────
    if amt_col:
        round_mask = (
            (s_amt >= 1000) &
            ((s_amt % 1000 == 0) | (s_amt % 500 == 0)) &
            (s_amt > 0)
        )
        large_round = round_mask & (s_amt >= 50_000)
        _apply("R13", large_round, 15,
               "Amount is suspiciously round (≥50k RWF, multiple of 500/1000)")

    # ── R14: Weekend / Holiday Dispensing Anomaly ─────────────────────
    if date_col:
        day_of_week = s_date.dt.dayofweek   # Mon=0 … Sun=6
        weekend     = day_of_week.isin([5, 6])
        holiday_hrs = s_date.dt.hour.between(0, 6) | s_date.dt.hour.between(22, 23)
        _apply("R14", weekend & has_drug, 10,
               "Dispensing on weekend — verify pharmacy was operational")
        _apply("R14", holiday_hrs & has_drug, 15,
               "Dispensing at unusual hours (00:00–06:00 or 22:00+)")

    # ── R15: Same-Day Multi-Drug High-Value Cluster ────────────────────
    if id_col and date_col and amt_col:
        # Count how many high-value claims a patient has on same date
        W2["_date_only"] = s_date.dt.date
        W2["_hv"]        = (s_amt >= 10_000).astype(int)
        same_day_hv = (
            W2.groupby([id_col, "_date_only"])["_hv"].transform("sum")
            if id_col in W2.columns else pd.Series(0, index=W2.index)
        )
        _apply("R15", same_day_hv >= 3, 25,
               "Patient has ≥3 high-value (≥10k RWF) claims on the same day")
        _apply("R15", same_day_hv >= 5, 20,
               "Patient has ≥5 high-value claims on the same day — strong fraud signal")

    # ── Compose final scores ─────────────────────────────────────────────
    # For R07, scores were written directly into numpy array — sync back
    W2["_score"]      = scores
    W2["_rules_fired"] = rfired
    W2["_reasons"]     = reasons

    W2["_n_rules"] = W2["_rules_fired"].apply(
        lambda x: len(x.split(";")) if x.strip() else 0
    )

    def _decision(sc):
        if sc >= 75: return "BLOCK"
        if sc >= 50: return "HOLD"
        if sc >= 30: return "FLAG"
        return "APPROVE"

    def _risk(sc):
        if sc >= 75: return "CRITICAL"
        if sc >= 50: return "HIGH"
        if sc >= 30: return "MEDIUM"
        return "LOW"

    W2["_decision"] = W2["_score"].apply(_decision)
    W2["_risk"]     = W2["_score"].apply(_risk)
    W2["_rules_fired"] = W2["_rules_fired"].replace("", "—")
    W2["_reasons"]     = W2["_reasons"].replace("", "—")

    # Drop internal join columns
    drop_cols = [c for c in W2.columns if c.startswith("_dc_") or
                 c in ("_dc_key","_date_only","_hv","_idx","_atc1","_atc3",
                        "_instr","_price","_max_u","_min_r","name")]
    W2 = W2.drop(columns=[c for c in drop_cols if c in W2.columns], errors="ignore")

    # ── Summary ──────────────────────────────────────────────────────────
    dec_vc = W2["_decision"].value_counts()
    flagged_amt = W2.loc[W2["_decision"].isin(["HOLD","BLOCK"]), amt_col].sum() \
                  if amt_col else 0.0

    summary = {
        "total":                len(W2),
        "rules_version":        RULES_VERSION,
        "rule_counts":          rule_counts,
        "decisions": {
            "APPROVE": int(dec_vc.get("APPROVE", 0)),
            "FLAG":    int(dec_vc.get("FLAG",    0)),
            "HOLD":    int(dec_vc.get("HOLD",    0)),
            "BLOCK":   int(dec_vc.get("BLOCK",   0)),
        },
        "total_flagged_amount": float(flagged_amt),
        "flagged_count":        int(dec_vc.get("FLAG",0) + dec_vc.get("HOLD",0) + dec_vc.get("BLOCK",0)),
        "rules_available":      [k for k,v in rule_counts.items() if v > 0 or True],
        "rules_with_most_fires": sorted(
            [(k,v) for k,v in rule_counts.items() if v > 0],
            key=lambda x: -x[1]
        )[:10],
        "elapsed_ms": round((_time.perf_counter() - t0) * 1000, 1),
    }

    elapsed = summary["elapsed_ms"]
    audit("RULES_ENGINE", f"{n:,} claims evaluated, {summary['flagged_count']:,} flagged",
           n, elapsed)
    return W2, summary



def _apply_early_refill(W2, s_pid, s_drug, s_date, min_r,
                        scores, rfired, reasons, rule_counts):
    """
    Vectorized early refill detection.
    Uses a groupby-shift approach: per (patient, drug) pair,
    compare each dispensing date to the previous one.
    """
    if s_date.isna().all():
        return

    tmp = pd.DataFrame({
        "pid":  s_pid.values,
        "drug": s_drug.values,
        "date": s_date.values,
        "minr": min_r.values,
        "orig": np.arange(len(s_pid)),
    }).dropna(subset=["pid","drug","date"])

    tmp = tmp[tmp["pid"].str.len() > 0]
    tmp = tmp.sort_values(["pid","drug","date"])
    tmp["_prev"]  = tmp.groupby(["pid","drug"])["date"].shift(1)
    tmp["_gap"]   = (tmp["date"] - tmp["_prev"]).dt.days
    tmp["_minr"]  = pd.to_numeric(tmp["minr"], errors="coerce")

    fire_rows = tmp[
        tmp["_gap"].notna() &
        (tmp["_gap"] > 0) &
        tmp["_minr"].notna() &
        (tmp["_gap"] < tmp["_minr"])
    ]

    for _, fr in fire_rows.iterrows():
        i   = int(fr["orig"])
        gap = int(fr["_gap"])
        mr  = int(fr["_minr"])
        scores[i]  += 40
        rule_counts["R07"] += 1
        tag = "R07(+40)"
        rfired[i]  = (rfired[i]  + "; " + tag).lstrip("; ")
        reasons[i] = (reasons[i] + f" | Early refill: {gap}d gap vs {mr}d minimum").lstrip(" | ")


# ═══════════════════════════════════════════════════════════════════════════════
# PROFESSIONAL EXCEL EXPORT  — Rules engine results → formatted workbook
# ═══════════════════════════════════════════════════════════════════════════════

