from datetime import datetime

from mindful_news.dedup import dedupe_headlines, stable_external_id
from mindful_news.models import Headline


def test_stable_external_id_from_numeric_field():
    h = Headline(
        titulo="Test",
        url="https://www.elobservador.com.uy/foo-n6046384",
        medio="El Observador",
        external_id="6046384",
    )
    assert stable_external_id(h) == "6046384"


def test_stable_external_id_from_eo_url():
    h = Headline(
        titulo="Test",
        url="https://www.elobservador.com.uy/estados-unidos/washington-eleva-n6046384",
        medio="El Observador",
        external_id="https://wrong",
    )
    assert stable_external_id(h) == "6046384"


def test_dedupe_headlines_keeps_one_per_external_id():
    base = datetime(2026, 6, 4, 20, 32)
    older = Headline(
        titulo="Old slug",
        url="https://www.elobservador.com.uy/a/washington-sanciona-n6046384",
        medio="El Observador",
        external_id="6046384",
        fecha=base,
    )
    newer = Headline(
        titulo="New slug",
        url="https://www.elobservador.com.uy/a/washington-eleva-n6046384",
        medio="El Observador",
        external_id="6046384",
        fecha=datetime(2026, 6, 4, 21, 0),
    )
    result = dedupe_headlines([older, newer])
    assert len(result) == 1
    assert result[0].url.endswith("washington-eleva-n6046384")
