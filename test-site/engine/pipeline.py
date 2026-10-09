"""
Urutan langkah untuk satu penilai. Menambah langkah baru = satu modul + satu baris di sini.

  1. jev.ask        dokumen -> jawaban terketik
  2. scoring.score  jawaban + data terstruktur -> skor, tingkat, kontribusi, reviu
  3. llm.narrate    skor + pendorong utama -> narasi
  4. jev.verify     narasi diperiksa; gagal -> template fallback
"""
import time

from . import jev, llm, scoring
from .config import LABELS, MOCK, SETTINGS

STATUS_TEXT = {True: "Ya", False: "Tidak (pakai template)", None: "Dilewati"}


def run_appraiser(appraiser, client=None, questions=None, mock=MOCK):
    """Jalankan seluruh pipeline untuk satu penilai; kembalikan jejak tiap tahap (dipakai UI)."""
    t0 = time.perf_counter()
    raw, jev_state = jev.ask(client, questions, appraiser, mock)
    t1 = time.perf_counter()
    s = scoring.score(appraiser, raw)
    top = sorted(s["contrib"].items(), key=lambda x: -x[1])[: SETTINGS["narration"]["top_drivers"]]
    nar = llm.narrate(appraiser, s["total"], s["tier"], top, s["review"], mock)
    t2 = time.perf_counter()
    ok, checks, verify_state = jev.verify(client, nar["fields"], nar["output"], mock)
    t3 = time.perf_counter()
    return {
        "appraiser": appraiser, "jev_state": jev_state, "raw": raw,
        "contrib": s["contrib"], "total": s["total"], "tier": s["tier"], "top": top, "review": s["review"],
        "narration": nar, "verified": ok, "checks": checks, "verify_state": verify_state,
        "narrative": nar["fallback"] if ok is False else nar["output"],
        "seconds": {"jev": t1 - t0, "llm": t2 - t1, "verify": t3 - t2},
    }


def to_row(trace):
    """Satu baris tabel/CSV hasil akhir."""
    return {
        "ID": trace["appraiser"]["id"], "Skor": round(trace["total"], 1), "Tingkat": trace["tier"],
        "Pendorong utama": "; ".join(LABELS[k] for k, _ in trace["top"]),
        "Reviu manual": ", ".join(trace["review"]) or "-",
        "Verifikasi narasi": STATUS_TEXT[trace["verified"]],
        "Narasi": trace["narrative"],
    }
