from pricewatch.utils.urls import normalize_site, site_search_query, urls_share_site


def test_normalize_site_from_domain() -> None:
    assert normalize_site("www.Bol.com") == "bol.com"


def test_normalize_site_from_url() -> None:
    assert normalize_site("https://www.mediamarkt.nl/product") == "mediamarkt.nl"


def test_site_search_query() -> None:
    assert site_search_query("bol.com", "Sony headphones") == "site:bol.com Sony headphones"


def test_urls_share_site() -> None:
    assert urls_share_site("https://www.bol.com/a", "https://bol.com/b")
