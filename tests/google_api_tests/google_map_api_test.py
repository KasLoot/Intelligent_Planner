from __future__ import annotations

import json
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import date, datetime, timedelta, timezone


import requests


TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
NEARBY_SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"
GEOLOCATION_URL = "https://www.googleapis.com/geolocation/v1/geolocate"
GEOCODE_ADDRESS_URL = "https://geocode.googleapis.com/v4/geocode/address"
TIMEZONE_URL = "https://maps.googleapis.com/maps/api/timezone/json"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

API_KEY = __import__("os").environ.get("GOOGLE_MAPS_API_KEY", "")
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
    "routes.polyline.encodedPolyline,"
    "routes.legs.steps.travelMode,"
    "routes.legs.steps.transitDetails.headsign,"
    "routes.legs.steps.transitDetails.stopCount,"
    "routes.legs.steps.transitDetails.stopDetails.departureStop.name,"
    "routes.legs.steps.transitDetails.stopDetails.arrivalStop.name,"
    "routes.legs.steps.transitDetails.transitLine.name,"
    "routes.legs.steps.transitDetails.transitLine.nameShort,"
    "routes.legs.steps.transitDetails.transitLine.vehicle.name,"
    "routes.legs.steps.transitDetails.transitLine.vehicle.type"
)


def search_by_text(text_query: str) -> dict:
    payload = {"textQuery": text_query}
    response = requests.post(
        TEXT_SEARCH_URL,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": SEARCH_FIELD_MASK,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


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
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": SEARCH_FIELD_MASK,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


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
        params={"key": API_KEY},
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
        headers={"X-Goog-Api-Key": API_KEY},
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
            "key": API_KEY,
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
    origin_input_type: str,
    destination_input_type: str,
    travel_mode: str,
    routing_preference: str | None = "TRAFFIC_AWARE",
    compute_alternative_routes: bool = False,
    avoid_tolls: bool = False,
    avoid_highways: bool = False,
    avoid_ferries: bool = False,
    language_code: str = "en-US",
    units: str = "METRIC",
) -> dict:
    travel_mode = travel_mode.upper()
    if travel_mode not in {"DRIVE", "WALK", "TRANSIT"}:
        raise ValueError("travel_mode must be either 'DRIVE', 'WALK', or 'TRANSIT'")

    origin_location = _build_route_location(origin, origin_input_type)
    destination_location = _build_route_location(destination, destination_input_type)

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

    response = requests.post(
        ROUTES_URL,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": API_KEY,
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



if __name__ == "__main__":
    # try:
    #     result = search_by_text("UCL East, London")
    # except requests.HTTPError as error:
    #     print(f"HTTP {error.response.status_code}: {error.response.reason}")
    #     print(error.response.text)
    # except requests.RequestException as error:
    #     print(f"Request failed: {error}")
    # else:
    #     print(json.dumps(result, indent=2, ensure_ascii=False))
    #     with open("google_map_text_search_response.json", "w+", encoding="utf-8") as file:
    #         json.dump(result, file, indent=2, ensure_ascii=False)



    # try:
    #     result = get_current_location()
    # except requests.HTTPError as error:
    #     print(f"HTTP {error.response.status_code}: {error.response.reason}")
    #     print(error.response.text)
    # except requests.RequestException as error:
    #     print(f"Request failed: {error}")
    # else:
    #     print(json.dumps(result, indent=2, ensure_ascii=False))
    #     with open("google_map_geolocation_response.json", "w+", encoding="utf-8") as file:
    #         json.dump(result, file, indent=2, ensure_ascii=False)



    # try:
    #     result = search_nearby(
    #         included_types=["restaurant"],
    #         latitude=result["location"]["lat"],
    #         longitude=result["location"]["lng"],
    #         radius=1000.0,
    #         max_result_count=5,
    #     )
    # except requests.HTTPError as error:
    #     print(f"HTTP {error.response.status_code}: {error.response.reason}")
    #     print(error.response.text)
    # except requests.RequestException as error:
    #     print(f"Request failed: {error}")
    # else:
    #     print(json.dumps(result, indent=2, ensure_ascii=False))
    #     with open("google_map_nearby_search_response.json", "w+", encoding="utf-8") as file:
    #         json.dump(result, file, indent=2, ensure_ascii=False)

    

    # try:
    #     result = get_lat_lng_from_address(result["places"][0]["formattedAddress"])
    # except requests.HTTPError as error:
    #     print(f"HTTP {error.response.status_code}: {error.response.reason}")
    #     print(error.response.text)
    # except requests.RequestException as error:
    #     print(f"Request failed: {error}")
    # else:
    #     print(json.dumps(result, indent=2, ensure_ascii=False))
    #     with open("google_map_geocode_response.json", "w+", encoding="utf-8") as file:
    #         json.dump(result, file, indent=2, ensure_ascii=False)

    try:
        result = compute_route(
            origin={"address": "London, UK"},
            destination={"address": "British Museum, London, UK"},
            origin_input_type="address",
            destination_input_type="address",
            travel_mode="TRANSIT",
        )
    except requests.HTTPError as error:
        print(f"HTTP {error.response.status_code}: {error.response.reason}")
        print(error.response.text)
    except requests.RequestException as error:
        print(f"Request failed: {error}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        with open("google_map_route_response.json", "w+", encoding="utf-8") as file:
            json.dump(result, file, indent=2, ensure_ascii=False)
