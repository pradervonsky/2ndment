"""Jev (TypeSafe API): ekstraksi indikator dari dokumen, dan verifikasi narasi LLM."""
from .config import JEV_Q, MOCK, MOCK_ANSWERS, VERIFY


def make_client():
    """Klien TypeSafe + pertanyaan Jev yang sudah dibangun (dipakai ulang antar penilai)."""
    from typesafe_sdk import TypeSafeClient
    return TypeSafeClient(), build_questions()


def build_questions():
    from typesafe_sdk import Choice, Noul, Score
    builders = {
        "noul": lambda q: Noul(instructions=q["instructions"]),
        "score": lambda q: Score(instructions=q["instructions"], criteria=q["criteria"]),
        "choice": lambda q: Choice(instructions=q["instructions"], criteria=q["criteria"]),
    }
    return {k: builders[q["type"]](q) for k, q in JEV_Q["questions"].items()}


def ask(client, questions, appraiser, mock=MOCK):
    """Kembalikan ({indikator: {'value': ..., 'conf': ...}}, state yang dikirim ke Jev)."""
    state = JEV_Q["state_template"].format(**appraiser)
    if mock:
        return MOCK_ANSWERS[appraiser["id"]], state
    resp = client.system_one(state=state, questions=questions)
    raw = {}
    for key, q in JEV_Q["questions"].items():
        ans = resp.answers[key]
        value = {"noul": getattr(ans, "noul", None),
                 "score": getattr(ans, "score", None),
                 "choice": getattr(ans, "choice", None)}[q["type"]]
        raw[key] = {"value": value, "conf": getattr(ans, "confidence", None)}
    return raw, state


def verify(client, fields, narrative, mock=MOCK):
    """(True = lolos / False = gagal / None = dilewati, {cek: noul}, state yang dikirim ke Jev).
    fields = isian prompt narasi, jadi Jev memeriksa terhadap informasi yang sama dengan LLM."""
    state = VERIFY["state_template"].format(**fields, narrative=narrative)
    if mock or not VERIFY["enabled"]:
        return None, {}, state
    if not narrative.strip():  # mis. model kehabisan token saat berpikir -> langsung pakai fallback
        return False, {}, state
    from typesafe_sdk import Noul
    checks = VERIFY["checks"]
    resp = client.system_one(
        state=state,
        questions={k: Noul(instructions=c["instructions"]) for k, c in checks.items()},
    )
    scores = {k: resp.answers[k].noul for k in checks}
    return all(scores[k] <= c["max_noul"] for k, c in checks.items()), scores, state
