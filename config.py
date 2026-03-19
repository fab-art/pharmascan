"""
config.py — PharmaScan shared constants, colours, CSS, and column map.
Imported by every other module.
"""
import re
import warnings
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import streamlit as st

warnings.filterwarnings("ignore")

# ── Colours ───────────────────────────────────────────────────────────────────
ACCENT  = "#00e5a0"
ACCENT2 = "#0ea5e9"
PURPLE  = "#a78bfa"
WARN    = "#f59e0b"
DANGER  = "#ef4444"
MUTED   = "#64748b"
TEXT    = "#e2e8f0"
DARK    = "#0d1117"
BG      = DARK
CARD    = "#111720"
BORDER  = "#1e2a38"

plt.rcParams.update({
    "figure.facecolor": CARD,  "axes.facecolor":  DARK,
    "axes.edgecolor":   BORDER,"axes.labelcolor": MUTED,
    "axes.titlecolor":  TEXT,  "xtick.color":     MUTED,
    "ytick.color":      MUTED, "text.color":      TEXT,
    "grid.color":       BORDER,"grid.linewidth":  0.5,
    "font.family":      "monospace", "font.size": 9,
})

# ── CSS (injected once in app.py) ─────────────────────────────────────────────
APP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Mono&display=swap');
.stApp { background: #080c10; }
section[data-testid="stSidebar"] { background: #0d1117!important; border-right:1px solid #1e2a38; }
[data-testid="stMetric"] {
    background:#111720; border:1px solid #1e2a38;
    border-radius:12px; padding:16px 20px!important;
}
[data-testid="stMetricLabel"] { color:#64748b!important; font-size:11px!important; text-transform:uppercase; letter-spacing:.5px; }
[data-testid="stMetricValue"] { color:#e2e8f0!important; font-size:26px!important; font-weight:800!important; font-family:'Syne',sans-serif!important; }
.stTabs [data-baseweb="tab-list"] { background:#0d1117; border-bottom:1px solid #1e2a38; gap:4px; }
.stTabs [data-baseweb="tab"] { background:transparent; color:#64748b; font-weight:600; border-radius:0; border-bottom:2px solid transparent; padding:10px 18px; }
.stTabs [aria-selected="true"] { color:#00e5a0!important; border-bottom:2px solid #00e5a0!important; background:transparent!important; }
h1,h2,h3 { font-family:'Syne',sans-serif!important; }
.sidebar-title { font-family:'Syne',sans-serif; font-size:22px; font-weight:800; color:#e2e8f0; margin-bottom:4px; }
.sidebar-sub   { font-size:12px; color:#64748b; margin-bottom:20px; }
.chip-row { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }
.chip {
    background:rgba(14,165,233,.08); border:1px solid rgba(14,165,233,.2);
    border-radius:6px; padding:3px 10px; font-size:11px;
    font-family:'DM Mono',monospace; color:#0ea5e9;
}
.info-banner {
    background:rgba(14,165,233,.06); border:1px solid rgba(14,165,233,.2);
    border-radius:10px; padding:14px 18px; margin-bottom:16px;
}
.info-banner b { color:#0ea5e9; }
.sec-head {
    font-family:'Syne',sans-serif; font-size:15px; font-weight:700;
    color:#e2e8f0; padding-left:10px; border-left:3px solid #00e5a0;
    margin:20px 0 12px;
}
.rapid-card {
    background:#111720; border:1px solid #1e2a38;
    border-left:3px solid #f59e0b; border-radius:10px; padding:12px 14px;
}
.rapid-card.crit { border-left-color:#ef4444; }
.rc-head { display:flex; justify-content:space-between; align-items:flex-start; }
.rc-name { font-size:13px; font-weight:600; color:#e2e8f0; }
.rc-id   { font-size:11px; color:#64748b; font-family:'DM Mono',monospace; margin-top:2px; }
.rc-days { font-size:24px; font-weight:800; font-family:'Syne',sans-serif; color:#f59e0b; line-height:1; }
.rapid-card.crit .rc-days { color:#ef4444; }
.rc-days small { font-size:11px; font-weight:400; }
.rc-meta { font-size:11px; color:#64748b; font-family:'DM Mono',monospace; margin-top:5px; }
</style>
"""

# ── Column normalisation map ───────────────────────────────────────────────────
COLUMN_MAP = {
    r"#":                                               "row_number",
    r"paper.?code":                                     "voucher_id",
    r"dispensing.?date":                                "visit_date",
    r"patient.?name":                                   "patient_name",
    r"patient.?type":                                   "patient_type",
    r"gender":                                          "gender",
    r"is.?newborn":                                     "is_newborn",
    r"rama.?number":                                    "patient_id",
    r"practitioner.?name":                              "doctor_name",
    r"practitioner.?type":                              "doctor_type",
    r"total.?cost":                                     "amount",
    r"patient.?co.?payment":                            "patient_copay",
    r"insurance.?co.?payment":                          "insurance_copay",
    r"medicine.?cost":                                  "medicine_cost",
    r"patient.?(id|no|num|number|code)?":               "patient_id",
    r"pat.?id|pid":                                     "patient_id",
    r"doctor.?(id|no|num|code)?":                       "doctor_id",
    r"(doctor|dr|physician|prescriber).?name":          "doctor_name",
    r"doc.?id|did":                                     "doctor_id",
    r"prescriber":                                      "doctor_name",
    r"(visit|service|rx|voucher).?date":                "visit_date",
    r"date.?(of.?)?(visit|service|dispensing)?":        "visit_date",
    r"date":                                            "visit_date",
    r"(pharmacy|facility|clinic|hospital|branch).?(name|id|code)?": "facility",
    r"(drug|medicine|medication|item|product).?(name|description|desc)?": "drug_name",
    r"(drug|medicine|medication|item|product).?(code|id)?":              "drug_code",
    r"(amount|cost|price|value|total|charge)":          "amount",
    r"quantity|qty":                                    "quantity",
    r"(diagnosis|diag|icd|condition)":                  "diagnosis",
    r"(voucher|claim|ref|reference).?(no|number|id|code)?": "voucher_id",
}
