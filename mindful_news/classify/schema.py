from mindful_news.classify.labels import CARGAS, TEMAS

CLASSIFICATION_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "integer"},
                    "tema": {"type": "string", "enum": list(TEMAS)},
                    "carga": {"type": "string", "enum": list(CARGAS)},
                },
                "required": ["id", "tema", "carga"],
            },
        }
    },
    "required": ["items"],
}
