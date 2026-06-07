from mindful_news.thumbnails import clean_thumbnail, is_placeholder_thumbnail


def test_clean_thumbnail_rejects_generic_la_diaria() -> None:
    assert clean_thumbnail("https://ladiaria.com.uy/static/meta/la-diaria-1200x630.png") is None


def test_clean_thumbnail_keeps_photologue() -> None:
    url = "https://ladiaria.com.uy/media/photologue/photos/cache/foo.webp"
    assert clean_thumbnail(url) == url


def test_is_placeholder_thumbnail_empty() -> None:
    assert is_placeholder_thumbnail(None) is True
    assert is_placeholder_thumbnail("") is True
