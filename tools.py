from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
TRANSPORT_DIR = BASE_DIR / "database" / "transport"


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
            "Hotel and POI booking are not available yet because no current hotel or POI datasets exist outside _old_1.",
            "Use the selected arrival/departure times to constrain future hotel-night and POI-opening-time searches.",
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
    }
    if name not in tool_map:
        return {"ok": False, "error": f"Unknown tool: {name}"}
    return tool_map[name](**arguments)


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
