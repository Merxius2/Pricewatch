from pricewatch.api.schemas import TrackedItemCreate


def test_new_item_defaults_to_eur() -> None:
    item = TrackedItemCreate(name="Iphone 17e", search_query="iphone 17e 256gb")
    assert item.currency == "EUR"
