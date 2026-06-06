import re

from mindful_news.config import load_config


def preprocess(texto: str) -> str:
    """Shared train/serve text normalization (no lowercasing or stemming)."""
    texto = texto.strip()
    return re.sub(r"\s+", " ", texto)


def _input_config() -> dict:
    return load_config().get("training", {}).get("input", {})


def input_text_mode() -> str:
    cfg = _input_config()
    return "seccion_titulo" if cfg.get("include_seccion", True) else "titulo"


def build_input_text(titulo: str, seccion: str | None = None) -> str:
    """Build model input from headline title and optional section."""
    titulo = preprocess(str(titulo))
    cfg = _input_config()
    if not cfg.get("include_seccion", True):
        return titulo

    if seccion is None:
        return titulo
    seccion_clean = preprocess(str(seccion))
    if not seccion_clean or seccion_clean.lower() == "nan":
        return titulo

    sep = cfg.get("separator", " | ")
    template = cfg.get("template", "{seccion}{sep}{titulo}")
    return template.format(seccion=seccion_clean, titulo=titulo, sep=sep)
