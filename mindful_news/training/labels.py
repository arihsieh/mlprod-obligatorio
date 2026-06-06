import unicodedata

from mindful_news.classify.labels import CARGAS, TEMAS

TEMA_TO_ID = {label: index for index, label in enumerate(TEMAS)}
CARGA_TO_ID = {label: index for index, label in enumerate(CARGAS)}

ID_TO_TEMA = {index: label for label, index in TEMA_TO_ID.items()}
ID_TO_CARGA = {index: label for label, index in CARGA_TO_ID.items()}


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def normalize_label(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _strip_accents(value.strip().lower())
    return cleaned or None
