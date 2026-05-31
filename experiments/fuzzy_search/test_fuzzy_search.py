from fuzzy_search import fuzzy_search


def test_typo_city_match() -> None:
    result = fuzzy_search("Pariss", kind="city")
    assert result["status"] == "matched"
    assert result["selected"]["id"] == "city:Paris"


def test_chinese_city_alias() -> None:
    result = fuzzy_search("伦敦", kind="city")
    assert result["status"] == "matched"
    assert result["selected"]["id"] == "city:London"


def test_airport_code_match() -> None:
    result = fuzzy_search("CDG", kind="airport")
    assert result["status"] == "matched"
    assert result["selected"]["id"] == "airport:CDG"


def test_poi_brand_plus_keyword_beats_generic_tag() -> None:
    result = fuzzy_search("Wagas轻食", kind="poi")
    assert result["status"] == "matched"
    assert result["selected"]["id"] == "poi:CB005"


def test_generic_place_query_stays_ambiguous() -> None:
    result = fuzzy_search("公园", kind="poi")
    assert result["status"] == "ambiguous"


def test_context_override_requires_strong_evidence() -> None:
    result = fuzzy_search(
        "Paris",
        kind="city",
        context={
            "recent_destinations": ["Shanghai", "Shanghai"],
            "itinerary_cities": ["Shanghai"],
            "current_city": "London",
        },
    )
    assert result["status"] == "context_override"
    assert result["selected"]["id"] == "city:Shanghai"


def test_unknown_inventory_does_not_invent() -> None:
    result = fuzzy_search("广州", kind="city")
    assert result["status"] == "no_match"
    assert result["selected"] is None
