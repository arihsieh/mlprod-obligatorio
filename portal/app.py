from __future__ import annotations

import streamlit as st

from mindful_news.classify.labels import CARGAS, TEMAS
from mindful_news.db import fetch_headlines, init_db, stats

TEMA_LABELS = {
    "politica": "Política",
    "seguridad": "Seguridad",
    "economia": "Economía",
    "salud": "Salud",
    "deportes": "Deportes",
    "cultura": "Cultura",
    "tecnologia": "Tecnología",
    "medioambiente": "Medioambiente",
    "internacional": "Internacional",
    "sociedad": "Sociedad",
}

CARGA_LABELS = {"baja": "Baja", "media": "Media", "alta": "Alta"}


def _format_tema(value: str) -> str:
    return TEMA_LABELS.get(value, value)


def _format_carga(value: str) -> str:
    return CARGA_LABELS.get(value, value)


def main() -> None:
    st.set_page_config(page_title="Mindful News", page_icon="📰", layout="wide")
    st.title("Noticias UY — Clasificadas")
    st.caption("Titulares uruguayos con tema y carga emocional. Cada nota enlaza al medio original.")

    init_db()
    db_stats = stats()

    with st.sidebar:
        st.subheader("Filtros")
        temas_sel = st.multiselect(
            "Temas",
            options=list(TEMAS),
            default=["deportes", "cultura", "tecnologia"],
            format_func=_format_tema,
        )
        cargas_sel = st.multiselect(
            "Carga emocional",
            options=list(CARGAS),
            default=["baja", "media"],
            format_func=_format_carga,
        )
        limit = st.slider("Cantidad máxima", min_value=10, max_value=500, value=100, step=10)
        st.divider()
        st.metric("Sin clasificar", db_stats["unclassified"])
        if st.button("Actualizar"):
            st.rerun()

    if not temas_sel or not cargas_sel:
        st.info("Seleccioná al menos un tema y una carga.")
        return

    rows = fetch_headlines(temas=temas_sel, cargas=cargas_sel, limit=limit)
    st.write(f"**{len(rows)}** titulares")

    for row in rows:
        titulo = row["titulo"]
        url = row["url"]
        medio = row["medio"]
        tema = _format_tema(row["tema"])
        carga = _format_carga(row["carga"])
        fecha = row.get("fecha") or row.get("scraped_at")
        fecha_str = fecha.strftime("%Y-%m-%d %H:%M") if fecha else "—"

        st.markdown(f"**[{titulo}]({url})**")
        st.caption(f"{medio} · {tema} · carga {carga} · {fecha_str}")
        st.divider()


if __name__ == "__main__":
    main()
