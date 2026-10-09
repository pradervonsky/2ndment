"""
Scoring: jawaban Jev + data terstruktur -> skor, tingkat, kontribusi, flag reviu.

Ini bagian yang paling mungkin diganti (mis. bobot hasil statistik, regresi logistik).
Kontrak yang dipakai pipeline dan UI — fungsi scoring baru cukup mengembalikan dict yang sama:

    score(appraiser, answers) -> {
        "total":   float 0–100,
        "tier":    nama tingkat dari settings.yaml,
        "contrib": {indikator: poin},   # dipakai chart Skor dan narasi
        "review":  [indikator yang perlu reviu manual],
    }

Metode dipilih lewat `scoring.method` di config/settings.yaml (daftar di METHODS di bawah).
"""
import math

from .config import JEV_Q, SETTINGS, STRUCT


# ---------------------------------------------------------------- Pemetaan jawaban -> risiko 0..1
def struct_risk(ind, value):
    """Indikator terstruktur: risk = min(|value| / cap, 1)."""
    return min(abs(value) / ind["cap"], 1)


def to_risk(q, value):
    """Petakan jawaban Jev ke risiko 0..1 sesuai aturan di jev_questions.yaml."""
    if q["type"] == "noul":
        return value if q["risk_if_true"] else 1 - value
    if q["type"] == "score":
        levels = q["level_risk"]
        lo = min(int(math.floor(value)), len(levels) - 1)
        hi = min(lo + 1, len(levels) - 1)
        return levels[lo] + (levels[hi] - levels[lo]) * (value - lo)
    return q["option_risk"][value]


def needs_review(q, ans):
    """Score/Choice: confidence < min_confidence. Noul: nilai di noul_uncertain_band (dekat 0,5)."""
    rv = SETTINGS["review"]
    if q["type"] == "noul":
        lo, hi = rv["noul_uncertain_band"]
        return lo < ans["value"] < hi
    conf = ans.get("conf")
    return conf is not None and conf < rv["min_confidence"]


def tier_for(total):
    tiers = sorted(SETTINGS["tiers"], key=lambda t: -t["min_score"])
    return next(t["name"] for t in tiers if total >= t["min_score"])


# ---------------------------------------------------------------- Metode scoring
def weighted_scorecard(appraiser, answers):
    """Scorecard berbobot: kontribusi = weight × risk; total = jumlah kontribusi."""
    contrib, review = {}, []
    for key, ind in STRUCT.items():
        contrib[key] = ind["weight"] * struct_risk(ind, appraiser["structured"][ind["field"]])
    for key, q in JEV_Q["questions"].items():
        contrib[key] = q["weight"] * to_risk(q, answers[key]["value"])
        if needs_review(q, answers[key]):
            review.append(key)
    total = sum(contrib.values())
    return {"total": total, "tier": tier_for(total), "contrib": contrib, "review": review}


METHODS = {"weighted": weighted_scorecard}


def score(appraiser, answers):
    method = SETTINGS.get("scoring", {}).get("method", "weighted")
    return METHODS[method](appraiser, answers)
