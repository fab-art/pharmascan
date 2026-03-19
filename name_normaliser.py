"""
name_normaliser.py — Fuzzy name clustering and normalisation.
Uses Union-Find with first-3-char blocking for O(n log n) performance.
"""
import re
import difflib
import pandas as pd
from collections import defaultdict as _dd
from utils import CLUSTER_MAX_NAMES, LOG


# ── Name normalisation engine ─────────────────────────────────────────────────

def _toks(name: str) -> set:
    """Lowercase alpha-numeric tokens from a name string."""
    return set(re.sub(r"[^a-z0-9 ]", "", name.lower()).split())

def _seq_ratio(a: str, b: str) -> float:
    sa = " ".join(sorted(_toks(a)))
    sb = " ".join(sorted(_toks(b)))
    return difflib.SequenceMatcher(None, sa, sb).ratio()

def _tok_fuzzy_subset(a: str, b: str, thresh: float = 0.76) -> bool:
    """
    True if every token in the SHORTER name has a fuzzy-close counterpart
    in the LONGER name (catches 'Aurbain'/'Urbain', 'Constatin'/'Constantin').
    """
    ta = list(_toks(a))
    tb = list(_toks(b))
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    for tok in shorter:
        best = max((difflib.SequenceMatcher(None, tok, lt).ratio() for lt in longer), default=0)
        if best < thresh:
            return False
    return True

def _match_score(a: str, b: str):
    """
    Returns (score 0–1, reason str).
    reason ∈ {'subset', 'typo', 'none'}
    """
    ta, tb = _toks(a), _toks(b)
    if not ta or not tb:
        return 0.0, "none"

    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)

    # Rule 1 — exact token subset ('ZACHEE' ⊂ 'Niyonsenga Zachee')
    if shorter <= longer:
        boost = min(0.12, len(shorter) * 0.04)
        return 0.88 + boost, "subset"

    # Rule 2 — fuzzy-token subset: every short token ≈ some long token
    if _tok_fuzzy_subset(a, b):
        return 0.85, "typo"

    # Rule 3 — high overall char-sequence similarity
    ratio = _seq_ratio(a, b)
    if ratio >= 0.88:
        return ratio, "typo"

    return 0.0, "none"


def detect_name_clusters(names: list, counts: dict) -> list[dict]:
    """
    Cluster similar names using Union-Find with blocking:
    1. Block by first 3 chars (reduces O(n²) to O(b²) where b << n)
    2. Full fuzzy match only within blocks
    Scales to ~10k unique names without performance issues.
    """
    if len(names) > CLUSTER_MAX_NAMES:
        # Sub-sample by frequency for very large name lists
        names = sorted(names, key=lambda n: -counts.get(n, 0))[:CLUSTER_MAX_NAMES]
        LOG.warning("Name cluster: capped at %d names", CLUSTER_MAX_NAMES)

    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        pa, pb = find(a), find(b)
        if pa != pb:
            if len(_toks(pa)) >= len(_toks(pb)):
                parent[pb] = pa
            else:
                parent[pa] = pb

    # ── Blocking: group by first 3 lowercase alphanum chars ──────────────
    from collections import defaultdict as _dd2
    blocks: dict = _dd2(list)
    for n in names:
        clean = re.sub(r"[^a-z]", "", n.lower())
        key = clean[:3] if len(clean) >= 3 else clean
        blocks[key].add(n) if hasattr(blocks[key], "add") else blocks[key].append(n)

    # Also index by each token's first 3 chars for cross-block matching
    tok_blocks: dict = _dd2(list)
    for n in names:
        for tok in _toks(n):
            tok_blocks[tok[:3]].append(n)

    compared = set()
    for block_members in list(blocks.values()) + list(tok_blocks.values()):
        for i, a in enumerate(block_members):
            for b in block_members[i + 1:]:
                pair = (min(a, b), max(a, b))
                if pair in compared:
                    continue
                compared.add(pair)
                sc, why = _match_score(a, b)
                if sc > 0 and why != "none":
                    union(a, b)

    # ── Build clusters ────────────────────────────────────────────────────
    from collections import defaultdict as _dd3
    final: dict = _dd3(list)
    for n in names:
        final[find(n)].append(n)

    def best_canonical(members):
        def score(n):
            return (len(_toks(n)), not re.match(r"^(Dr|DR)\s", n),
                    n == n.title(), counts.get(n, 0), len(n))
        return max(members, key=score)

    results = []
    for root, members in final.items():
        if len(members) < 2:
            continue
        canon = best_canonical(members)
        variants = [m for m in members if m != canon]
        scores = [_match_score(canon, v)[0] for v in variants]
        conf = round(sum(scores) / len(scores), 3) if scores else 1.0
        ct = _toks(canon)
        suspicious = any(not (_toks(v) & ct) for v in variants)
        results.append({
            "canonical":  canon,
            "variants":   sorted(variants, key=lambda x: (-counts.get(x, 0), -len(x))),
            "confidence": conf,
            "suspicious": suspicious,
            "count":      len(members),
        })
    results.sort(key=lambda x: (-x["count"], -x["confidence"]))
    return results




def apply_name_normalisation(df: pd.DataFrame, col: str,
                              approved_clusters: list[dict]) -> pd.DataFrame:
    """Apply approved rename clusters to a column in a copy of df."""
    df = df.copy()
    mapping = {}
    for c in approved_clusters:
        for v in c["variants"]:
            mapping[v] = c["canonical"]
    df[col] = df[col].map(lambda x: mapping.get(x, x))
    return df



# ══════════════════════════════════════════════════════════════════════════════
