"""
data_prep.py — Intelligent column mapping wizard.
Profiles every column, scores against 17 system fields, proposes mapping.
"""
import re
import pandas as pd


_SYSTEM_FIELDS = {
    "patient_id": {
        "label": "Patient / Member ID",
        "group": "Patient",
        "patterns": [r"rama", r"member.?id", r"patient.?id", r"benefi", r"insur.?no",
                     r"affil", r"no.*pat", r"num.*adh"],
        "dtype_hints": ["object", "string", "int"],
        "sample_hints": ["contains digits", "6-12 chars"],
        "required": True,
    },
    "patient_name": {
        "label": "Patient Full Name",
        "group": "Patient",
        "patterns": [r"patient.?name", r"nom.?patient", r"beneficiary.?name",
                     r"client.?name", r"full.?name", r"nom.*prenom"],
        "dtype_hints": ["object"],
        "required": False,
    },
    "visit_date": {
        "label": "Visit / Dispensing Date",
        "group": "Visit",
        "patterns": [r"dispensing.?date", r"visit.?date", r"date.?dispens",
                     r"service.?date", r"date.?service", r"date.?visite",
                     r"date.?soins", r"^date$"],
        "dtype_hints": ["datetime64", "object"],
        "required": True,
    },
    "voucher_id": {
        "label": "Voucher / Claim ID",
        "group": "Visit",
        "patterns": [r"paper.?code", r"voucher", r"claim.?id", r"claim.?no",
                     r"bon.?no", r"fiche.?no", r"reference", r"invoice.?no",
                     r"receipt.?no"],
        "dtype_hints": ["object", "string"],
        "required": False,
    },
    "doctor_name": {
        "label": "Prescriber / Doctor Name",
        "group": "Provider",
        "patterns": [r"practitioner.?name", r"doctor.?name", r"prescriber",
                     r"medecin", r"nom.?medecin", r"physician.?name",
                     r"provider.?name"],
        "dtype_hints": ["object"],
        "required": False,
    },
    "doctor_type": {
        "label": "Prescriber Type / Speciality",
        "group": "Provider",
        "patterns": [r"practitioner.?type", r"doctor.?type", r"specialit",
                     r"type.?medecin", r"provider.?type"],
        "dtype_hints": ["object"],
        "required": False,
    },
    "facility": {
        "label": "Health Facility",
        "group": "Provider",
        "patterns": [r"facility", r"hospital", r"clinic", r"pharmacy", r"pharmacie",
                     r"health.?center", r"centre.?sante", r"etablissement"],
        "dtype_hints": ["object"],
        "required": False,
    },
    "drug_code": {
        "label": "Drug / Medicine Code",
        "group": "Drug",
        "patterns": [r"drug.?code", r"medicine.?code", r"med.?code", r"item.?code",
                     r"product.?code", r"rhia.?code", r"atc.?code", r"ndc"],
        "dtype_hints": ["object", "string"],
        "required": False,
    },
    "drug_name": {
        "label": "Drug / Medicine Name",
        "group": "Drug",
        "patterns": [r"drug.?name", r"medicine.?name", r"medication", r"item.?name",
                     r"product.?name", r"denomination", r"generic.?name",
                     r"nom.?medicament"],
        "dtype_hints": ["object"],
        "required": False,
    },
    "quantity": {
        "label": "Quantity Dispensed",
        "group": "Drug",
        "patterns": [r"quantity", r"qty", r"quantite", r"qte", r"units?$",
                     r"nombre.?unite", r"dose.?qty"],
        "dtype_hints": ["int", "float", "int64", "float64"],
        "required": False,
    },
    "diagnosis": {
        "label": "Diagnosis / ICD Code",
        "group": "Clinical",
        "patterns": [r"diagnosis", r"diagnos", r"icd", r"condition",
                     r"disease.?code", r"code.?patho", r"pathology"],
        "dtype_hints": ["object"],
        "required": False,
    },
    "amount": {
        "label": "Total Amount (RWF)",
        "group": "Financial",
        "patterns": [r"total.?cost", r"total.?amount", r"montant.?total",
                     r"cout.?total", r"amount$", r"total$"],
        "dtype_hints": ["float64", "int64"],
        "required": False,
    },
    "insurance_copay": {
        "label": "Insurance Co-payment",
        "group": "Financial",
        "patterns": [r"insurance.?co.?pay", r"couverture", r"part.?assur",
                     r"rssb.?amount", r"rama.?amount", r"insurance.?share",
                     r"rama.?part"],
        "dtype_hints": ["float64"],
        "required": False,
    },
    "patient_copay": {
        "label": "Patient Co-payment",
        "group": "Financial",
        "patterns": [r"patient.?co.?pay", r"ticket.?moderateur",
                     r"patient.?share", r"part.?patient", r"copay"],
        "dtype_hints": ["float64"],
        "required": False,
    },
    "medicine_cost": {
        "label": "Medicine Cost",
        "group": "Financial",
        "patterns": [r"medicine.?cost", r"drug.?cost", r"med.?cost",
                     r"cout.?medicament"],
        "dtype_hints": ["float64"],
        "required": False,
    },
    "gender": {
        "label": "Gender",
        "group": "Patient",
        "patterns": [r"gender", r"sex$", r"sexe$"],
        "dtype_hints": ["object"],
        "required": False,
    },
    "patient_type": {
        "label": "Patient Type",
        "group": "Patient",
        "patterns": [r"patient.?type", r"type.?patient", r"beneficiary.?type",
                     r"categorie"],
        "dtype_hints": ["object"],
        "required": False,
    },
}

_GROUPS_ORDER = ["Patient", "Visit", "Provider", "Drug", "Clinical", "Financial"]
_GROUP_COLORS = {
    "Patient":   "#0ea5e9",
    "Visit":     "#00e5a0",
    "Provider":  "#a78bfa",
    "Drug":      "#f59e0b",
    "Clinical":  "#f97316",
    "Financial": "#22c55e",
}


def profile_column(df: pd.DataFrame, col: str) -> dict:
    """Compute rich stats for a column to help with mapping."""
    s = df[col]
    total = len(s)
    nulls = int(s.isna().sum())
    non_null = s.dropna()
    dtype_str = str(s.dtype)

    info = {
        "col":       col,
        "dtype":     dtype_str,
        "total":     total,
        "nulls":     nulls,
        "null_pct":  round(100 * nulls / max(total, 1), 1),
        "unique":    int(non_null.nunique()),
        "samples":   [],
        "is_numeric": pd.api.types.is_numeric_dtype(s),
        "is_date":   False,
        "looks_like_id": False,
        "looks_like_date": False,
        "looks_like_amount": False,
        "looks_like_drug_code": False,
    }

    # Sample values
    info["samples"] = [str(v) for v in non_null.head(5).tolist()]

    # Detect date
    if "datetime" in dtype_str:
        info["is_date"] = True
        info["looks_like_date"] = True
    elif dtype_str == "object" and len(non_null) > 0:
        try:
            test = pd.to_datetime(non_null.head(20), errors="coerce")
            if test.notna().mean() > 0.7:
                info["looks_like_date"] = True
        except Exception:
            pass

    # Looks like amount
    if info["is_numeric"] and len(non_null) > 0:
        med = float(non_null.median())
        if 100 < med < 10_000_000:
            info["looks_like_amount"] = True

    # Looks like ID
    if not info["is_numeric"] and len(non_null) > 0:
        sample_str = non_null.head(20).astype(str)
        alpha_ratio = sample_str.str.match(r"^[A-Za-z0-9\-/]+$").mean()
        avg_len = sample_str.str.len().mean()
        if alpha_ratio > 0.8 and 4 <= avg_len <= 20:
            info["looks_like_id"] = True

    # Looks like drug code (ATC pattern)
    if dtype_str == "object" and len(non_null) > 0:
        sample_str = non_null.head(20).astype(str)
        atc_match = sample_str.str.match(r"^[A-Z][0-9]{2}[A-Z]{2}").mean()
        if atc_match > 0.5:
            info["looks_like_drug_code"] = True

    return info


def score_column_vs_field(col_key: str, profile: dict,
                           field_name: str, field_def: dict) -> float:
    """Return 0-1 confidence that col maps to field."""
    score = 0.0

    # Pattern matching (strongest signal)
    for pat in field_def["patterns"]:
        if re.search(pat, col_key, re.IGNORECASE):
            score += 0.7
            break

    # Dtype hint
    for dh in field_def.get("dtype_hints", []):
        if dh in profile["dtype"] or profile["dtype"].startswith(dh):
            score += 0.15
            break

    # Semantic hints
    if field_name == "visit_date" and profile["looks_like_date"]:
        score += 0.2
    if field_name in ("amount", "insurance_copay", "patient_copay", "medicine_cost"):
        if profile["looks_like_amount"]:
            score += 0.15
    if field_name == "patient_id" and profile["looks_like_id"]:
        score += 0.1
    if field_name == "drug_code" and profile["looks_like_drug_code"]:
        score += 0.2

    return min(score, 1.0)


def auto_map_columns(df: pd.DataFrame) -> dict:
    """
    Auto-detect which df column maps to which system field.
    Returns {system_field: original_col_name} for confident matches,
    and a full scores dict {original_col: {field: score}}.
    """
    profiles = {}
    for col in df.columns:
        key = re.sub(r"[^a-z0-9]", "_", col.lower().strip())
        key = re.sub(r"_+", "_", key).strip("_")
        profiles[col] = profile_column(df, col)
        profiles[col]["col_key"] = key

    # Score all columns against all fields
    all_scores = {}   # col -> {field -> score}
    for col, prof in profiles.items():
        all_scores[col] = {}
        for field, fdef in _SYSTEM_FIELDS.items():
            all_scores[col][field] = score_column_vs_field(
                prof["col_key"], prof, field, fdef
            )

    # Greedy assignment: highest-score match wins, no field used twice
    mapping = {}           # system_field -> original_col
    reverse = {}           # original_col -> system_field
    assigned_fields = set()

    # Flatten to (score, col, field) sorted desc
    pairs = sorted(
        [(s, col, field)
         for col, scores in all_scores.items()
         for field, s in scores.items()
         if s >= 0.35],
        key=lambda x: -x[0]
    )

    for score, col, field in pairs:
        if field not in assigned_fields and col not in reverse:
            mapping[field] = col
            reverse[col] = field
            assigned_fields.add(field)

    return mapping, all_scores, profiles


def apply_column_mapping(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """
    Rename df columns according to mapping {system_field: original_col}.
    Unknown columns get a raw_ prefix.
    Returns new df with system field names.
    """
    df = df.copy()
    rename = {}
    for field, orig_col in mapping.items():
        if orig_col in df.columns:
            rename[orig_col] = field

    # Rename known columns
    df = df.rename(columns=rename)

    # Prefix unknown remaining columns with raw_
    final_rename = {}
    for col in df.columns:
        if col not in _SYSTEM_FIELDS and not col.startswith("raw_"):
            final_rename[col] = f"raw_{col}"
    if final_rename:
        df = df.rename(columns=final_rename)

    return df


# ══════════════════════════════════════════════════════════════════════════════
# RULES ENGINE  (in-memory, no database required)
# ══════════════════════════════════════════════════════════════════════════════

# Diagnosis-Drug Blacklist (ICD prefix -> set of ATC prefixes to flag)
