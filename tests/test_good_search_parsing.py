from pricewatch.services.good_search import GoodSearchClient


def test_parse_search_results_from_json_list() -> None:
    client = GoodSearchClient.__new__(GoodSearchClient)
    results = client._parse_search_results(
        [{"title": "Widget", "url": "https://shop.example/widget", "snippet": "$19.99"}]
    )
    assert len(results) == 1
    assert results[0]["url"] == "https://shop.example/widget"


def test_parse_search_results_from_text_urls() -> None:
    client = GoodSearchClient.__new__(GoodSearchClient)
    text = "Best deal\nhttps://shop.example/item\nAnother line https://other.example/p"
    results = client._parse_search_results_from_text(text)
    assert len(results) == 2
    assert results[0]["url"] == "https://shop.example/item"
