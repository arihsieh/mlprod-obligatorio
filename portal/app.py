"""portal/app.py — Mindful News v2 — rediseño completo."""
from __future__ import annotations

import html as _html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from mindful_news.classify.labels import CARGAS, TEMAS
from mindful_news.db import fetch_headlines, init_db

# ── Metadata ──────────────────────────────────────────────────────────────────

TEMAS_META: dict[str, tuple[str, str]] = {
    "politica":      ("Política",      "🏛️"),
    "seguridad":     ("Seguridad",     "🛡️"),
    "economia":      ("Economía",      "📈"),
    "salud":         ("Salud",         "🩺"),
    "deportes":      ("Deportes",      "⚽"),
    "cultura":       ("Cultura",       "🎭"),
    "tecnologia":    ("Tecnología",    "💡"),
    "medioambiente": ("Medioambiente", "🌿"),
    "internacional": ("Internacional", "🌍"),
    "sociedad":      ("Sociedad",      "👥"),
}

CARGAS_META: dict[str, tuple[str, str]] = {
    "baja":  ("Serena",   "#4ade80"),
    "media": ("Moderada", "#fbbf24"),
    "alta":  ("Intensa",  "#f87171"),
}

DEFAULT_TEMAS  = ["deportes", "cultura", "tecnologia", "salud", "medioambiente"]
DEFAULT_CARGAS = ["baja", "media"]
LIMIT_OPTIONS  = [20, 50, 100, 200]

# ── Logo SVG (teal, transparent background) ───────────────────────────────────

LOGO_SVG = (
    '<svg viewBox="0 0 680 680" xmlns="http://www.w3.org/2000/svg"'
    ' width="48" height="48" style="flex-shrink:0">'
    "<defs>"
    '<linearGradient id="wg" x1="0%" y1="0%" x2="100%" y2="100%">'
    '<stop offset="0%" stop-color="#2dd4bf"/>'
    '<stop offset="100%" stop-color="#059669"/>'
    "</linearGradient>"
    '<clipPath id="cc"><circle cx="340" cy="340" r="268"/></clipPath>'
    "</defs>"
    '<circle cx="340" cy="340" r="270" fill="none" stroke="#2dd4bf" stroke-width="6"/>'
    '<g clip-path="url(#cc)" fill="none" stroke="url(#wg)" stroke-linecap="round" stroke-linejoin="round">'
    '<path stroke-width="5.5" d="M70 345 Q180 290,340 320 Q500 350,610 295"/>'
    '<path stroke-width="5.5" d="M70 375 Q170 315,340 348 Q510 380,610 322"/>'
    '<path stroke-width="5.5" d="M82 408 Q175 345,340 378 Q510 410,605 355"/>'
    '<path stroke-width="5.5" d="M105 442 Q185 378,340 410 Q505 442,598 390"/>'
    '<path stroke-width="5.5" d="M135 478 Q200 415,340 445 Q498 476,580 425"/>'
    '<path stroke-width="5.5" d="M175 515 Q222 455,340 480 Q488 510,555 462"/>'
    '<path stroke-width="5.5" d="M222 552 Q252 498,340 518 Q468 545,520 502"/>'
    '<path stroke-width="5.5" d="M278 585 Q295 548,340 558 Q430 576,475 548"/>'
    '<path stroke-width="5.5" d="M338 608 Q342 598,355 595 Q390 590,428 588"/>'
    "</g></svg>"
)

# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700&display=swap');

:root {
  --bg:       #080c12;
  --surf:     #0d1520;
  --card:     #101a28;
  --card-h:   #152136;
  --border:   #1c2d42;
  --teal:     #14b8a6;
  --teal-l:   #2dd4bf;
  --txt1:     #e2e8f0;
  --txt2:     #94a3b8;
  --txt3:     #4a6080;
  --green:    #4ade80;
  --green-bg: rgba(74,222,128,.09);
  --amber:    #fbbf24;
  --amber-bg: rgba(251,191,36,.09);
  --red:      #f87171;
  --red-bg:   rgba(248,113,113,.09);
  --r:        14px;
  --r-sm:     8px;
}

*, *::before, *::after { box-sizing: border-box; }

/* ─ hide default chrome ─ */
#MainMenu,
header[data-testid="stHeader"],
footer,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"],
.stDeployButton { visibility: hidden !important; height: 0 !important; overflow: hidden !important; }

/* ─ app background ─ */
.stApp, body, .main,
[data-testid="stAppViewContainer"],
section[data-testid="stAppViewContainer"] > .main {
  background: var(--bg) !important;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}

/* ─ container ─ */
.main .block-container {
  max-width: 1180px !important;
  padding: 0 1.25rem 5rem !important;
  margin: 0 auto !important;
}

[data-testid="stVerticalBlock"] { gap: 0.2rem !important; }

/* ─ scrollbar ─ */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 999px; }
::-webkit-scrollbar-thumb:hover { background: var(--txt3); }

/* ─ header ─ */
.mn-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 1.5rem 0 1.3rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 1.5rem;
}
.mn-header-text { flex: 1; }
.mn-header-text h1 {
  font-size: 1.55rem; font-weight: 700;
  color: var(--txt1); margin: 0; letter-spacing: -.025em;
}
.mn-header-text p { font-size: .8rem; color: var(--txt3); margin: 3px 0 0; }

/* ─ count + legend bar ─ */
.mn-countbar {
  display: flex; align-items: center; gap: 12px;
  margin: 1.25rem 0 .4rem; flex-wrap: wrap;
}
.mn-count-pill {
  background: rgba(20,184,166,.12); color: var(--teal-l);
  font-size: .73rem; font-weight: 600;
  padding: 4px 13px; border-radius: 999px;
}
.mn-legend { display: flex; gap: 14px; flex-wrap: wrap; }
.mn-legend-item {
  display: flex; align-items: center; gap: 6px;
  font-size: .72rem; color: var(--txt2);
}

/* ─ animated dots ─ */
.mn-dot {
  width: 7px; height: 7px; border-radius: 50%;
  display: inline-block; flex-shrink: 0;
}
.mn-dot--baja  { background: var(--green); animation: breathe 3.5s ease-in-out infinite; }
.mn-dot--media { background: var(--amber); animation: breathe 2.2s ease-in-out infinite; }
.mn-dot--alta  { background: var(--red);   animation: pulse-alert 1.1s ease-in-out infinite; }

@keyframes breathe {
  0%,100% { opacity: 1;   transform: scale(1); }
  50%      { opacity: .4; transform: scale(.6); }
}
@keyframes pulse-alert {
  0%,100% { opacity: 1;  transform: scale(1);    box-shadow: 0 0 0 0 rgba(248,113,113,.55); }
  50%      { opacity: .8; transform: scale(1.35); box-shadow: 0 0 0 5px rgba(248,113,113,0); }
}

/* ─ cards grid ─ */
.mn-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(288px, 1fr));
  gap: 13px;
  margin-top: .4rem;
}

/* ─ card ─ */
.mn-card {
  display: block; text-decoration: none !important;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--r);
  padding: 17px 19px;
  transition: background .18s, transform .18s, border-color .18s, box-shadow .18s;
  animation: slideUp .35s ease both;
  position: relative; overflow: hidden;
}
.mn-card::after {
  content: ''; position: absolute;
  top: 0; left: 0; right: 0; height: 2px;
  border-radius: var(--r) var(--r) 0 0;
  opacity: 0; transition: opacity .18s;
}
.mn-card--baja::after  { background: var(--green); }
.mn-card--media::after { background: var(--amber); }
.mn-card--alta::after  { background: var(--red);   }

.mn-card:hover {
  background: var(--card-h);
  transform: translateY(-3px);
  border-color: #253d5a;
  box-shadow: 0 10px 28px rgba(0,0,0,.4);
}
.mn-card:hover::after { opacity: 1; }

@keyframes slideUp {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ─ card inner ─ */
.mn-card-meta {
  display: flex; align-items: center;
  justify-content: space-between;
  gap: 8px; margin-bottom: 9px;
}
.mn-topic {
  font-size: .69rem; font-weight: 600;
  color: var(--teal); background: rgba(20,184,166,.1);
  padding: 2px 9px; border-radius: 999px;
  white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; max-width: 165px;
}
.mn-date { font-size: .67rem; color: var(--txt3); white-space: nowrap; }
.mn-title {
  font-size: .92rem; font-weight: 500;
  color: var(--txt1); line-height: 1.48;
  margin: 0 0 13px;
}
.mn-card-foot {
  display: flex; align-items: center;
  justify-content: space-between; gap: 8px;
}
.mn-medio {
  font-size: .67rem; color: var(--txt3);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mn-carga {
  display: flex; align-items: center; gap: 5px;
  font-size: .69rem; font-weight: 600;
  padding: 2px 9px; border-radius: 999px; flex-shrink: 0;
}
.mn-carga--baja  { color: var(--green); background: var(--green-bg); }
.mn-carga--media { color: var(--amber); background: var(--amber-bg); }
.mn-carga--alta  { color: var(--red);   background: var(--red-bg);   }

/* ─ empty ─ */
.mn-empty {
  text-align: center; padding: 5rem 2rem;
  color: var(--txt3);
}
.mn-empty-icon { font-size: 2.8rem; margin-bottom: 1rem; }
.mn-empty p { font-size: .88rem; margin: 0; }

/* ─ footer ─ */
.mn-footer {
  text-align: center;
  margin-top: 3rem;
  font-size: .68rem;
  color: var(--txt3);
  padding-top: 1.2rem;
  border-top: 1px solid var(--border);
}

/* ─ guide dialog content ─ */
.mn-guide-intro {
  font-size: .87rem; color: var(--txt2); line-height: 1.65;
  margin-bottom: 1.4rem;
  padding: 12px 16px;
  background: rgba(20,184,166,.07);
  border-left: 3px solid var(--teal);
  border-radius: 0 var(--r-sm) var(--r-sm) 0;
}
.mn-guide-steps { display: flex; flex-direction: column; gap: 10px; margin-bottom: 1.4rem; }
.mn-guide-step {
  display: flex; gap: 13px; align-items: flex-start;
  padding: 13px 15px;
  background: var(--surf);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
}
.mn-guide-icon {
  font-size: 1.3rem; flex-shrink: 0;
  width: 40px; height: 40px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(20,184,166,.08);
  border-radius: var(--r-sm);
}
.mn-guide-text h4 { color: var(--txt1); margin: 0 0 3px; font-size: .86rem; }
.mn-guide-text p  { color: var(--txt2); margin: 0; font-size: .79rem; line-height: 1.55; }
.mn-guide-carga-grid { display: flex; flex-direction: column; gap: 7px; }
.mn-guide-carga-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 13px; border-radius: var(--r-sm);
  font-size: .81rem;
}
.mn-guide-carga-row--baja  { background: var(--green-bg); }
.mn-guide-carga-row--media { background: var(--amber-bg); }
.mn-guide-carga-row--alta  { background: var(--red-bg);   }
.mn-guide-carga-name { font-weight: 600; min-width: 72px; }
.mn-guide-carga-row--baja  .mn-guide-carga-name { color: var(--green); }
.mn-guide-carga-row--media .mn-guide-carga-name { color: var(--amber); }
.mn-guide-carga-row--alta  .mn-guide-carga-name { color: var(--red);   }
.mn-guide-carga-desc { color: var(--txt2); font-size: .78rem; }

/* ─ Streamlit widget overrides ─ */
[data-testid="stMultiSelect"] label,
[data-testid="stSlider"] label,
[data-testid="stSelectSlider"] label {
  font-size: .71rem !important; font-weight: 600 !important;
  letter-spacing: .055em !important; text-transform: uppercase !important;
  color: var(--txt3) !important;
}
[data-testid="stMultiSelect"] > div > div {
  background: var(--surf) !important;
  border-color: var(--border) !important;
  border-radius: var(--r-sm) !important;
}
span[data-baseweb="tag"] {
  background: rgba(20,184,166,.15) !important;
  color: var(--teal-l) !important;
}
/* selected tag X button */
span[data-baseweb="tag"] span { color: var(--teal-l) !important; }

.stButton > button {
  background: transparent !important;
  color: var(--txt2) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--r-sm) !important;
  font-size: .78rem !important;
  font-weight: 500 !important;
  padding: 5px 14px !important;
  transition: all .15s !important;
}
.stButton > button:hover {
  border-color: var(--teal) !important;
  color: var(--teal) !important;
  background: rgba(20,184,166,.08) !important;
}

/* dialog overlay */
[data-testid="stDialog"] > div > div {
  background: var(--surf) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--r) !important;
}

/* ─ mobile ─ */
@media (max-width: 620px) {
  .mn-grid { grid-template-columns: 1fr; gap: 10px; }
  .mn-header-text h1 { font-size: 1.2rem; }
  .main .block-container { padding: 0 .75rem 3rem !important; }
  .mn-header { padding: 1rem 0 .9rem; }
  .mn-legend { gap: 10px; }
}
"""

# ── Guide HTML ────────────────────────────────────────────────────────────────

GUIDE_HTML = """
<div>
  <p class="mn-guide-intro">
    <strong>Mindful News</strong> clasifica titulares uruguayos por
    <strong>tema</strong> y <strong>carga emocional</strong> usando un modelo
    de ML propio, para que puedas informarte con más consciencia sobre
    lo que consumís cada día.
  </p>

  <div class="mn-guide-steps">
    <div class="mn-guide-step">
      <div class="mn-guide-icon">🎯</div>
      <div class="mn-guide-text">
        <h4>Filtrá por temas</h4>
        <p>Elegí las categorías que te interesan. Tu selección se guarda
           automáticamente en la URL&nbsp;— guardá la página como favorito
           y siempre verás lo mismo.</p>
      </div>
    </div>
    <div class="mn-guide-step">
      <div class="mn-guide-icon">🌡️</div>
      <div class="mn-guide-text">
        <h4>Controlá la carga emocional</h4>
        <p>Cada noticia tiene un nivel de impacto. Podés ver solo las más
           tranquilas, o incluir las intensas cuando querés estar al
           tanto de todo.</p>
      </div>
    </div>
    <div class="mn-guide-step">
      <div class="mn-guide-icon">📰</div>
      <div class="mn-guide-text">
        <h4>Cada tarjeta va al medio original</h4>
        <p>No reproducimos contenido. Cada click te lleva directo al
           artículo en el medio correspondiente.</p>
      </div>
    </div>
  </div>

  <div class="mn-guide-carga-grid">
    <div class="mn-guide-carga-row mn-guide-carga-row--baja">
      <span class="mn-dot mn-dot--baja"></span>
      <span class="mn-guide-carga-name">Serena</span>
      <span class="mn-guide-carga-desc">Bajo impacto emocional — ideal para arrancar el día tranquilo.</span>
    </div>
    <div class="mn-guide-carga-row mn-guide-carga-row--media">
      <span class="mn-dot mn-dot--media"></span>
      <span class="mn-guide-carga-name">Moderada</span>
      <span class="mn-guide-carga-desc">Información relevante con algo de tensión — el punto medio.</span>
    </div>
    <div class="mn-guide-carga-row mn-guide-carga-row--alta">
      <span class="mn-dot mn-dot--alta"></span>
      <span class="mn-guide-carga-name">Intensa</span>
      <span class="mn-guide-carga-desc">Alto impacto emocional — procesá con cuidado.</span>
    </div>
  </div>
</div>
"""


# ── Guide dialog ──────────────────────────────────────────────────────────────


@st.dialog("¿Cómo funciona Mindful News?", width="large")
def _guide_dialog() -> None:
    st.markdown(GUIDE_HTML, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("¡Entendido, empezar! →", use_container_width=True):
        st.session_state.guide_seen = True
        st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    st.set_page_config(
        page_title="Mindful News",
        page_icon="🌊",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)

    init_db()

    # ── URL param persistence ──────────────────────────────────────────────
    params = st.query_params
    t_raw = params.get("t", "")
    c_raw = params.get("c", "")
    n_raw = params.get("n", "50")

    init_temas  = [x for x in t_raw.split(",") if x in list(TEMAS)]  if t_raw  else DEFAULT_TEMAS
    init_cargas = [x for x in c_raw.split(",") if x in list(CARGAS)] if c_raw  else DEFAULT_CARGAS
    init_limit  = int(n_raw) if n_raw.isdigit() and int(n_raw) in LIMIT_OPTIONS else 50

    # ── First-time guide ───────────────────────────────────────────────────
    if "guide_seen" not in st.session_state:
        st.session_state.guide_seen = False

    # ── Header ────────────────────────────────────────────────────────────
    hdr_col, btn_col = st.columns([11, 1])
    with hdr_col:
        st.markdown(
            f'<div class="mn-header">'
            f'{LOGO_SVG}'
            f'<div class="mn-header-text">'
            f"<h1>Mindful News</h1>"
            f"<p>Noticias uruguayas · tu información sin ruido</p>"
            f"</div></div>",
            unsafe_allow_html=True,
        )
    with btn_col:
        st.markdown("<div style='padding-top:1.6rem'>", unsafe_allow_html=True)
        if st.button("ℹ️", help="Ver guía de uso"):
            st.session_state.guide_seen = False
        st.markdown("</div>", unsafe_allow_html=True)

    if not st.session_state.guide_seen:
        _guide_dialog()

    # ── Filters ───────────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns([4, 2, 1])

    with fc1:
        temas_sel: list[str] = st.multiselect(
            "Temas",
            options=list(TEMAS),
            default=init_temas,
            format_func=lambda k: f"{TEMAS_META[k][1]} {TEMAS_META[k][0]}",
        )

    with fc2:
        cargas_sel: list[str] = st.multiselect(
            "Carga emocional",
            options=list(CARGAS),
            default=init_cargas,
            format_func=lambda k: CARGAS_META[k][0],
        )

    with fc3:
        limit: int = st.select_slider(
            "Cantidad",
            options=LIMIT_OPTIONS,
            value=init_limit,
        )

    # Persist current selection to URL (updates browser address bar)
    st.query_params["t"] = ",".join(temas_sel) if temas_sel else ""
    st.query_params["c"] = ",".join(cargas_sel) if cargas_sel else ""
    st.query_params["n"] = str(limit)

    # ── Guard ─────────────────────────────────────────────────────────────
    if not temas_sel or not cargas_sel:
        st.markdown(
            '<div class="mn-empty">'
            '<div class="mn-empty-icon">🧘</div>'
            "<p>Seleccioná al menos un tema y una carga emocional.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    # ── Fetch ─────────────────────────────────────────────────────────────
    rows = fetch_headlines(temas=temas_sel, cargas=cargas_sel, limit=limit)

    if not rows:
        st.markdown(
            '<div class="mn-empty">'
            '<div class="mn-empty-icon">🔍</div>'
            "<p>No hay noticias con esos filtros por el momento.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    # ── Count + legend bar ────────────────────────────────────────────────
    st.markdown(
        f'<div class="mn-countbar">'
        f'<span class="mn-count-pill">{len(rows)} titulares</span>'
        f'<div class="mn-legend">'
        f'<span class="mn-legend-item"><span class="mn-dot mn-dot--baja"></span>&nbsp;Serena</span>'
        f'<span class="mn-legend-item"><span class="mn-dot mn-dot--media"></span>&nbsp;Moderada</span>'
        f'<span class="mn-legend-item"><span class="mn-dot mn-dot--alta"></span>&nbsp;Intensa</span>'
        f"</div></div>",
        unsafe_allow_html=True,
    )

    # ── Cards grid ────────────────────────────────────────────────────────
    parts = ['<div class="mn-grid">']

    for i, row in enumerate(rows):
        titulo  = _html.escape(str(row.get("titulo", "")))
        url     = _html.escape(str(row.get("url", "#")))
        medio   = _html.escape(str(row.get("medio", "")))
        t_key   = str(row.get("tema", ""))
        c_key   = str(row.get("carga", ""))

        t_label, t_emoji = TEMAS_META.get(t_key, (t_key, "📰"))
        c_label, _       = CARGAS_META.get(c_key, ("?", "#666"))

        fecha = row.get("fecha") or row.get("scraped_at")
        if fecha:
            fecha_str = f"{fecha.day} {fecha.strftime('%b')}"
        else:
            fecha_str = "—"

        delay = f"{min(i * 0.04, 0.8):.2f}s"

        parts.append(
            f'<a href="{url}" target="_blank" rel="noopener noreferrer"'
            f' class="mn-card mn-card--{c_key}" style="animation-delay:{delay}">'
            f'<div class="mn-card-meta">'
            f'<span class="mn-topic">{t_emoji} {t_label}</span>'
            f'<span class="mn-date">{fecha_str}</span>'
            f"</div>"
            f'<p class="mn-title">{titulo}</p>'
            f'<div class="mn-card-foot">'
            f'<span class="mn-medio">{medio}</span>'
            f'<span class="mn-carga mn-carga--{c_key}">'
            f'<span class="mn-dot mn-dot--{c_key}"></span>'
            f"{c_label}"
            f"</span>"
            f"</div>"
            f"</a>"
        )

    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)

    # ── Footer ────────────────────────────────────────────────────────────
    st.markdown(
        '<div class="mn-footer">'
        "Mindful News &nbsp;·&nbsp; Clasificación ML &nbsp;·&nbsp;"
        " mmBERT-small &nbsp;·&nbsp; Uruguay 🇺🇾"
        "</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
