"""LLM lokal via Ollama: narasi skor risiko, dan deskripsi foto objek."""
import base64
import io

import requests

from .config import CAPTION_PROMPT, FALLBACK_TMPL, LABELS, MOCK, NARRATION_TMPL, SETTINGS


def chat(model, content, options, images=None, think=False):
    """Satu panggilan /api/chat Ollama; kembalikan message (content, thinking)."""
    msg = {"role": "user", "content": content}
    if images:
        msg["images"] = images
    llm = SETTINGS["llm"]
    r = requests.post(llm["url"], timeout=llm["timeout_seconds"], json={
        "model": model, "stream": False, "think": think, "options": options, "messages": [msg]})
    r.raise_for_status()
    return r.json()["message"]


def narrate(appraiser, total, tier, top, review, mock=MOCK):
    """Kembalikan dict: prompt, output (dan thinking) LLM, evidence, fields, fallback."""
    evidence = "\n".join(f"- {LABELS[k]} (kontribusi {c:.1f} poin)" for k, c in top)
    fields = {
        "id": appraiser["id"], "score": total, "tier": tier, "evidence": evidence,
        "drivers": "; ".join(LABELS[k] for k, _ in top),
        "review": ", ".join(LABELS[k] for k in review) or "tidak ada",
    }
    out = {"prompt": NARRATION_TMPL.format(**fields), "evidence": evidence, "fields": fields,
           "fallback": FALLBACK_TMPL.format(**fields), "output": None, "thinking": None}
    if mock:
        out["output"] = out["fallback"]
        return out

    llm = SETTINGS["llm"]
    msg = chat(llm["model"], out["prompt"], {"temperature": llm["temperature"]},
               think=llm.get("think", False))
    out["output"], out["thinking"] = msg["content"].strip(), msg.get("thinking")
    return out


def caption_photo(image_bytes):
    """Kembalikan deskripsi kondisi fisik dari foto objek (Bahasa Indonesia)."""
    from PIL import Image

    vis = SETTINGS["vision"]
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((vis["max_side_px"], vis["max_side_px"]))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)

    # num_ctx besar: sebagian model tetap "berpikir" walau think=False, agar jawaban tidak terpotong
    msg = chat(vis["model"], CAPTION_PROMPT,
               {"temperature": vis["temperature"], "num_ctx": vis["num_ctx"]},
               images=[base64.b64encode(buf.getvalue()).decode()])
    caption = " ".join(msg["content"].split())
    if not caption:
        raise RuntimeError("Model tidak menghasilkan deskripsi (kehabisan token saat berpikir). Coba lagi.")
    return caption
