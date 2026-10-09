"""
Demo Streamlit — PoC Risk Engine Penilai Publik (Jev + Qwen3.5)

A risk-based profiling system for Penilai Publik exists to catch appraisers
who systematically produce unreliable valuations before that unreliability
compounds into bank losses or market mispricing

  cd ~/2ndment
  uv run streamlit run test-site/app.py

Theme in ~/2ndment/.streamlit/config.toml.
"""
import os
import time
from pathlib import Path

import altair as alt
import pandas as pd
import requests
import streamlit as st

from engine import config as cfg, jev, llm, pipeline, scoring

# Palet tema: hanya lima warna ini yang dipakai
DARK, LIGHT = "#1a535c", "#f7fff7"
TIER_COLOR = {"Rendah": "#4ecdc4", "Sedang": "#ffe66d", "Tinggi": "#ff6b6b"}

st.set_page_config(page_title="Risk Engine Penilai Publik", page_icon=":material/balance:", layout="wide")

# CSS tambahan (ukuran kode, tabel Jev, kotak foto, hover, jarak atas) ada di style.css
st.html(f"<style>{(Path(__file__).parent / 'style.css').read_text(encoding='utf-8')}</style>")

# ---------------------------------------------------------------- Helpers
def ollama_ok():
    try:
        base = cfg.SETTINGS["llm"]["url"].split("/api/")[0]
        return requests.get(base, timeout=2).ok
    except requests.RequestException:
        return False

@st.cache_resource
def jev_client():
    return jev.make_client()


@st.cache_data(show_spinner=False)
def run(appraiser, mock):
    """Di-cache per isi input agar klik ulang tidak memanggil API/LLM lagi."""
    client, questions = (None, None) if mock else jev_client()
    return pipeline.run_appraiser(appraiser, client, questions, mock)


@st.cache_data(show_spinner=False)
def caption(image_bytes):
    """(deskripsi, detik). Waktu diukur di dalam cache, jadi tetap waktu proses model aslinya."""
    t0 = time.perf_counter()
    return llm.caption_photo(image_bytes), time.perf_counter() - t0


def synthetic(appraiser_id):
    return next(x for x in cfg.APPRAISERS if x["id"] == appraiser_id)


def struct_key(ind):
    return f"structured_{ind['field']}"


def fill_structured(a):
    # nilai di atas cap dipotong ke cap; risikonya sama karena risk = min(|value| / cap, 1)
    for ind in cfg.STRUCT.values():
        v = min(a["structured"][ind["field"]], ind["cap"])
        st.session_state[struct_key(ind)] = v              # slider (sumber nilai)
        st.session_state[struct_key(ind) + "_num"] = v     # kotak angka di sebelahnya


def sync_struct(key, from_num):
    """Slider dan kotak angka saling mengikuti."""
    if from_num:
        st.session_state[key] = st.session_state[key + "_num"]
    else:
        st.session_state[key + "_num"] = st.session_state[key]


def fill_synthetic():
    a = synthetic(st.session_state.appraiser_id)
    fill_structured(a)
    st.session_state.report = a["report"]
    st.session_state.photo_captions = a["photo_captions"]


def reset_inputs():
    fill_structured(synthetic(st.session_state.appraiser_id))
    for k in ("report", "photo_captions", "result"):
        st.session_state.pop(k, None)


def tier_ranges():
    """[(name, lo, hi)] urut naik, dari config/settings.yaml."""
    tiers = sorted(cfg.SETTINGS["tiers"], key=lambda x: x["min_score"])
    return [(x["name"], x["min_score"], tiers[i + 1]["min_score"] if i + 1 < len(tiers) else 100)
            for i, x in enumerate(tiers)]


def chip(tier, solid=True):
    c = TIER_COLOR.get(tier, LIGHT)
    style = (f"background:{c};color:{DARK};border:2px solid {c}" if solid
             else f"background:transparent;color:{LIGHT};border:2px solid {c}")
    return (f"<span style='{style};border-radius:999px;padding:2px 12px;"
            f"font-weight:600;white-space:nowrap'>{tier}</span>")


def status(ok, text):
    c = TIER_COLOR["Rendah"] if ok else TIER_COLOR["Tinggi"]
    state = "online" if ok else "offline"  # tetap ada untuk tooltip/pembaca layar, warna bukan satu-satunya tanda
    return f"<span style='color:{c}' title='{state}' aria-label='{state}'>●</span> {text}"


def returned_field(name, value, as_bar=True):
    """Satu baris di kolom `returns`: nama field · bar 0–1 (atau teks) · nilai."""
    if as_bar:
        mid = f"<div class='track'><div class='fill' style='width:{value * 100:.0f}%'></div></div>"
        val = f"{value:.2f}"
    else:
        mid, val = f"<span>{value}</span>", ""
    return f"<div class='ret'><code>{name}</code>{mid}<span>{val}</span></div>"


def returns_cell(q, ans):
    """Field yang dikembalikan Jev per tipe:
    noul -> noul; score -> score + confidence; choice -> choice + confidence."""
    if q["type"] == "noul":
        return returned_field("noul", ans["value"])
    if q["type"] == "score":
        top = len(q["criteria"]) - 1
        first = returned_field("score", f"{ans['value']:.1f} / {top:.1f}", as_bar=False)
    else:
        first = returned_field("choice", ans["value"], as_bar=False)
    return first + returned_field("confidence", ans["conf"])


def style_chart(chart):
    return chart.configure(background="transparent").configure_view(stroke=None).configure_axis(
        labelColor=LIGHT, titleColor=LIGHT, domainColor=LIGHT, tickColor=LIGHT,
        gridColor=LIGHT, gridOpacity=0.15, labelFontSize=12,
    ).configure_legend(labelColor=LIGHT, titleColor=LIGHT)


def score_band(total):
    """Skala 0–100: pita warna per tingkat (legenda) + penanda posisi skor."""
    segs = "".join(
        f"<div title='{n}: {lo}–{hi}' style='flex:{hi - lo};background:{TIER_COLOR.get(n, LIGHT)};"
        f"color:{DARK};font-weight:600;font-size:0.8rem;text-align:center;line-height:26px;"
        f"border-right:2px solid {DARK}'>{n} {lo}–{hi}</div>"
        for n, lo, hi in tier_ranges())
    pos = max(0.0, min(total, 100.0))
    return (f"<div style='position:relative;padding-top:22px'>"
            f"<div style='position:absolute;top:0;left:{pos}%;transform:translateX(-50%);"
            f"color:{LIGHT};font-weight:700;font-size:0.85rem'>▼ {total:.1f}</div>"
            f"<div style='display:flex;border-radius:4px;overflow:hidden'>{segs}</div>"
            f"<div style='position:absolute;top:20px;bottom:0;left:{pos}%;width:3px;"
            f"background:{LIGHT};transform:translateX(-50%)'></div></div>")

# ---------------------------------------------------------------- Sidebar
with st.sidebar:
    st.header("Pengaturan demo")
    ids = [a["id"] for a in cfg.APPRAISERS]
    appraiser_id = st.selectbox("ID Penilai", ids, key="appraiser_id",
                                on_change=reset_inputs)

    has_key = bool(os.getenv("TYPESAFE_API_KEY"))
    has_ollama = ollama_ok()
    live_ready = has_key and has_ollama
    mode = st.radio("Mode", ["Mockup", "Live (Jev API + Qwen3.5)"],
                    index=0 if cfg.MOCK or not live_ready else 1,
                    disabled=not live_ready,
                    help="Mock memakai isian sintesis (mock_answers.yaml)")
    mock = mode.startswith("Mock")

    st.markdown(status(has_key, "`TYPESAFE_API_KEY`"), unsafe_allow_html=True)
    for model in dict.fromkeys((cfg.SETTINGS["llm"]["model"], cfg.SETTINGS["vision"]["model"])):
        st.markdown(status(has_ollama, f"`{model}`"), unsafe_allow_html=True)
    if st.button("Hapus cache", width="stretch", help="Paksa Jev/Qwen dipanggil ulang."):
        run.clear()
        caption.clear()
        st.session_state.pop("result", None)

    st.divider()
    rv = cfg.SETTINGS["review"]
    st.caption("App ini menggunakan data sintesis.")

st.title("Risk Engine Penilai Publik")
st.caption("Jev ekstrak indikator dari laporan → weighted scorecard → Qwen3.5 generate narasi → "
           "Jev verifikasi narasi.  ")
header = st.container()  # diisi setelah pipeline jalan

tab_in, tab_jev, tab_score, tab_llm = st.tabs(["1 · Input", "2 · Jev", "3 · Skor", "4 · Narasi"])

# ---------------------------------------------------------------- 1. Input
with tab_in:
    base = synthetic(appraiser_id)
    if struct_key(next(iter(cfg.STRUCT.values()))) not in st.session_state:
        fill_structured(base)

    left, right = st.columns([1, 2], gap="large")
    with left:
        st.subheader("Data entry")
        st.caption(f"Dari data pengawasan {appraiser_id}.")
        structured = {}
        with st.container(key="structured_inputs"):  # CSS: tanpa tombol − / + (style.css)
            for ind in cfg.STRUCT.values():
                k = struct_key(ind)
                # label selebar kolom (tidak terlipat) + ikon (?) dengan detail field/cap/weight
                st.markdown(f"<p class='struct-label'>{ind['label']} (max {ind['cap']})</p>",
                            unsafe_allow_html=True,
                            help=f"`{ind['field']}` · `cap` = {ind['cap']} · `weight` = {ind['weight']}")
                slider_col, num_col = st.columns([4, 1], vertical_alignment="center")
                structured[ind["field"]] = slider_col.slider(
                    f"{ind['label']} (max {ind['cap']})", min_value=0, max_value=ind["cap"], step=1,
                    key=k, on_change=sync_struct, args=(k, False), label_visibility="collapsed")
                num_col.number_input(
                    f"{ind['label']} (angka)", min_value=0, max_value=ind["cap"], step=1,
                    key=k + "_num", on_change=sync_struct, args=(k, True), label_visibility="collapsed")
        st.button(f"Isi contoh data sintetis {appraiser_id}", on_click=fill_synthetic, width="stretch")

    with right:
        st.subheader("Laporan penilaian")
        st.text_area("Laporan", key="report", height=130, label_visibility="collapsed",
                     placeholder="Tempel atau ketik kutipan laporan penilaian di sini…")

        st.subheader("Foto objek")
        # foto ada -> 2 kolom: (unggah + deskripsi) | gambar; tanpa foto -> deskripsi selebar penuh
        has_photo = st.session_state.get("photo") is not None
        form_col, img_col = st.columns([2, 1], gap="medium") if has_photo else (st.container(), None)
        with form_col:
            st.markdown("<p style='font-size:0.875rem;margin-bottom:0'>Unggah foto aset</p>", unsafe_allow_html=True)
            # satu kotak: unggah foto + tombol deskripsi (gaya di .st-key-photo_box, CSS di atas)
            # foto ada -> satu baris: nama file | tombol Generate (gaya di .st-key-photo_box, CSS di atas)
            with st.container(border=True, key="photo_box", width="stretch",
                              horizontal=True, vertical_alignment="center", wrap=False):
                photo = st.file_uploader("Unggah foto aset", type=["jpg", "jpeg", "png", "webp"],
                                         key="photo", label_visibility="collapsed")
                if photo:
                    vision = cfg.SETTINGS["vision"]["model"]
                    # klik -> flag diset sebelum rerun, jadi tombol langsung tampil "processing…"
                    busy = st.session_state.get("captioning", False)
                    st.button("Processing…" if busy else "Generate", key="generate_btn",
                              disabled=busy or not has_ollama, width="stretch",
                              help=f"Buat deskripsi foto dengan {vision}",
                              on_click=lambda: st.session_state.update(captioning=True, caption_error=None))
                    if busy:
                        try:
                            st.session_state.photo_captions, secs = caption(photo.getvalue())
                            st.session_state.caption_time = (photo.file_id, secs)
                        except Exception as e:
                            st.session_state.caption_error = str(e)
                        st.session_state.captioning = False
                        st.rerun()  # gambar ulang: tombol kembali "Generate", deskripsi terisi
            if st.session_state.get("caption_error"):
                st.error(f"Gagal membuat deskripsi: {st.session_state.caption_error}")
            done = st.session_state.get("caption_time")
            cap_label = "Deskripsi foto objek"
            if photo and done and done[0] == photo.file_id:  # hanya untuk foto yang sedang tampil
                cap_label += f" :gray[| Qwen duration: {done[1]:.1f} detik]"
            st.text_area(cap_label, key="photo_captions", height=100,
                         placeholder="Unggah foto untuk generate deskripsi atau isi manual…",
                         help="Hasil dari model masuk ke sini dan dapat diedit sebelum dilakukan analisis.")
        if photo and img_col is not None:
            img_col.image(photo, width="stretch")

    report = st.session_state.get("report", "").strip()
    captions = st.session_state.get("photo_captions", "").strip()
    if mock and report and report != base["report"]:
        st.warning("Mode mock: jawaban Jev diambil dari data/mock_answers.yaml milik "
                   f"{appraiser_id}, jadi teks bebas ini tidak benar-benar dianalisis. Pakai mode Live.")
    if st.button("Jalankan analisis", disabled=not report, width="stretch"):
        appraiser = {**base, "structured": {**base["structured"], **structured},
                     "report": report, "photo_captions": captions or "(tidak ada foto)"}
        with st.spinner("Menjalankan pipeline…" if mock else "Processing… (±30–60 detik)"):
            try:
                st.session_state.result = run(appraiser, mock)
            except Exception as e:  # tampilkan error di halaman, bukan traceback mentah
                st.error(f"Pipeline gagal: {e}")
    if not report:
        st.caption("Isi laporan secara manual atau klik **Isi contoh data sintetis**, lalu jalankan analisis.")

t = st.session_state.get("result")
if t is None:
    for tab in (tab_jev, tab_score, tab_llm):
        tab.info("Jalankan analisis di tab 1 · Input.")
    st.stop()

a = t["appraiser"]
with header:
    c1, c2, c3, c4 = st.columns([1, 1, 3, 1])
    c1.metric("Penilai", a["id"])
    c2.metric("Skor risiko", f"{t['total']:.1f} / 100")
    with c3:
        st.markdown(f"<div style='font-size:0.875rem;margin-bottom:4px'>Tingkat: {chip(t['tier'])}</div>"
                    + score_band(t["total"]), unsafe_allow_html=True)
    c4.metric("Indikator perlu reviu", len(t["review"]))

    source = {True: "Qwen-generated, Jev-verified", False: "template, narasi qwen tidak lolos verifikasi oleh Jev",
              None: "template" if mock else "dari qwen, tanpa verifikasi"}[t["verified"]]
    st.info(t["narrative"])

# ---------------------------------------------------------------- 2. Jev
with tab_jev:
    st.subheader("`answers` from Jev")
    st.caption("`type`: **Noul** → `noul` yaitu probabilitas 0–1 apakah pernyataan benar "
               "(dekat 0,5 = ragu, perlu reviu manual) | "
               "**Score** → `score` + `confidence` | **Choice** → `choice` + "
               "`confidence`")
    body = "".join(
        f"<tr><td><code>{key}</code></td><td>{q['type']}</td><td class='wrap'>{q['instructions']}</td>"
        f"<td style='min-width:16rem'>{returns_cell(q, t['raw'][key])}</td>"
        f"<td>{scoring.to_risk(q, t['raw'][key]['value']):.2f}</td><td>{q['weight']:.1f}</td>"
        + ("<td class='flag'>ya</td></tr>" if key in t['review'] else "<td>tidak</td></tr>")
        for key, q in cfg.JEV_Q["questions"].items())
    st.html(f"<table class='jev-table'><thead><tr><th>question</th><th>type</th><th>instructions</th>"
            f"<th>returns</th><th>risk</th><th>weight</th><th>review</th></tr></thead>"
            f"<tbody>{body}</tbody></table>")
    st.caption("`risk`: 0 = aman, 1 = berisiko | `score` = indeks kriteria (0 = kriteria pertama)")
    st.caption(f"Reviu manual jika `confidence` < {rv['min_confidence']} (Score/Choice) "
               f"atau `noul` di antara {rv['noul_uncertain_band'][0]}–{rv['noul_uncertain_band'][1]}.")
    if not mock:
        st.caption(f"Jev duration: {t['seconds']['jev']:.1f} detik")

# ---------------------------------------------------------------- 3. Skor
with tab_score:
    st.subheader("Kontribusi tiap indikator ke skor total")
    st.caption("`contrib` = `weight` × `risk` (0–1). Skor total = jumlah `contrib`.")
    weights = {**{k: v["weight"] for k, v in cfg.STRUCT.items()},
               **{k: v["weight"] for k, v in cfg.JEV_Q["questions"].items()}}
    df = pd.DataFrame([{
        "indicator": k, "label": cfg.LABELS[k],
        "source": "structured_indicators" if k in cfg.STRUCT else "jev_questions",
        "contrib": round(c, 2), "weight": weights[k]} for k, c in t["contrib"].items()])
    df = df.sort_values("contrib", ascending=False)

    # nama kolom tanpa titik: Vega-Lite membaca "." sebagai field bersarang (-> NaN)
    for source, title in [("structured_indicators", "Data Entry"),
                          ("jev_questions", "Reports & Documentations")]:
        part = df[df["source"] == source]
        order = list(part["label"])  # sudah urut menurun menurut contrib; dipakai kedua layer
        st.markdown(f"**{title}** — {part['contrib'].sum():.1f} poin")
        # lebar area label dikunci agar sumbu x kedua chart mulai di posisi yang sama
        y = alt.Y("label:N", sort=order, title=None,
                  axis=alt.Axis(labelLimit=340, minExtent=340, maxExtent=340))
        # sumbu tepat 0–15 (nice=False: tanpa pembulatan ke 16); garis weight=15 tetap tampil di tepi
        x_scale = alt.Scale(domain=[0, max(weights.values())], nice=False)
        bar = alt.Chart(part).mark_bar(cornerRadiusEnd=4, height={"band": 0.7}).encode(
            x=alt.X("contrib:Q", title="contrib", scale=x_scale),
            y=y, tooltip=["indicator", "label", "contrib", "weight"],
            # indikator yang sudah mencapai weight-nya (risk = 1) -> merah
            color=alt.condition(alt.datum.contrib >= alt.datum.weight,
                                alt.value(TIER_COLOR["Tinggi"]), alt.value(LIGHT)),
        )
        cap = alt.Chart(part).mark_tick(color=LIGHT, opacity=0.5, thickness=2, clip=False).encode(
            x=alt.X("weight:Q", scale=x_scale), y=y, tooltip=["indicator", "weight"],
        )
        st.altair_chart(style_chart(bar + cap), width="stretch", height=34 * len(part) + 50)
    st.caption("Garis tipis = `weight` (poin maksimum indikator).")

    st.markdown(f"Skor total **{t['total']:.1f}** → {chip(t['tier'])}", unsafe_allow_html=True)
    with st.expander("Tabel"):
        st.dataframe(df, hide_index=True, width="stretch")

# ---------------------------------------------------------------- 4. Qwen
with tab_llm:
    nar = t["narration"]
    if mock:
        st.warning("Mode mock: qwen tidak dipanggil. Output di bawah adalah template deterministik.")
    left, right = st.columns(2)
    with left:
        st.subheader(f"Input to {cfg.SETTINGS['llm']['model']}")
        st.code(nar["prompt"], language=None, wrap_lines=True)
    with right:
        st.subheader(f"Output from {cfg.SETTINGS['llm']['model']}")
        st.info(nar["output"])
        if nar["thinking"]:
            st.markdown("**`<thinking>` context**")
            st.code(nar["thinking"], language=None, wrap_lines=True, height=150)
        if not mock:
            st.caption(f"Qwen duration: {t['seconds']['llm']:.1f} detik")

    # kiri: state yang dikirim ke Jev | kanan: hasil verif
    v_left, v_right = st.columns(2)
    with v_left:
        st.subheader("Jev verification")
        if t["verified"] is None:
            st.caption("Dilewati (mode mock atau verifikasi dimatikan).")
        else:
            st.markdown("**`state` yang dikirim ke Jev** (isi yang sama dengan input qwen + narasinya)")
            st.code(t["verify_state"], language=None, wrap_lines=True)
    if t["verified"] is not None:
        with v_right:
            st.subheader("Verification results")
            if not t["checks"]:
                st.warning("Output model kosong, jadi tidak dikirim ke Jev.")
            for k, p in t["checks"].items():
                limit = cfg.VERIFY["checks"][k]["max_noul"]
                st.metric(f"{k} · noul", f"{p:.2f}", f"{'lolos' if p <= limit else 'gagal'} (max_noul {limit})",
                          delta_color="normal" if p <= limit else "inverse")
                st.caption(cfg.VERIFY["checks"][k]["instructions"])
            if t["verified"]:
                st.success("Narasi lolos verifikasi dan digunakan sebagai output.")
            else:
                st.error("Narasi gagal verifikasi → diganti template fallback:")
                st.info(nar["fallback"])
