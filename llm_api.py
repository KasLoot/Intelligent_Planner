import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
BOOKINGS_FILE = BASE_DIR / "bookings.json"
CURRENT_LOCATION = "London, UK"
DEFAULT_MODEL = "gpt-5.4-nano"
DEFAULT_DEMO_START_DATE = "2026-06-05"
DEFAULT_DEMO_END_DATE = "2026-06-07"
GOOGLE_API_KEY_ENV = "GOOGLE_MAPS_API_KEY"
GOOGLE_TIMEOUT_SECONDS = 10


CUISINE_FAMILIES = {
    "european": {
        "british",
        "french",
        "greek",
        "italian",
        "mediterranean",
        "portuguese",
        "spanish",
    },
    "asian": {"chinese", "indian", "japanese", "korean", "thai", "vietnamese"},
}

DOMAIN_FILES = {
    "flight": "plane_tickets.json",
    "hotel": "hotels.json",
    "restaurant": "restaurants.json",
    "entertainment": "entertainment.json",
    "transport": "transport.json",
}


class JsonStore:
    def __init__(self, base_dir: Path = BASE_DIR):
        self.base_dir = base_dir
        self._cache: dict[str, list[dict[str, Any]]] = {}

    def load(self, filename: str) -> list[dict[str, Any]]:
        if filename not in self._cache:
            path = self.base_dir / filename
            if not path.exists() or path.stat().st_size == 0:
                self._cache[filename] = []
            else:
                with path.open(encoding="utf-8") as file:
                    data = json.load(file)
                if not isinstance(data, list):
                    raise ValueError(f"{filename} must contain a JSON list")
                self._cache[filename] = data
        return self._cache[filename]


STORE = JsonStore()


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def normalize_location(value: Any) -> str:
    text = normalize_text(value)
    return re.sub(r"\bway\b", "way", text)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_text(value)).strip("-")
    return slug or "item"


def item_id(domain: str, item: dict[str, Any]) -> str:
    if item.get("id"):
        return str(item["id"])
    name = item.get("name") or item.get("airline") or item.get("type") or domain
    return f"{domain}-{slugify(str(name))}"


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def clamp_limit(limit: Any) -> int:
    return max(1, min(to_int(limit, 5), 10))


def google_api_key() -> str | None:
    return os.getenv(GOOGLE_API_KEY_ENV)


def google_enabled() -> bool:
    return bool(google_api_key())


def request_json(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None
    request_headers = headers or {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers = {"Content-Type": "application/json", **request_headers}

    request = urllib.request.Request(
        url,
        data=data,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=GOOGLE_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Google API HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Google API request failed: {exc.reason}") from exc


def google_price_to_number(price_level: str | None) -> int | None:
    mapping = {
        "PRICE_LEVEL_FREE": 0,
        "PRICE_LEVEL_INEXPENSIVE": 1,
        "PRICE_LEVEL_MODERATE": 2,
        "PRICE_LEVEL_EXPENSIVE": 3,
        "PRICE_LEVEL_VERY_EXPENSIVE": 4,
    }
    return mapping.get(str(price_level or ""))


def compact_google_place(
    place: dict[str, Any],
    domain: str,
    score: float,
    match_reasons: list[str],
) -> dict[str, Any]:
    display_name = place.get("displayName", {}).get("text") or place.get("name") or "Google place"
    google_id = place.get("id") or place.get("name") or slugify(display_name)
    return {
        "id": f"google-{domain}-{google_id}",
        "name": display_name,
        "category": domain,
        "location": place.get("formattedAddress"),
        "price": None,
        "price_level": google_price_to_number(place.get("priceLevel")),
        "rating": place.get("rating"),
        "availability": place.get("regularOpeningHours", {}).get("weekdayDescriptions"),
        "booking_required": True,
        "score": round(score, 2),
        "match_reasons": match_reasons,
        "constraints_failed": [],
        "provider": "google",
        "google_maps_uri": place.get("googleMapsUri"),
        "website_uri": place.get("websiteUri"),
        "phone": place.get("nationalPhoneNumber"),
    }


def google_places_text_search(
    query: str,
    domain: str,
    limit: int = 5,
    min_rating: float | None = None,
) -> list[dict[str, Any]]:
    key = google_api_key()
    if not key:
        return []

    url = "https://places.googleapis.com/v1/places:searchText"
    payload: dict[str, Any] = {
        "textQuery": query,
        "maxResultCount": clamp_limit(limit),
    }
    if min_rating is not None:
        payload["minRating"] = float(min_rating)

    headers = {
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,places.location,"
            "places.rating,places.priceLevel,places.types,places.regularOpeningHours,"
            "places.googleMapsUri,places.websiteUri,places.nationalPhoneNumber"
        ),
    }
    data = request_json(url, method="POST", headers=headers, payload=payload)
    places = data.get("places", [])
    results = []
    for place in places[:clamp_limit(limit)]:
        score = to_float(place.get("rating")) * 10.0
        reasons = ["Google Places text search result", f"query: {query}"]
        results.append(compact_google_place(place, domain, score, reasons))
    return results


def google_geocode(address: str) -> dict[str, Any] | None:
    key = google_api_key()
    if not key or not address:
        return None

    params = urllib.parse.urlencode({"address": address, "key": key})
    url = f"https://maps.googleapis.com/maps/api/geocode/json?{params}"
    data = request_json(url)
    if data.get("status") != "OK" or not data.get("results"):
        return None
    result = data["results"][0]
    location = result.get("geometry", {}).get("location", {})
    return {
        "formatted_address": result.get("formatted_address"),
        "lat": location.get("lat"),
        "lng": location.get("lng"),
        "place_id": result.get("place_id"),
        "provider": "google",
    }


def google_directions(
    origin: str,
    destination: str,
    mode: str = "transit",
) -> list[dict[str, Any]]:
    key = google_api_key()
    if not key or not origin or not destination:
        return []

    params = urllib.parse.urlencode(
        {
            "origin": origin,
            "destination": destination,
            "mode": mode,
            "key": key,
        }
    )
    url = f"https://maps.googleapis.com/maps/api/directions/json?{params}"
    data = request_json(url)
    if data.get("status") != "OK":
        return []

    results = []
    for index, route in enumerate(data.get("routes", [])[:3]):
        leg = route.get("legs", [{}])[0]
        name = route.get("summary") or f"{mode.title()} route"
        results.append(
            {
                "id": f"google-transport-route-{index + 1}",
                "name": name,
                "category": mode,
                "location": f"{leg.get('start_address')} to {leg.get('end_address')}",
                "price": None,
                "rating": None,
                "availability": {
                    "duration": leg.get("duration", {}).get("text"),
                    "distance": leg.get("distance", {}).get("text"),
                    "departure_time": leg.get("departure_time", {}).get("text"),
                    "arrival_time": leg.get("arrival_time", {}).get("text"),
                },
                "booking_required": False,
                "score": 80.0 - index,
                "match_reasons": ["Google Directions route", f"mode: {mode}"],
                "constraints_failed": [],
                "provider": "google",
            }
        )
    return results


def location_score(candidate: str | None, query: str | None) -> tuple[float, str | None]:
    if not query:
        return 0.0, None

    candidate_norm = normalize_location(candidate)
    query_norm = normalize_location(query)
    if not candidate_norm:
        return -20.0, "missing location"
    if candidate_norm == query_norm:
        return 30.0, "same location"

    candidate_parts = set(candidate_norm.split())
    query_parts = set(query_norm.split())
    shared = candidate_parts & query_parts
    if shared:
        if "silicon" in shared and "way" in shared:
            return 24.0, "near current Silicon Way location"
        return 10.0, f"shares location terms: {', '.join(sorted(shared))}"

    return -8.0, "different location"


def date_matches(value: str | None, requested_date: str | None) -> bool:
    if not requested_date or not value:
        return True
    return value.startswith(requested_date)


def inventory_has_date(items: list[dict[str, Any]], field: str, requested_date: str | None) -> bool:
    if not requested_date:
        return False
    return any(date_matches(str(item.get(field, "")), requested_date) for item in items)


def inventory_has_availability_date(
    items: list[dict[str, Any]],
    field: str,
    requested_date: str | None,
) -> bool:
    if not requested_date:
        return False
    return any(
        any(str(slot).startswith(requested_date) for slot in item.get(field, []))
        for item in items
    )


def inventory_has_slot_date(items: list[dict[str, Any]], requested_date: str | None) -> bool:
    if not requested_date:
        return False
    return any(
        any(str(slot[0]).startswith(requested_date) for slot in item.get("time_slots", []))
        for item in items
    )


def slot_matches(
    slots: list[list[str]] | None,
    requested_date: str | None,
    requested_time: str | None,
    strict: bool,
) -> tuple[bool, str | None]:
    if not requested_date and not requested_time:
        return True, None
    if not slots:
        return not strict, "no time slots listed"

    for start, end in slots:
        if requested_date and not start.startswith(requested_date):
            continue
        if not requested_time:
            return True, "has a matching date slot"
        start_time = start[11:16]
        end_time = end[11:16]
        if start_time <= requested_time <= end_time:
            return True, f"covers {requested_time}"

    return not strict, "no exact slot match"


def cuisine_matches(cuisine: str, query: str | None) -> tuple[bool, str | None]:
    if not query:
        return True, None

    cuisine_norm = normalize_text(cuisine)
    query_norm = normalize_text(query)
    if cuisine_norm == query_norm or query_norm in cuisine_norm:
        return True, f"{cuisine} matches {query}"

    family = CUISINE_FAMILIES.get(query_norm, set())
    if cuisine_norm in family:
        return True, f"{cuisine} is treated as {query}"

    return False, f"{cuisine} is not {query}"


def compact_result(
    domain: str,
    item: dict[str, Any],
    score: float,
    match_reasons: list[str],
    constraints_failed: list[str],
) -> dict[str, Any]:
    name = item.get("name") or item.get("airline") or item.get("type") or item_id(domain, item)
    category = (
        item.get("category")
        or item.get("cuisine")
        or item.get("type")
        or domain
    )
    availability = (
        item.get("availability")
        or item.get("time_slots")
        or item.get("seats_available")
        or item.get("rooms_available")
        or item.get("tickets_available")
        or item.get("vehicles_available")
    )
    booking_value = item.get("booking_required", item.get("booking"))
    booking_required = booking_value in (True, "required", "yes")

    return {
        "id": item_id(domain, item),
        "name": name,
        "category": category,
        "location": item.get("location") or item.get("destination") or item.get("pickup_location"),
        "price": item.get("price"),
        "rating": item.get("rating", item.get("ratings")),
        "availability": availability,
        "booking_required": booking_required,
        "score": round(score, 2),
        "match_reasons": match_reasons,
        "constraints_failed": constraints_failed,
    }


def sorted_top_results(
    domain: str,
    scored_items: list[tuple[dict[str, Any], float, list[str], list[str]]],
    limit: int,
) -> list[dict[str, Any]]:
    valid_items = [row for row in scored_items if not row[3]]
    valid_items.sort(key=lambda row: row[1], reverse=True)
    return [compact_result(domain, *row) for row in valid_items[:clamp_limit(limit)]]


def search_restaurants(
    cuisine_query: str | None = None,
    location: str | None = None,
    date: str | None = None,
    time: str | None = None,
    party_size: int | None = None,
    min_rating: float | None = None,
    booking_preference: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if google_enabled():
        query_parts = [cuisine_query or "restaurants"]
        if cuisine_query and "restaurant" not in normalize_text(cuisine_query):
            query_parts.append("restaurants")
        if location:
            query_parts.append(f"near {location}")
        query = " ".join(query_parts)
        google_results = google_places_text_search(
            query=query,
            domain="restaurant",
            limit=limit,
            min_rating=min_rating,
        )
        if google_results:
            if date or time or party_size or booking_preference:
                for result in google_results:
                    result["match_reasons"].append(
                        "live place result; exact reservation availability must be confirmed before booking"
                    )
            return google_results

    restaurants = STORE.load(DOMAIN_FILES["restaurant"])
    scored: list[tuple[dict[str, Any], float, list[str], list[str]]] = []
    strict_time = bool(time or booking_preference in {"available", "required"})
    has_requested_slot_date = inventory_has_slot_date(restaurants, date)

    for restaurant in restaurants:
        score = 0.0
        reasons: list[str] = []
        failed: list[str] = []

        cuisine_ok, cuisine_reason = cuisine_matches(str(restaurant.get("cuisine", "")), cuisine_query)
        if cuisine_ok:
            score += 35.0
            if cuisine_reason:
                reasons.append(cuisine_reason)
        else:
            failed.append(cuisine_reason or "cuisine mismatch")

        rating = to_float(restaurant.get("ratings"))
        if min_rating is not None and rating < float(min_rating):
            failed.append(f"rating {rating} below requested {min_rating}")
        else:
            score += rating * 6.0

        loc_score, loc_reason = location_score(restaurant.get("location"), location)
        score += loc_score
        if loc_reason and loc_score >= 0:
            reasons.append(loc_reason)
        elif loc_reason:
            failed.append(loc_reason)

        booking = normalize_text(restaurant.get("booking"))
        if booking_preference:
            preference = normalize_text(booking_preference)
            if preference == "available" and booking not in {"available", "no"}:
                failed.append(f"booking is {booking}, not available")
            elif preference == "required" and booking != "required":
                failed.append(f"booking is {booking}, not required")
            elif preference == "no" and booking != "no":
                failed.append(f"booking is {booking}, not no")
        elif booking:
            reasons.append(f"booking {booking}")

        if date and not has_requested_slot_date:
            score -= 3.0
            reasons.append(f"no exact mock restaurant slot for {date}; showing available inventory")
        else:
            slots_ok, slot_reason = slot_matches(restaurant.get("time_slots"), date, time, strict_time)
            if not slots_ok:
                failed.append(slot_reason or "time slot mismatch")
            elif slot_reason:
                score += 8.0
                reasons.append(slot_reason)

        if party_size:
            reasons.append(f"party size {party_size} noted")

        scored.append((restaurant, score, reasons, failed))

    return sorted_top_results("restaurant", scored, limit)


def search_flights(
    origin: str | None = None,
    destination: str | None = None,
    departure_date: str | None = None,
    return_date: str | None = None,
    traveler_count: int = 1,
    max_price: float | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    flights = STORE.load(DOMAIN_FILES["flight"])
    scored: list[tuple[dict[str, Any], float, list[str], list[str]]] = []
    has_requested_departure = inventory_has_date(flights, "departure_time", departure_date)
    has_requested_return = inventory_has_date(flights, "return_time", return_date)

    for flight in flights:
        score = 20.0
        reasons: list[str] = []
        failed: list[str] = []

        if origin and normalize_text(origin) not in normalize_text(flight.get("origin")):
            failed.append("origin mismatch")
        else:
            score += 20.0
            if origin:
                reasons.append("origin matches")

        if destination and normalize_text(destination) not in normalize_text(flight.get("destination")):
            failed.append("destination mismatch")
        else:
            score += 25.0
            if destination:
                reasons.append("destination matches")

        if departure_date and not has_requested_departure:
            score -= 5.0
            reasons.append(f"no exact mock flight for {departure_date}; showing available inventory")
        elif not date_matches(flight.get("departure_time"), departure_date):
            failed.append("departure date mismatch")
        elif departure_date:
            score += 15.0
            reasons.append("departure date matches")

        if return_date and not has_requested_return:
            score -= 3.0
            reasons.append(f"no exact mock return for {return_date}; showing available inventory")
        elif return_date and flight.get("return_time") and not date_matches(flight.get("return_time"), return_date):
            failed.append("return date mismatch")

        seats = to_int(flight.get("seats_available"))
        if seats < traveler_count:
            failed.append(f"only {seats} seats available")
        else:
            score += min(seats, 10)

        price = to_float(flight.get("price"))
        if max_price is not None and price > float(max_price):
            failed.append(f"price {price} above {max_price}")
        else:
            score += max(0.0, 20.0 - price / 100.0)

        scored.append((flight, score, reasons, failed))

    return sorted_top_results("flight", scored, limit)


def search_hotels(
    destination: str | None = None,
    check_in: str | None = None,
    check_out: str | None = None,
    guests: int = 1,
    max_price: float | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    hotels = STORE.load(DOMAIN_FILES["hotel"])
    scored: list[tuple[dict[str, Any], float, list[str], list[str]]] = []

    for hotel in hotels:
        score = to_float(hotel.get("rating")) * 8.0
        reasons: list[str] = []
        failed: list[str] = []

        loc_score, loc_reason = location_score(hotel.get("location"), destination)
        score += loc_score
        if loc_score >= 0 and loc_reason:
            reasons.append(loc_reason)
        elif loc_reason:
            failed.append("destination mismatch")

        rooms = to_int(hotel.get("rooms_available"))
        if rooms <= 0:
            failed.append("no rooms available")
        else:
            score += min(rooms, 10)

        capacity = to_int(hotel.get("guest_capacity"), guests)
        if capacity < guests:
            failed.append(f"capacity {capacity} below {guests} guests")

        price = to_float(hotel.get("price"))
        if max_price is not None and price > float(max_price):
            failed.append(f"price {price} above {max_price}")
        else:
            score += max(0.0, 15.0 - price / 50.0)

        if check_in:
            reasons.append(f"check-in requested {check_in}")
        if check_out:
            reasons.append(f"check-out requested {check_out}")

        scored.append((hotel, score, reasons, failed))

    return sorted_top_results("hotel", scored, limit)


def search_entertainment(
    destination: str | None = None,
    date: str | None = None,
    category_query: str | None = None,
    party_size: int = 1,
    max_price: float | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if google_enabled():
        query_parts = [category_query or "things to do"]
        if destination:
            query_parts.append(f"in {destination}")
        google_results = google_places_text_search(
            query=" ".join(query_parts),
            domain="entertainment",
            limit=limit,
        )
        if google_results:
            if date or party_size:
                for result in google_results:
                    result["match_reasons"].append(
                        "live place result; ticket availability must be confirmed before booking"
                    )
            return google_results

    events = STORE.load(DOMAIN_FILES["entertainment"])
    scored: list[tuple[dict[str, Any], float, list[str], list[str]]] = []
    has_requested_date = inventory_has_date(events, "date_time", date)

    for event in events:
        score = to_float(event.get("rating")) * 8.0
        reasons: list[str] = []
        failed: list[str] = []

        loc_score, loc_reason = location_score(event.get("location"), destination)
        score += loc_score
        if loc_score >= 0 and loc_reason:
            reasons.append(loc_reason)
        elif loc_reason:
            failed.append("destination mismatch")

        if category_query and normalize_text(category_query) not in normalize_text(event.get("category")):
            failed.append("category mismatch")
        elif category_query:
            score += 20.0
            reasons.append("category matches")

        if date and not has_requested_date:
            score -= 4.0
            reasons.append(f"no exact mock event for {date}; showing available inventory")
        elif not date_matches(event.get("date_time"), date):
            failed.append("date mismatch")
        elif date:
            score += 15.0
            reasons.append("date matches")

        tickets = to_int(event.get("tickets_available"))
        if tickets < party_size:
            failed.append(f"only {tickets} tickets available")

        price = to_float(event.get("price"))
        if max_price is not None and price > float(max_price):
            failed.append(f"price {price} above {max_price}")
        else:
            score += max(0.0, 12.0 - price / 25.0)

        scored.append((event, score, reasons, failed))

    return sorted_top_results("entertainment", scored, limit)


def search_transport(
    location: str | None = None,
    origin: str | None = None,
    destination: str | None = None,
    date: str | None = None,
    category_query: str | None = None,
    mode: str = "transit",
    passengers: int = 1,
    max_price: float | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if google_enabled() and (origin or location) and destination:
        google_results = google_directions(
            origin=origin or location or CURRENT_LOCATION,
            destination=destination,
            mode=mode or "transit",
        )
        if google_results:
            return google_results[:clamp_limit(limit)]

    options = STORE.load(DOMAIN_FILES["transport"])
    scored: list[tuple[dict[str, Any], float, list[str], list[str]]] = []
    has_requested_date = inventory_has_availability_date(options, "availability", date)

    for option in options:
        score = to_float(option.get("rating")) * 8.0
        reasons: list[str] = []
        failed: list[str] = []

        loc_score, loc_reason = location_score(option.get("pickup_location"), location)
        score += loc_score
        if loc_score >= 0 and loc_reason:
            reasons.append(loc_reason)
        elif loc_reason:
            failed.append("pickup location mismatch")

        if category_query and normalize_text(category_query) not in normalize_text(option.get("type")):
            failed.append("transport type mismatch")
        elif category_query:
            score += 20.0
            reasons.append("transport type matches")

        if date and not has_requested_date:
            score -= 4.0
            reasons.append(f"no exact mock transport for {date}; showing available inventory")
        elif date and not any(str(slot).startswith(date) for slot in option.get("availability", [])):
            failed.append("date mismatch")
        elif date:
            score += 10.0
            reasons.append("date matches")

        capacity = to_int(option.get("capacity"))
        if capacity < passengers:
            failed.append(f"capacity {capacity} below {passengers} passengers")

        price = to_float(option.get("price"))
        if max_price is not None and price > float(max_price):
            failed.append(f"price {price} above {max_price}")
        else:
            score += max(0.0, 10.0 - price / 20.0)

        scored.append((option, score, reasons, failed))

    return sorted_top_results("transport", scored, limit)


def create_itinerary(
    trip_summary: str,
    days: list[dict[str, Any]] | None = None,
    selected_items: list[dict[str, Any]] | None = None,
    alternatives: list[dict[str, Any]] | None = None,
    estimated_total: float | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "trip_summary": trip_summary,
        "days": days or [],
        "selected_items": selected_items or [],
        "alternatives": alternatives or [],
        "estimated_total": estimated_total,
        "warnings": warnings or [],
        "confirmation_required": True,
    }


def explicit_confirmation_received(confirmation_text: str | None) -> bool:
    text = normalize_text(confirmation_text)
    if not text:
        return False
    return bool(re.search(r"\b(confirm|confirmed|book it|book these|yes|go ahead|reserve)\b", text))


def confirm_booking(
    selected_items: list[dict[str, Any]],
    traveler_count: int = 1,
    confirmation_text: str | None = None,
    ledger_path: Path = BOOKINGS_FILE,
) -> dict[str, Any]:
    if not explicit_confirmation_received(confirmation_text):
        return {
            "status": "confirmation_required",
            "message": "No booking was written. Ask the user to explicitly confirm before booking.",
            "bookings": [],
        }

    existing: list[dict[str, Any]]
    if ledger_path.exists() and ledger_path.stat().st_size > 0:
        with ledger_path.open(encoding="utf-8") as file:
            existing = json.load(file)
    else:
        existing = []

    created_at = datetime.now(timezone.utc).isoformat()
    new_bookings = []
    for selected in selected_items:
        domain = selected.get("domain") or selected.get("category") or "unknown"
        record = {
            "booking_id": f"bk_{uuid.uuid4().hex[:12]}",
            "domain": domain,
            "item_id": selected.get("item_id") or selected.get("id"),
            "status": "confirmed",
            "traveler_count": traveler_count,
            "date_time": selected.get("date_time") or selected.get("time"),
            "price": selected.get("price"),
            "provider_reference": f"MOCK-{uuid.uuid4().hex[:8].upper()}",
            "created_at": created_at,
        }
        new_bookings.append(record)

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("w", encoding="utf-8") as file:
        json.dump(existing + new_bookings, file, indent=2)

    return {"status": "confirmed", "bookings": new_bookings}


def get_current_location() -> dict[str, str]:
    result = {"location": CURRENT_LOCATION, "provider": "env"}
    geocoded = google_geocode(CURRENT_LOCATION)
    if geocoded:
        result.update(geocoded)
    return result


TOOLS = [
    {
        "type": "function",
        "name": "get_current_location",
        "description": "Get the user's current location.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "search_restaurants",
        "description": "Search restaurant candidates. Use broad intent fields; do not invent hard filters.",
        "parameters": {
            "type": "object",
            "properties": {
                "cuisine_query": {"type": "string"},
                "location": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD when explicitly relevant."},
                "time": {"type": "string", "description": "HH:MM when explicitly relevant."},
                "party_size": {"type": "integer"},
                "min_rating": {"type": "number"},
                "booking_preference": {"type": "string", "enum": ["available", "required", "no"]},
                "limit": {"type": "integer", "default": 5},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "search_flights",
        "description": "Search flight candidates from local mock inventory.",
        "parameters": {
            "type": "object",
            "properties": {
                "origin": {"type": "string"},
                "destination": {"type": "string"},
                "departure_date": {"type": "string"},
                "return_date": {"type": "string"},
                "traveler_count": {"type": "integer", "default": 1},
                "max_price": {"type": "number"},
                "limit": {"type": "integer", "default": 5},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "search_hotels",
        "description": "Search accommodation candidates from local mock inventory.",
        "parameters": {
            "type": "object",
            "properties": {
                "destination": {"type": "string"},
                "check_in": {"type": "string"},
                "check_out": {"type": "string"},
                "guests": {"type": "integer", "default": 1},
                "max_price": {"type": "number"},
                "limit": {"type": "integer", "default": 5},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "search_entertainment",
        "description": "Search activities and entertainment from local mock inventory.",
        "parameters": {
            "type": "object",
            "properties": {
                "destination": {"type": "string"},
                "date": {"type": "string"},
                "category_query": {"type": "string"},
                "party_size": {"type": "integer", "default": 1},
                "max_price": {"type": "number"},
                "limit": {"type": "integer", "default": 5},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "search_transport",
        "description": "Search local transport options from local mock inventory.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "origin": {"type": "string"},
                "destination": {"type": "string"},
                "date": {"type": "string"},
                "category_query": {"type": "string"},
                "mode": {"type": "string", "enum": ["driving", "walking", "transit", "bicycling"]},
                "passengers": {"type": "integer", "default": 1},
                "max_price": {"type": "number"},
                "limit": {"type": "integer", "default": 5},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "create_itinerary",
        "description": "Create a structured itinerary from selected candidates. It always requires confirmation before booking.",
        "parameters": {
            "type": "object",
            "properties": {
                "trip_summary": {"type": "string"},
                "days": {"type": "array", "items": {"type": "object"}},
                "selected_items": {"type": "array", "items": {"type": "object"}},
                "alternatives": {"type": "array", "items": {"type": "object"}},
                "estimated_total": {"type": "number"},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["trip_summary"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "confirm_booking",
        "description": "Write confirmed bookings to bookings.json. Call only after explicit user confirmation; pass the user's exact confirmation text.",
        "parameters": {
            "type": "object",
            "properties": {
                "selected_items": {"type": "array", "items": {"type": "object"}},
                "traveler_count": {"type": "integer", "default": 1},
                "confirmation_text": {"type": "string"},
            },
            "required": ["selected_items", "confirmation_text"],
            "additionalProperties": False,
        },
    },
]


TOOL_FUNCTIONS = {
    "get_current_location": get_current_location,
    "search_restaurants": search_restaurants,
    "search_flights": search_flights,
    "search_hotels": search_hotels,
    "search_entertainment": search_entertainment,
    "search_transport": search_transport,
    "create_itinerary": create_itinerary,
    "confirm_booking": confirm_booking,
}


SYSTEM_PROMPT = f"""
You are a holiday planning agent. Use tools to retrieve bounded candidate lists; never assume the full inventory is in the prompt.
Use deterministic search tools for facts, availability, prices, and IDs. Assemble a ranked day-by-day itinerary from returned candidates.

Prototype defaults:
- If the user asks for a weekend or holiday but does not provide exact dates, use {DEFAULT_DEMO_START_DATE} to {DEFAULT_DEMO_END_DATE}. Do not stop just to ask for dates.
- Use the departing location provided by the user. If none is provided, call get_current_location and use that as the departure location.
- If mock inventory has no exact date match, use the candidates returned by the tools and clearly list the date assumption or fallback in warnings.
- For restaurant recommendation requests, do not require booking status or exact time unless the user explicitly asks for availability at a specific time.
- When Google Maps Platform is configured, restaurant and entertainment tools can return live Google Places results, and transport can return live Google Directions routes.
- Google-backed place results are real place candidates, but booking or ticket availability still must be confirmed before calling confirm_booking.
- Flights and hotels may still be mock inventory until a real flight/hotel provider is added; clearly state that limitation in warnings.
- Do not say a category has no candidates if a tool returned candidates or fallback candidates. Use the returned candidates and explain any fallback reason from match_reasons.

Booking safety:
- Do not call confirm_booking until the user has explicitly confirmed the proposed itinerary.
- Before confirmation, explain the plan and ask for approval.

Final response contract:
- Always output two sections in this exact order: PLAN_TEXT and PLAN_JSON.
- PLAN_TEXT is a concise human-readable itinerary with assumptions, selected options, alternatives, estimated total, and a confirmation question.
- PLAN_JSON must be a valid JSON object in a fenced ```json block. It must use this shape:
  {{
    "trip_summary": "string",
    "assumptions": ["string"],
    "days": [
      {{
        "date": "YYYY-MM-DD",
        "title": "string",
        "items": [
          {{
            "time": "HH:MM or null",
            "domain": "flight|hotel|restaurant|entertainment|transport",
            "item_id": "string",
            "name": "string",
            "location": "string or null",
            "price": 0,
            "booking_required": true,
            "notes": "string"
          }}
        ]
      }}
    ],
    "selected_items": [
      {{
        "domain": "flight|hotel|restaurant|entertainment|transport",
        "item_id": "string",
        "name": "string",
        "date_time": "ISO datetime or null",
        "price": 0
      }}
    ],
    "alternatives": [],
    "estimated_total": 0,
    "warnings": ["string"],
    "confirmation_required": true
  }}
- The JSON must be parseable by a frontend without comments or trailing commas.
"""


def dispatch_tool(name: str, arguments: str) -> Any:
    function = TOOL_FUNCTIONS[name]
    kwargs = json.loads(arguments or "{}")
    return function(**kwargs)


def run_agent(user_message: str, model: str = DEFAULT_MODEL, max_turns: int = 8) -> str:
    from openai import OpenAI

    client = OpenAI()
    input_list: list[Any] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    response = client.responses.create(model=model, tools=TOOLS, input=input_list)
    for _ in range(max_turns):
        input_list += response.output
        function_calls = [item for item in response.output if item.type == "function_call"]
        if not function_calls:
            return response.output_text

        for item in function_calls:
            output = dispatch_tool(item.name, item.arguments)
            input_list.append(
                {
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": json.dumps(output),
                }
            )

        response = client.responses.create(model=model, tools=TOOLS, input=input_list)

    return response.output_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the holiday planning prototype.")
    parser.add_argument(
        "message",
        nargs="?",
        default="Plan a weekend holiday to Paris with my family, including flights, hotel, sightseeing, and restaurants.",
    )
    parser.add_argument(
        "--from-location",
        dest="from_location",
        help="Override CURRENT_LOCATION for this run when the prompt omits a departure location.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    message = args.message
    if args.from_location:
        message = f"Departing location: {args.from_location}. {message}"
    print(run_agent(message, model=args.model))


if __name__ == "__main__":
    main()
