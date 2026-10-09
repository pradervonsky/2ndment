"""
Memuat semua file konfigurasi, prompt, dan data (sekali, saat diimpor).
Semua parameter ada di config/, prompt di prompts/, data di data/.
SELURUH DATA SINTETIS. Jangan kirim data pengawasan asli ke API eksternal.
"""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent  # test-site/
load_dotenv(BASE.parent / ".env")  # TYPESAFE_API_KEY di ~/2ndment/.env


def load_yaml(rel):
    with open(BASE / rel, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_text(rel):
    return (BASE / rel).read_text(encoding="utf-8").strip()


SETTINGS = load_yaml("config/settings.yaml")
JEV_Q = load_yaml("config/jev_questions.yaml")
STRUCT = load_yaml("config/structured_indicators.yaml")["indicators"]
VERIFY = load_yaml("config/verification.yaml")
APPRAISERS = load_yaml("data/appraisers.yaml")["appraisers"]
MOCK_ANSWERS = load_yaml("data/mock_answers.yaml")
NARRATION_TMPL = load_text("prompts/narration.txt")
FALLBACK_TMPL = load_text("prompts/narration_fallback.txt")
CAPTION_PROMPT = load_text("prompts/photo_caption.txt")

MOCK = os.getenv("MOCK") == "1" or SETTINGS["mode"]["mock"]
LABELS = {**{k: v["label"] for k, v in STRUCT.items()},
          **{k: v["label"] for k, v in JEV_Q["questions"].items()}}
WEIGHTS = {**{k: v["weight"] for k, v in STRUCT.items()},
           **{k: v["weight"] for k, v in JEV_Q["questions"].items()}}


def check_weights():
    total = sum(WEIGHTS.values())
    if abs(total - 100) > 1e-6:
        print(f"[PERINGATAN] Total bobot = {total}, bukan 100. Batas tier mungkin perlu disesuaikan.\n")
