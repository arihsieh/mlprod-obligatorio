from dataclasses import dataclass
from datetime import datetime


@dataclass
class Headline:
    titulo: str
    url: str
    medio: str
    thumbnail_url: str | None = None
    seccion: str | None = None
    fecha: datetime | None = None
    external_id: str | None = None

    def __post_init__(self) -> None:
        if not self.external_id:
            self.external_id = self.url
