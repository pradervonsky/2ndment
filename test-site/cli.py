"""
PoC Risk Engine Penilai Publik — jalankan semua penilai tanpa UI, simpan CSV.
SELURUH DATA SINTETIS. Jangan kirim data pengawasan asli ke API eksternal.

  cd ~/2ndment
  uv run test-site/cli.py           # mode sesuai config/settings.yaml
  MOCK=1 uv run test-site/cli.py    # paksa demo offline
"""
import pandas as pd

from engine import jev
from engine.config import APPRAISERS, BASE, MOCK, SETTINGS, check_weights
from engine.pipeline import run_appraiser, to_row


def main():
    check_weights()
    client, questions = (None, None) if MOCK else jev.make_client()

    rows = [to_row(run_appraiser(a, client, questions)) for a in APPRAISERS]
    df = pd.DataFrame(rows).sort_values("Skor", ascending=False)
    pd.set_option("display.max_colwidth", 120)
    print(df.to_string(index=False))

    out = BASE / SETTINGS["output"]["csv_path"]
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\nHasil disimpan di {out}")


if __name__ == "__main__":
    main()
