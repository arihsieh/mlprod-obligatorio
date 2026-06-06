from mindful_news.classify.labels import CARGAS, TEMAS

DEFAULT_SYSTEM_PROMPT = f"""Sos un clasificador de titulares de noticias uruguayas.
Clasificá cada titular en tema ({", ".join(TEMAS)}) y carga ({", ".join(CARGAS)}).
Respondé solo JSON válido según el schema."""

DEFAULT_BATCH_USER_TEMPLATE = "Clasificá este lote:\n{batch_json}"

PROMPT_OPTIMIZATION_REQUEST = f"""Diseñá el mejor prompt para clasificar titulares uruguayos en lotes.
Etiquetas tema: {", ".join(TEMAS)}. Carga: {", ".join(CARGAS)}.
Entregá JSON con system_prompt, batch_user_template (con {{batch_json}}), rationale, recommended_batch_size."""
