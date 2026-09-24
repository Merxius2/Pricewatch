from pricewatch.services.good_search import GoodSearchClient


def test_parse_search_page_extracts_urls() -> None:
    client = GoodSearchClient.__new__(GoodSearchClient)
    payload = {
        "content": (
            "Amazon.com: Sony WH-1000XM5 www.amazon.com/sony-wh1000xm5/s?k=sony+wh1000xm5\n"
            "Best Buy Sony headphones www.bestbuy.com/site/sony-wh-1000xm5.p\n"
        )
    }
    results = client._parse_search_page(payload)
    assert len(results) >= 2
    assert any("amazon.com" in r["url"] for r in results)


def test_parse_scrape_payload_from_json_text() -> None:
    client = GoodSearchClient.__new__(GoodSearchClient)
    payload = client._parse_scrape_payload('{"content":"Price $19.99","blocked":false}')
    assert payload["content"] == "Price $19.99"
    assert payload["blocked"] is False
