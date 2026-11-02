from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

#-------------------------------------------------------------
# Google Maps API endpoints and API key
#-------------------------------------------------------------
TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
NEARBY_SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"
GEOLOCATION_URL = "https://www.googleapis.com/geolocation/v1/geolocate"
GEOCODE_ADDRESS_URL = "https://geocode.googleapis.com/v4/geocode/address"
TIMEZONE_URL = "https://maps.googleapis.com/maps/api/timezone/json"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


SEARCH_FIELD_MASK = (
    "places.displayName,"
    "places.formattedAddress,"
    "places.location,"
    "places.priceLevel,"
    "places.priceRange,"
    "places.rating,"
    "places.regularOpeningHours,"
    "places.regularSecondaryOpeningHours,"
    "places.internationalPhoneNumber,"
    "places.nationalPhoneNumber,"
    "places.currentOpeningHours,"
    "places.currentSecondaryOpeningHours"
)
ROUTES_FIELD_MASK = (
    "routes.duration,"
    "routes.distanceMeters,"
    "routes.legs.steps.travelMode,"
    "routes.legs.steps.transitDetails.headsign,"
    "routes.legs.steps.transitDetails.stopCount,"
    "routes.legs.steps.transitDetails.stopDetails.departureStop.name,"
    "routes.legs.steps.transitDetails.stopDetails.departureTime,"
    "routes.legs.steps.transitDetails.stopDetails.arrivalStop.name,"
    "routes.legs.steps.transitDetails.stopDetails.arrivalTime,"
    "routes.legs.steps.transitDetails.localizedValues.departureTime,"
    "routes.legs.steps.transitDetails.localizedValues.arrivalTime,"
    "routes.legs.steps.transitDetails.transitLine.name,"
    "routes.legs.steps.transitDetails.transitLine.nameShort,"
    "routes.legs.steps.transitDetails.transitLine.vehicle.name,"
    "routes.legs.steps.transitDetails.transitLine.vehicle.type"
)
PRICE_LEVEL_LABELS = {
    "PRICE_LEVEL_FREE": "free",
    "PRICE_LEVEL_INEXPENSIVE": "inexpensive",
    "PRICE_LEVEL_MODERATE": "moderate",
    "PRICE_LEVEL_EXPENSIVE": "expensive",
    "PRICE_LEVEL_VERY_EXPENSIVE": "very expensive",
}


def _google_maps_api_key() -> str:
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Set GOOGLE_MAPS_API_KEY before calling Google Maps tools.")
    return key


def search_by_text(text_query: str) -> dict:
    payload = {"textQuery": text_query}
    response = requests.post(
        TEXT_SEARCH_URL,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": _google_maps_api_key(),
            "X-Goog-FieldMask": SEARCH_FIELD_MASK,
        },
        timeout=30,
    )
    response.raise_for_status()
    return _add_place_price_helpers(response.json())


def search_nearby(
    included_types: list[str],
    latitude: float,
    longitude: float,
    radius: float = 500.0,
    max_result_count: int = 10,
) -> dict:
    payload = {
        "includedTypes": included_types,
        "maxResultCount": max_result_count,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "radius": radius,
            }
        },
    }
    response = requests.post(
        NEARBY_SEARCH_URL,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": _google_maps_api_key(),
            "X-Goog-FieldMask": SEARCH_FIELD_MASK,
        },
        timeout=30,
    )
    response.raise_for_status()
    return _add_place_price_helpers(response.json())


def _money_amount(money: dict | None) -> float | None:
    if not money:
        return None

    units = float(money.get("units", 0) or 0)
    nanos = float(money.get("nanos", 0) or 0) / 1_000_000_000
    return units + nanos


def _format_amount(amount: float) -> str:
    return str(int(amount)) if amount.is_integer() else f"{amount:.2f}".rstrip("0").rstrip(".")


def _add_place_price_helpers(result: dict) -> dict:
    for place in result.get("places", []):
        price_range = place.get("priceRange")
        price_level = place.get("priceLevel")

        if price_range:
            start_price = price_range.get("startPrice", {})
            end_price = price_range.get("endPrice", {})
            start_amount = _money_amount(start_price)
            end_amount = _money_amount(end_price)
            currency = start_price.get("currencyCode") or end_price.get("currencyCode")

            if start_amount is not None and end_amount is not None and currency:
                place["priceAmount"] = round((start_amount + end_amount) / 2, 2)
                place["priceCurrency"] = currency
                place["priceDescription"] = (
                    f"{currency} {_format_amount(start_amount)}-{_format_amount(end_amount)} "
                    "from Google Places priceRange"
                )
                continue

        if price_level:
            label = PRICE_LEVEL_LABELS.get(price_level, price_level)
            place["priceDescription"] = f"Google Places price level: {label}"

    return result


def get_current_location() -> dict:
    payload = {
        "homeMobileCountryCode": 310,
        "homeMobileNetworkCode": 410,
        "radioType": "gsm",
        "carrier": "Vodafone",
        "considerIp": True,
    }
    response = requests.post(
        GEOLOCATION_URL,
        params={"key": _google_maps_api_key()},
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_lat_lng_from_address(address: str) -> dict:
    encoded_address = quote(address, safe="")
    response = requests.get(
        f"{GEOCODE_ADDRESS_URL}/{encoded_address}",
        headers={"X-Goog-Api-Key": _google_maps_api_key()},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_time_zone(latitude: float, longitude: float, timestamp: int) -> dict:
    response = requests.get(
        TIMEZONE_URL,
        params={
            "location": f"{latitude},{longitude}",
            "timestamp": timestamp,
            "key": _google_maps_api_key(),
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_current_datetime_for_location(latitude: float, longitude: float) -> dict:
    timestamp = int(datetime.now(timezone.utc).timestamp())
    timezone_result = get_time_zone(latitude, longitude, timestamp)
    if timezone_result.get("status") != "OK":
        return {
            "ok": False,
            "timestamp": timestamp,
            "location": {
                "latitude": latitude,
                "longitude": longitude,
            },
        }

    utc_now = datetime.fromtimestamp(timestamp, timezone.utc)
    time_zone_id = timezone_result["timeZoneId"]

    try:
        local_now = utc_now.astimezone(ZoneInfo(time_zone_id))
    except ZoneInfoNotFoundError:
        offset_seconds = timezone_result.get("rawOffset", 0) + timezone_result.get("dstOffset", 0)
        fallback_timezone = timezone(timedelta(seconds=offset_seconds), time_zone_id)
        local_now = utc_now.astimezone(fallback_timezone)

    return {
        "ok": True,
        "timestamp": timestamp,
        "current_date": local_now.date().isoformat(),
        "current_time": local_now.time().replace(microsecond=0).isoformat(),
        "current_datetime": local_now.replace(microsecond=0).isoformat(),
        "timezone": timezone_result["timeZoneId"],
        "timezone_name": timezone_result.get("timeZoneName"),
        "location": {
            "latitude": latitude,
            "longitude": longitude,
        },
    }


def compute_route(
    origin: str | dict,
    destination: str | dict,
    location_input_type: str,
    travel_mode: str,
    routing_preference: str | None = "TRAFFIC_AWARE",
    compute_alternative_routes: bool = False,
    avoid_tolls: bool = False,
    avoid_highways: bool = False,
    avoid_ferries: bool = False,
    language_code: str = "en-US",
    units: str = "METRIC",
    departure_time: str | None = None,
    arrival_time: str | None = None,
) -> dict:
    travel_mode = travel_mode.upper()
    if travel_mode not in {"DRIVE", "WALK", "TRANSIT"}:
        raise ValueError("travel_mode must be either 'DRIVE', 'WALK', or 'TRANSIT'")
    if departure_time and arrival_time:
        raise ValueError("Provide either departure_time or arrival_time, not both")

    origin_location = _build_route_location(origin, location_input_type)
    destination_location = _build_route_location(destination, location_input_type)

    payload = {
        "origin": origin_location,
        "destination": destination_location,
        "travelMode": travel_mode,
        "computeAlternativeRoutes": compute_alternative_routes,
        "routeModifiers": {
            "avoidTolls": avoid_tolls,
            "avoidHighways": avoid_highways,
            "avoidFerries": avoid_ferries,
        },
        "languageCode": language_code,
        "units": units,
    }
    if travel_mode == "DRIVE" and routing_preference:
        payload["routingPreference"] = routing_preference
    if departure_time:
        payload["departureTime"] = departure_time
    if arrival_time:
        payload["arrivalTime"] = arrival_time

    response = requests.post(
        ROUTES_URL,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": _google_maps_api_key(),
            "X-Goog-FieldMask": ROUTES_FIELD_MASK,
        },
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()
    if travel_mode == "TRANSIT":
        _keep_transit_steps_only(result)
    return result


def _keep_transit_steps_only(result: dict) -> None:
    for route in result.get("routes", []):
        for leg in route.get("legs", []):
            leg["steps"] = [
                step for step in leg.get("steps", [])
                if step.get("travelMode") == "TRANSIT" or "transitDetails" in step
            ]


def _build_route_location(value: str | dict, location_input_type: str) -> dict:
    input_type = location_input_type.lower().replace("-", "_")

    if input_type in {"lat_lng", "latitude_longitude"}:
        if not isinstance(value, dict):
            raise ValueError("lat_lng route locations must be dictionaries")
        return {
            "location": {
                "latLng": {
                    "latitude": value["latitude"],
                    "longitude": value["longitude"],
                }
            }
        }

    if input_type == "address":
        return {"address": str(value)}

    if input_type in {"id", "place_id"}:
        return {"placeId": str(value)}

    raise ValueError("location_input_type must be 'address', 'id', or 'lat_lng'")



#-------------------------------------------------------------
# Tool calling interface for the agent
#-------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
TRANSPORT_DIR = BASE_DIR / "database" / "transport"
MAX_FLIGHT_SEARCH_RESULTS = 10

def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)

def _airports_for_city(city: str) -> list[dict[str, str]]:
    city_normalized = city.strip().lower()
    data = _load_json(TRANSPORT_DIR / "iata_codes.json")
    return [
        airport
        for airport in data["airports"]
        if airport["city"].strip().lower() == city_normalized
    ]

def _available_airport_cities_for_country(country: str) -> list[str]:
    country_normalized = country.strip().lower()
    data = _load_json(TRANSPORT_DIR / "iata_codes.json")
    return sorted(
        {
            airport["city"]
            for airport in data["airports"]
            if airport.get("country", "").strip().lower() == country_normalized
        }
    )

def _airport_lookup_error(kind: str, city: str) -> dict[str, Any]:
    error = {"ok": False, "error": f"No airports found for {kind} city: {city}"}
    if city.strip().lower() == "china":
        error["available_cities_for_country"] = _available_airport_cities_for_country("China")
        error["hint"] = "Use one of the available China cities in the demo airport data."
    return error

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

def search_flights(
    origin_city: str,
    destination_city: str,
    travel_date: str,
    max_results: int = 10,
) -> dict[str, Any]:
    result_limit = max(1, min(int(max_results or MAX_FLIGHT_SEARCH_RESULTS), MAX_FLIGHT_SEARCH_RESULTS))
    origin_airports = _airports_for_city(origin_city)
    destination_airports = _airports_for_city(destination_city)

    if not origin_airports:
        return _airport_lookup_error("origin", origin_city)
    if not destination_airports:
        return _airport_lookup_error("destination", destination_city)

    origin_codes = {airport["iata"] for airport in origin_airports}
    destination_codes = {airport["iata"] for airport in destination_airports}
    flights = _load_json(TRANSPORT_DIR / "aero.json")
    trip_date = date.fromisoformat(travel_date)

    candidates = []
    matched_flight_ids = set()
    for flight in flights:
        if flight["departure"] not in origin_codes or flight["arrival"] not in destination_codes:
            continue
        if not _runs_on_date(flight.get("routine", "daily"), trip_date):
            continue
        matched_flight_ids.add(flight["id"])
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
    returned_candidates = candidates[:result_limit]
    return {
        "ok": True,
        "source_file": "database/transport/aero.json",
        "database_total_flights": len(flights),
        "origin_city": origin_city,
        "destination_city": destination_city,
        "travel_date": travel_date,
        "origin_airports": sorted(origin_codes),
        "destination_airports": sorted(destination_codes),
        "matched_flight_count": len(matched_flight_ids),
        "matched_candidate_count": len(candidates),
        "returned_count": len(returned_candidates),
        "max_results": result_limit,
        "truncated": len(candidates) > len(returned_candidates),
        "candidates": returned_candidates,
    }


TOOL_MAP = {
    "get_current_location": get_current_location,
    "get_time_zone": get_time_zone,
    "get_current_datetime_for_location": get_current_datetime_for_location,
    "get_lat_lng_from_address": get_lat_lng_from_address,
    "search_by_text": search_by_text,
    "search_nearby": search_nearby,
    "compute_route": compute_route,
    "search_flights": search_flights,
}


def get_available_tool_names() -> set[str]:
    return set(TOOL_MAP)


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments or {}
    if name not in TOOL_MAP:
        return {"ok": False, "error": f"Unknown tool: {name}"}

    try:
        return TOOL_MAP[name](**arguments)
    except Exception as error:
        return {
            "ok": False,
            "error": str(error),
            "error_type": type(error).__name__,
            "tool": name,
        }



if __name__ == "__main__":
    result = get_current_datetime_for_location(51.5047424, -0.0131072)
    print(json.dumps(result, indent=2, ensure_ascii=False))
