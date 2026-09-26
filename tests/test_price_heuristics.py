from pricewatch.services.price_heuristics import extract_price_heuristic


def test_json_ld_product_offer() -> None:
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"Product","name":"Phone","offers":{"@type":"Offer","price":"899.00","priceCurrency":"EUR"}}
    </script>
    </head></html>
    """
    result = extract_price_heuristic(html, currency_hint="EUR")
    assert result is not None
    assert result["price"] == 899.0
    assert result["currency"] == "EUR"
    assert result["confidence"] == "high"


def test_dutch_euro_in_text() -> None:
    html = "<body>Actieprijs: € 749,00 incl. btw</body>"
    result = extract_price_heuristic(html, currency_hint="EUR")
    assert result is not None
    assert result["price"] == 749.0


def test_thousands_with_dot_and_comma_cents() -> None:
    html = '<span class="price">€ 1.299,00</span>'
    result = extract_price_heuristic(html, currency_hint="EUR")
    assert result is not None
    assert result["price"] == 1299.0


def test_phonemarket_html_entity_and_comma_dash() -> None:
    html = """
    2e Kans Apple iPhone 17e 256GB White
    &euro; 22,95 accessory
    &euro; 719,- 3 op voorraad Toevoegen aan winkelwagen
    """
    result = extract_price_heuristic(html, currency_hint="EUR")
    assert result is not None
    assert result["price"] == 719.0
