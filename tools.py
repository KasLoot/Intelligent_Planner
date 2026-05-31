from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
TRANSPORT_DIR = BASE_DIR / "database" / "transport"
POI_PATH = BASE_DIR / "frontend" / "frontend" / "src" / "data" / "poi_database.json"

POI_DOMAIN_MAP = {
    "restaurant": "restaurant",
    "hotel": "hotel",
    "attraction": "entertainment",
    "mall": "entertainment",
    "entertainment": "entertainment",
    "transport": "transport",
    "resting_area": "entertainment",
}

CITY_ALIASES = {
    "Amsterdam": ["阿姆斯特丹"],
    "Barcelona": ["巴塞罗那"],
    "Dubai": ["迪拜"],
    "Frankfurt": ["法兰克福"],
    "London": ["伦敦"],
    "New York": ["纽约"],
    "Paris": ["巴黎"],
    "Rome": ["罗马"],
    "Shanghai": ["上海"],
    "Zurich": ["苏黎世"],
}

CATEGORY_ALIASES = {
    "hotel": ["酒店", "住宿", "住"],
    "restaurant": ["餐厅", "饭店", "吃饭", "用餐", "美食"],
    "attraction": ["景点", "公园", "展馆", "游玩"],
    "mall": ["商场", "购物"],
    "transport": ["交通", "地铁", "车站", "机场"],
    "entertainment": ["娱乐", "电影", "酒吧", "ktv", "KTV"],
    "resting_area": ["休息", "避雨"],
}

MIN_FUZZY_MATCH_SCORE = 0.56
FUZZY_AMBIGUITY_DELTA = 0.06
FUZZY_CONTEXT_OVERRIDE_MARGIN = 0.18


def get_current_location() -> dict[str, str]:
    return {
        "street": "London",
        "city": "London",
        "postal_code": "",
        "country": "UK",
    }


def get_current_date() -> dict[str, str]:
    return {
        "current_date": "2026-05-28",
        "timezone": "Europe/London",
    }


def resolve_city_transport_nodes(city: str) -> dict[str, Any]:
    airports = _airports_for_city(city)
    return {
        "ok": bool(airports),
        "city": city,
        "airports": airports,
        "airport_codes": [airport["iata"] for airport in airports],
    }


def search_flights(
    origin_city: str,
    destination_city: str,
    travel_date: str,
    max_results: int = 10,
) -> dict[str, Any]:
    origin_airports = _airports_for_city(origin_city)
    destination_airports = _airports_for_city(destination_city)

    if not origin_airports:
        return {"ok": False, "error": f"No airports found for origin city: {origin_city}"}
    if not destination_airports:
        return {"ok": False, "error": f"No airports found for destination city: {destination_city}"}

    origin_codes = {airport["iata"] for airport in origin_airports}
    destination_codes = {airport["iata"] for airport in destination_airports}
    flights = _load_json(TRANSPORT_DIR / "aero.json")
    trip_date = date.fromisoformat(travel_date)

    candidates = []
    for flight in flights:
        if flight["departure"] not in origin_codes or flight["arrival"] not in destination_codes:
            continue
        if not _runs_on_date(flight.get("routine", "daily"), trip_date):
            continue
        for index, schedule in enumerate(flight["schedule"]):
            departure_at, arrival_at = _schedule_to_datetimes(travel_date, schedule)
            candidates.append(
                {
                    "candidate_id": f"{flight['id']}#{index}",
                    "flight_id": flight["id"],
                    "airline": flight["airline"],
                    "flight_number": flight["flight_number"],
                    "departure_airport": flight["departure"],
                    "arrival_airport": flight["arrival"],
                    "departure_at": departure_at,
                    "arrival_at": arrival_at,
                    "duration_minutes": _duration_minutes(departure_at, arrival_at),
                    "price": flight["price"],
                    "currency": flight["currency"],
                    "baggage_allowance": flight.get("additional_info", {}).get("baggage_allowance"),
                    "meal_service": flight.get("additional_info", {}).get("meal_service"),
                }
            )

    candidates.sort(key=lambda item: (item["price"], item["departure_at"]))
    return {
        "ok": True,
        "origin_city": origin_city,
        "destination_city": destination_city,
        "travel_date": travel_date,
        "origin_airports": sorted(origin_codes),
        "destination_airports": sorted(destination_codes),
        "count": len(candidates),
        "candidates": candidates[:max_results],
    }


def plan_trip_transport(
    destination_city: str,
    outbound_date: str,
    return_date: str,
    origin_city: str | None = None,
    max_options: int = 5,
) -> dict[str, Any]:
    location = get_current_location()
    resolved_origin = origin_city or location["city"]
    outbound = search_flights(resolved_origin, destination_city, outbound_date, max_results=12)
    inbound = search_flights(destination_city, resolved_origin, return_date, max_results=12)

    if not outbound.get("ok"):
        return outbound
    if not inbound.get("ok"):
        return inbound

    options = _pair_flights(outbound["candidates"], inbound["candidates"], max_options)
    return {
        "ok": True,
        "request": {
            "origin_city": resolved_origin,
            "destination_city": destination_city,
            "outbound_date": outbound_date,
            "return_date": return_date,
        },
        "dates": {
            "outbound_date": outbound_date,
            "return_date": return_date,
            "nights": max((date.fromisoformat(return_date) - date.fromisoformat(outbound_date)).days, 0),
        },
        "outbound_flight_count": outbound["count"],
        "return_flight_count": inbound["count"],
        "transport_options": options,
        "planning_notes": [
            "Transport search was done locally from database/transport/aero.json.",
            "Relative date phrases are resolved by the LLM after it calls get_current_date.",
            "Hotel, restaurant, attraction, and local POI candidates are available through search_pois.",
            "Use the selected arrival/departure times to constrain hotel-night and POI-opening-time searches.",
        ],
    }


def search_pois(
    query: str | None = None,
    category: str | None = None,
    district: str | None = None,
    price_level: str | None = None,
    open_at: str | None = None,
    max_results: int = 10,
) -> dict[str, Any]:
    pois = _load_pois()
    candidates = []

    for poi in pois:
        if category and poi.get("category") != category:
            continue
        if district and poi.get("district") != district:
            continue
        if price_level and poi.get("price_level") != price_level:
            continue
        if open_at and not _is_open_at(poi.get("opening_hours", ""), open_at):
            continue

        score = _poi_score(query or "", poi)
        if query and score < 0.6:
            continue
        candidates.append((_format_poi_candidate(poi, score), score))

    candidates.sort(
        key=lambda item: (
            -item[1],
            item[0]["price"],
            -item[0].get("rating", 0),
            item[0]["name"],
        )
    )
    return {
        "ok": True,
        "source": str(POI_PATH.relative_to(BASE_DIR)),
        "filters": {
            "query": query,
            "category": category,
            "district": district,
            "price_level": price_level,
            "open_at": open_at,
        },
        "count": len(candidates),
        "candidates": [candidate for candidate, _ in candidates[:max_results]],
    }


def fuzzy_search(
    query: str,
    kind: str | None = None,
    context: dict[str, Any] | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    candidates = _build_fuzzy_candidates()
    if kind:
        candidates = [candidate for candidate in candidates if candidate["kind"] == kind]

    scored = [_score_fuzzy_candidate(query, candidate, context) for candidate in candidates]
    scored.sort(key=lambda item: item["score"], reverse=True)
    top = scored[:top_k]

    if not top or top[0]["score"] < MIN_FUZZY_MATCH_SCORE:
        status = "no_match"
    elif len(top) > 1 and top[0]["score"] - top[1]["score"] < FUZZY_AMBIGUITY_DELTA:
        status = "ambiguous"
    else:
        status = "matched"

    literal = max(scored, key=lambda item: item["base_score"], default=None)
    contextual = top[0] if top else None
    context_champion = max(scored, key=lambda item: item["context_boost"], default=None)
    if (
        literal
        and contextual
        and literal["id"] != contextual["id"]
        and literal["base_score"] >= 0.86
        and contextual["score"] - literal["base_score"] >= FUZZY_CONTEXT_OVERRIDE_MARGIN
        and len(contextual["evidence"]) >= 2
    ):
        status = "context_override"
    elif (
        literal
        and context_champion
        and literal["id"] != context_champion["id"]
        and literal["base_score"] >= 0.95
        and context_champion["context_boost"] >= 0.42
        and len(context_champion["evidence"]) >= 2
    ):
        status = "context_override"

    return {
        "ok": True,
        "query": query,
        "kind": kind,
        "status": status,
        "top_match": top[0] if top else None,
        "candidates": top,
        "thresholds": {
            "min_match_score": MIN_FUZZY_MATCH_SCORE,
            "ambiguity_delta": FUZZY_AMBIGUITY_DELTA,
            "context_override_margin": FUZZY_CONTEXT_OVERRIDE_MARGIN,
        },
    }


def get_poi_details(poi_id: str) -> dict[str, Any]:
    poi = _poi_by_id(poi_id)
    if not poi:
        return {"ok": False, "error": f"No POI found for id: {poi_id}"}
    return {"ok": True, "poi": _format_poi_candidate(poi, score=1.0, include_raw=True)}


def get_replacement_pois(
    poi_id: str,
    trigger_event: str | None = None,
    max_results: int = 5,
) -> dict[str, Any]:
    poi = _poi_by_id(poi_id)
    if not poi:
        return {"ok": False, "error": f"No POI found for id: {poi_id}"}

    all_pois = {item["poi_id"]: item for item in _load_pois()}
    replacements = []
    for candidate_id in poi.get("replacement_candidates", []):
        candidate = all_pois.get(candidate_id)
        if not candidate:
            continue
        if not _passes_trigger(candidate, trigger_event):
            continue
        replacements.append(
            _format_poi_candidate(
                candidate,
                score=_replacement_score(poi, candidate, trigger_event),
            )
        )

    replacements.sort(key=lambda item: (-item["match_score"], item["price"], item["name"]))
    return {
        "ok": True,
        "request": {"poi_id": poi_id, "trigger_event": trigger_event},
        "original": _format_poi_candidate(poi, score=1.0),
        "count": len(replacements),
        "candidates": replacements[:max_results],
    }


def plan_trip_with_local_data(
    destination_city: str,
    outbound_date: str,
    return_date: str,
    origin_city: str | None = None,
    max_transport_options: int = 5,
    max_poi_candidates: int = 5,
) -> dict[str, Any]:
    transport = plan_trip_transport(
        destination_city=destination_city,
        outbound_date=outbound_date,
        return_date=return_date,
        origin_city=origin_city,
        max_options=max_transport_options,
    )
    hotels = search_pois(category="hotel", max_results=max_poi_candidates)
    restaurants = search_pois(category="restaurant", max_results=max_poi_candidates)
    activities = search_pois(category="attraction", max_results=max_poi_candidates)
    entertainment = search_pois(category="entertainment", max_results=max_poi_candidates)

    return {
        "ok": bool(transport.get("ok")),
        "request": {
            "origin_city": origin_city,
            "destination_city": destination_city,
            "outbound_date": outbound_date,
            "return_date": return_date,
        },
        "transport": transport,
        "local_data": {
            "hotels": hotels,
            "restaurants": restaurants,
            "activities": activities,
            "entertainment": entertainment,
        },
        "planning_notes": [
            "Local POI data is a small mock-city dataset and is not city-specific yet.",
            "Use item_id values from POI candidates directly in final JSON when selected.",
            "For categories not represented in the final output contract, map attraction/mall/resting_area to entertainment.",
        ],
    }


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments or {}
    tool_map = {
        "get_current_location": get_current_location,
        "get_current_date": get_current_date,
        "resolve_city_transport_nodes": resolve_city_transport_nodes,
        "search_flights": search_flights,
        "plan_trip_transport": plan_trip_transport,
        "search_pois": search_pois,
        "fuzzy_search": fuzzy_search,
        "get_poi_details": get_poi_details,
        "get_replacement_pois": get_replacement_pois,
        "plan_trip_with_local_data": plan_trip_with_local_data,
    }
    if name not in tool_map:
        return {"ok": False, "error": f"Unknown tool: {name}"}
    return tool_map[name](**arguments)


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _load_pois() -> list[dict[str, Any]]:
    if not POI_PATH.exists():
        return []
    data = _load_json(POI_PATH)
    return data if isinstance(data, list) else []


def _poi_by_id(poi_id: str) -> dict[str, Any] | None:
    normalized_id = poi_id.replace("poi:", "")
    for poi in _load_pois():
        if poi.get("poi_id") == normalized_id:
            return poi
    return None


def _normalize_text(value: str) -> str:
    value = value.strip().lower().replace("·", "")
    return re.sub(r"[\s\-_()（）/]+", "", value)


def _text_similarity(query: str, value: str) -> float:
    query_normalized = _normalize_text(query)
    value_normalized = _normalize_text(value)
    if not query_normalized or not value_normalized:
        return 0.0
    if query_normalized == value_normalized:
        return 1.0
    if query_normalized in value_normalized:
        return 0.95
    if value_normalized in query_normalized:
        return 0.9 if len(value_normalized) >= 4 else 0.7
    return SequenceMatcher(None, query_normalized, value_normalized).ratio()


def _char_bigrams(value: str) -> set[str]:
    text = _normalize_text(value)
    if len(text) <= 1:
        return {text} if text else set()
    return {text[index : index + 2] for index in range(len(text) - 1)}


def _fuzzy_similarity(query: str, value: str) -> float:
    base = _text_similarity(query, value)
    query_bigrams = _char_bigrams(query)
    value_bigrams = _char_bigrams(value)
    overlap = 0.0
    if query_bigrams and value_bigrams:
        overlap = len(query_bigrams & value_bigrams) / len(query_bigrams | value_bigrams)
    return max(base, overlap)


def _build_fuzzy_candidates() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    iata_data = _load_json(TRANSPORT_DIR / "iata_codes.json")

    cities: dict[str, list[dict[str, str]]] = {}
    for airport in iata_data["airports"]:
        cities.setdefault(airport["city"], []).append(airport)
        aliases = {
            airport["iata"],
            airport["name"],
            airport["city"],
            airport["country"],
            *CITY_ALIASES.get(airport["city"], []),
        }
        candidates.append(
            {
                "kind": "airport",
                "id": f"airport:{airport['iata']}",
                "label": f"{airport['name']} ({airport['iata']})",
                "aliases": sorted(alias for alias in aliases if alias),
                "metadata": airport,
            }
        )

    for city, airports in cities.items():
        aliases = {city, *CITY_ALIASES.get(city, [])}
        aliases.update(airport["iata"] for airport in airports)
        candidates.append(
            {
                "kind": "city",
                "id": f"city:{city}",
                "label": city,
                "aliases": sorted(alias for alias in aliases if alias),
                "metadata": {
                    "city": city,
                    "airport_codes": [airport["iata"] for airport in airports],
                    "country": airports[0]["country"],
                },
            }
        )

    for poi in _load_pois():
        category = poi.get("category", "")
        aliases = {
            poi.get("poi_id", ""),
            poi.get("poi_name", ""),
            poi.get("district", ""),
            category,
            poi.get("sub_category", ""),
            *poi.get("tags", []),
            *poi.get("suitable_for", []),
            *poi.get("recovery_tags", []),
            *CATEGORY_ALIASES.get(category, []),
        }
        candidates.append(
            {
                "kind": "poi",
                "id": f"poi:{poi['poi_id']}",
                "label": poi["poi_name"],
                "aliases": sorted(alias for alias in aliases if alias),
                "metadata": _format_poi_candidate(poi, score=1.0, include_raw=True),
            }
        )

    return candidates


def _context_score(candidate: dict[str, Any], context: dict[str, Any] | None) -> tuple[float, list[str]]:
    if not context:
        return 0.0, []

    score = 0.0
    evidence: list[str] = []

    def add_evidence(name: str, amount: float) -> None:
        nonlocal score
        score += amount
        evidence.append(name)

    metadata = candidate.get("metadata", {})
    city = metadata.get("city")
    if candidate["kind"] == "poi":
        raw = metadata.get("raw", {})
        district = raw.get("district") or metadata.get("district")
        category = raw.get("category") or metadata.get("category")
        if district and district == context.get("preferred_district"):
            add_evidence(f"preferred_district:{district}", 0.18)
        if category and category in set(context.get("preferred_categories", [])):
            add_evidence(f"preferred_category:{category}", 0.14)

    recent_destinations = context.get("recent_destinations", [])
    itinerary_cities = context.get("itinerary_cities", [])
    current_city = context.get("current_city")

    if city and city in recent_destinations:
        count = recent_destinations.count(city)
        add_evidence(f"recent_destinations:{city}x{count}", min(0.12 * count, 0.3))
    if city and city in itinerary_cities:
        add_evidence(f"itinerary_city:{city}", 0.24)
    if city and city == current_city:
        add_evidence(f"current_city:{city}", 0.08)

    return score, evidence


def _score_fuzzy_candidate(
    query: str,
    candidate: dict[str, Any],
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    alias_scores = [(alias, _fuzzy_similarity(query, alias)) for alias in candidate["aliases"]]
    best_alias, base_score = max(alias_scores, key=lambda item: item[1])
    boost, evidence = _context_score(candidate, context)
    final_score = min(base_score + boost, 1.0)
    return {
        "kind": candidate["kind"],
        "id": candidate["id"],
        "label": candidate["label"],
        "score": round(final_score, 4),
        "base_score": round(base_score, 4),
        "context_boost": round(boost, 4),
        "matched_alias": best_alias,
        "evidence": evidence,
        "metadata": candidate["metadata"],
    }


def _poi_score(query: str, poi: dict[str, Any]) -> float:
    if not query:
        return 0.5 + (float(poi.get("rating", 0)) / 10)
    fields = [
        poi.get("poi_id", ""),
        poi.get("poi_name", ""),
        poi.get("district", ""),
        poi.get("category", ""),
        poi.get("sub_category", ""),
        *poi.get("tags", []),
        *poi.get("suitable_for", []),
        *poi.get("recovery_tags", []),
    ]
    return max(_fuzzy_similarity(query, str(field)) for field in fields if field)


def _format_poi_candidate(
    poi: dict[str, Any],
    score: float,
    include_raw: bool = False,
) -> dict[str, Any]:
    category = poi.get("category", "entertainment")
    result = {
        "item_id": f"poi:{poi.get('poi_id')}",
        "poi_id": poi.get("poi_id"),
        "name": poi.get("poi_name"),
        "domain": POI_DOMAIN_MAP.get(category, "entertainment"),
        "category": category,
        "sub_category": poi.get("sub_category"),
        "district": poi.get("district"),
        "location": poi.get("district"),
        "price": _safe_float(poi.get("average_cost")),
        "price_level": poi.get("price_level"),
        "currency": "CNY",
        "opening_hours": poi.get("opening_hours"),
        "indoor_or_outdoor": poi.get("indoor_or_outdoor"),
        "stay_duration_minutes": _safe_int(poi.get("stay_duration_minutes")),
        "rating": _safe_float(poi.get("rating")),
        "booking_required": category in {"hotel", "restaurant", "entertainment"},
        "notes": _poi_notes(poi),
        "match_score": round(score, 4),
        "tags": poi.get("tags", []),
        "recovery_tags": poi.get("recovery_tags", []),
        "nearby_pois": poi.get("nearby_pois", []),
        "replacement_candidates": poi.get("replacement_candidates", []),
    }
    if include_raw:
        result["raw"] = poi
    return result


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _poi_notes(poi: dict[str, Any]) -> str:
    parts = [
        f"Category: {poi.get('category')}/{poi.get('sub_category')}",
        f"Hours: {poi.get('opening_hours')}",
        f"Average cost: CNY {poi.get('average_cost')}",
    ]
    tags = poi.get("tags", [])
    if tags:
        parts.append("Tags: " + ", ".join(tags[:4]))
    return "; ".join(part for part in parts if part)


def _is_open_at(opening_hours: str, target_time: str) -> bool:
    if not opening_hours or not target_time:
        return True
    if opening_hours.strip().lower() == "24h":
        return True
    match = re.match(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$", opening_hours.strip())
    target_match = re.match(r"^(\d{2}):(\d{2})$", target_time.strip())
    if not match or not target_match:
        return True

    start = int(match.group(1)) * 60 + int(match.group(2))
    end = int(match.group(3)) * 60 + int(match.group(4))
    target = int(target_match.group(1)) * 60 + int(target_match.group(2))
    if start <= end:
        return start <= target <= end
    return target >= start or target <= end


def _passes_trigger(poi: dict[str, Any], trigger_event: str | None) -> bool:
    if not trigger_event:
        return True
    trigger = trigger_event.strip().lower()
    tags = {tag.lower() for tag in poi.get("recovery_tags", [])}
    if trigger in {"rain", "rainy", "rainy_day"}:
        return poi.get("indoor_or_outdoor") != "outdoor" or "rainy_day_friendly" in tags
    if trigger in {"traffic", "traffic_delay"}:
        return "traffic_delay_friendly" in tags or "walkable" in tags
    if trigger in {"budget", "budget_change", "cheaper"}:
        return "budget_replacement" in tags
    return True


def _replacement_score(
    original: dict[str, Any],
    candidate: dict[str, Any],
    trigger_event: str | None,
) -> float:
    score = 0.4
    if candidate.get("district") == original.get("district"):
        score += 0.2
    if candidate.get("category") == original.get("category"):
        score += 0.15
    if candidate.get("price_level") == original.get("price_level"):
        score += 0.1
    if _passes_trigger(candidate, trigger_event):
        score += 0.15
    return min(score, 1.0)


def _airports_for_city(city: str) -> list[dict[str, str]]:
    city_normalized = city.strip().lower()
    data = _load_json(TRANSPORT_DIR / "iata_codes.json")
    return [
        airport
        for airport in data["airports"]
        if airport["city"].strip().lower() == city_normalized
    ]


def _runs_on_date(routine: str, trip_date: date) -> bool:
    routine = routine.strip().lower()
    if routine == "daily":
        return True
    if routine == "weekday":
        return trip_date.weekday() < 5
    if routine == "weekend":
        return trip_date.weekday() >= 5
    return False


def _schedule_to_datetimes(travel_date: str, schedule: list[str]) -> tuple[str, str]:
    departure_time, arrival_time = schedule
    departure = f"{travel_date}{departure_time}"
    arrival_date = travel_date
    if arrival_time < departure_time:
        arrival_date = (date.fromisoformat(travel_date) + timedelta(days=1)).isoformat()
    arrival = f"{arrival_date}{arrival_time}"
    return departure, arrival


def _duration_minutes(departure_at: str, arrival_at: str) -> int:
    departure = datetime.fromisoformat(departure_at.replace("Z", "+00:00"))
    arrival = datetime.fromisoformat(arrival_at.replace("Z", "+00:00"))
    return int((arrival - departure).total_seconds() / 60)


def _pair_flights(
    outbound_candidates: list[dict[str, Any]],
    return_candidates: list[dict[str, Any]],
    max_options: int,
) -> list[dict[str, Any]]:
    pairs = []
    for outbound in outbound_candidates:
        for inbound in return_candidates:
            total_price = outbound["price"] + inbound["price"]
            pairs.append(
                {
                    "option_id": f"{outbound['candidate_id']}__{inbound['candidate_id']}",
                    "outbound": outbound,
                    "return": inbound,
                    "total_transport_price": total_price,
                    "currency": outbound["currency"],
                    "destination_arrival_at": outbound["arrival_at"],
                    "destination_departure_at": inbound["departure_at"],
                }
            )
    pairs.sort(
        key=lambda item: (
            item["total_transport_price"],
            item["outbound"]["arrival_at"],
            -_sort_timestamp(item["return"]["departure_at"]),
        )
    )
    return pairs[:max_options]


def _sort_timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
