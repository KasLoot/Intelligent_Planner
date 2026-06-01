from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from tools import fuzzy_search, plan_trip_with_local_data, search_pois


HOST = "127.0.0.1"
PORT = 8000

LAST_TRIP_CONTEXT: dict[str, Any] | None = None


def build_fuzzy_response(message: str) -> dict[str, Any] | None:
    lowered = message.strip().lower()
    triggers = ["模糊", "搜索", "查询", "查找", "找", "search", "fuzzy", "match"]
    if not any(trigger in lowered for trigger in triggers):
        return None

    kind = None
    if any(word in lowered for word in ["城市", "city"]):
        kind = "city"
    elif any(word in lowered for word in ["机场", "airport"]):
        kind = "airport"
    elif any(word in lowered for word in ["poi", "地点", "餐厅", "酒店", "景点", "娱乐"]):
        kind = "poi"

    query = _strip_search_words(message)
    if not query:
        return None

    result = fuzzy_search(query=query, kind=kind, top_k=5)
    top = result.get("top_match")
    if not top:
        return {
            "reply": f"没有在本地城市、机场和 POI 数据中匹配到“{query}”。",
            "fuzzy_search": result,
        }

    options = "\n".join(
        f"{index + 1}. {item['label']} ({item['kind']}, {item['id']}), score={item['score']}"
        for index, item in enumerate(result["candidates"])
    )
    return {
        "reply": f"模糊搜索“{query}”结果：{result['status']}。\n{options}",
        "fuzzy_search": result,
    }


def build_poi_response(message: str) -> dict[str, Any] | None:
    category = None
    title = "Local recommendations"

    if any(word in message for word in ["餐厅", "吃饭", "美食", "火锅", "restaurant", "food", "hotpot"]):
        category = "restaurant"
        title = "餐厅推荐"
    elif any(word in message for word in ["酒店", "住宿", "hotel"]):
        category = "hotel"
        title = "酒店推荐"
    elif any(word in message for word in ["景点", "公园", "展馆", "游玩", "attraction"]):
        category = "attraction"
        title = "景点推荐"
    elif any(word in message for word in ["娱乐", "电影", "酒吧", "ktv", "entertainment"]):
        category = "entertainment"
        title = "娱乐推荐"

    if not category:
        return None

    result = search_pois(category=category, max_results=5)
    items = [_poi_to_plan_item(item, index) for index, item in enumerate(result["candidates"])]
    return {
        "plan_options": [
            {
                "plan_option_number": 1,
                "plan": [
                    {
                        "date": "2026-05-30",
                        "title": title,
                        "items": items,
                    }
                ],
            }
        ],
        "assumptions": [
            "使用本地 mock POI 数据库返回候选。",
            "当前 POI 数据还没有和真实城市绑定，因此这些地点作为本地生活 Demo 数据展示。",
        ],
        "trip_summary": f"已从本地数据中找到 {result['count']} 个{title}候选，优先展示评分和可用性较高的前 {len(items)} 个。",
    }


def build_trip_response(destination_city: str = "Paris", message: str = "") -> dict[str, Any]:
    result = plan_trip_with_local_data(
        destination_city=destination_city,
        outbound_date="2026-05-29",
        return_date="2026-05-31",
        max_transport_options=3,
        max_poi_candidates=12,
    )
    transport_options = result["transport"].get("transport_options", [])
    hotels = result["local_data"]["hotels"]["candidates"]
    restaurants = result["local_data"]["restaurants"]["candidates"]
    activities = result["local_data"]["activities"]["candidates"]

    if not transport_options:
        return {
            "reply": f"已识别目的地为 {destination_city}，但本地航班样例库里没有可用的往返航班候选。",
            "debug": result["transport"],
        }

    seed = _city_seed(destination_city + message)
    hotels = _rotate_by_city(hotels, seed)
    restaurants = _rotate_by_city(restaurants, seed + 1)
    activities = _rotate_by_city(activities, seed + 2)

    plan_options = []
    for index, transport in enumerate(transport_options[:3]):
        hotel = hotels[index % len(hotels)] if hotels else None
        restaurant = restaurants[index % len(restaurants)] if restaurants else None
        dinner = restaurants[(index + 2) % len(restaurants)] if restaurants else None
        activity = activities[index % len(activities)] if activities else None
        lunch = restaurants[(index + 1) % len(restaurants)] if restaurants else None
        times = _time_profile(seed, index)
        plan_options.append(
            {
                "plan_option_number": index + 1,
                "plan": [
                    {
                        "date": "2026-05-29",
                        "title": f"Arrive in {destination_city} - option {index + 1}",
                        "items": [
                            _flight_to_plan_item(transport["outbound"]),
                            *([_poi_to_plan_item(hotel, 1, time=times["checkin"])] if hotel else []),
                            *([_poi_to_plan_item(dinner, 2, time=times["dinner"])] if dinner else []),
                        ],
                    },
                    {
                        "date": "2026-05-30",
                        "title": f"{destination_city} local day",
                        "items": [
                            *([_poi_to_plan_item(activity, 0, time=times["activity"])] if activity else []),
                            *([_poi_to_plan_item(lunch, 1, time=times["lunch"])] if lunch else []),
                        ],
                    },
                    {
                        "date": "2026-05-31",
                        "title": "Return plan",
                        "items": [_flight_to_plan_item(transport["return"])],
                    },
                ],
            }
        )

    return {
        "plan_options": plan_options,
        "assumptions": [
            "交通数据来自 database/transport/aero.json。",
            "酒店、餐厅、景点来自 frontend/frontend/src/data/poi_database.json。",
            f"目的地已从用户输入解析为 {destination_city}。",
            f"POI 数据是本地 Demo 城市数据，尚未和 {destination_city} 真实地理位置绑定。",
        ],
        "trip_summary": f"已返回前往 {destination_city} 的结构化行程，包含交通、酒店、餐厅和景点。推荐 Option 1，因为它抵达早且回程晚，可用时间最长。",
    }


def build_sequential_trip_response(destination_city: str = "Paris", message: str = "") -> dict[str, Any]:
    outbound_date = "2026-05-29"
    return_date = "2026-05-31"
    start_time = _extract_start_time(message)
    airport_arrival_time = _add_minutes(start_time, _travel_minutes_to_airport())

    result = plan_trip_with_local_data(
        destination_city=destination_city,
        outbound_date=outbound_date,
        return_date=return_date,
        max_transport_options=12,
        max_poi_candidates=12,
    )
    transport_options = result["transport"].get("transport_options", [])
    if not transport_options:
        return {
            "reply": f"已识别目的地为 {destination_city}，但本地航班样例库里没有可用的往返航班候选。",
            "debug": result["transport"],
        }

    selected_transport = _select_earliest_reachable_transport(
        transport_options,
        outbound_date,
        airport_arrival_time,
    )
    if not selected_transport:
        return {
            "reply": (
                f"已识别目的地为 {destination_city}，但 {start_time} 出发、"
                f"{airport_arrival_time} 到机场后，没有可赶上的出境航班。"
            ),
            "debug": {
                "start_time": start_time,
                "airport_arrival_time": airport_arrival_time,
                "transport_options": transport_options,
            },
        }

    seed = _city_seed(destination_city + message)
    hotels = _rotate_by_city(result["local_data"]["hotels"]["candidates"], seed)
    restaurants = _rotate_by_city(result["local_data"]["restaurants"]["candidates"], seed + 1)
    activities = _rotate_by_city(result["local_data"]["activities"]["candidates"], seed + 2)

    plan = _build_sequential_timeline(
        destination_city=destination_city,
        outbound_date=outbound_date,
        return_date=return_date,
        start_time=start_time,
        airport_arrival_time=airport_arrival_time,
        transport=selected_transport,
        hotel=hotels[0] if hotels else None,
        lunch=restaurants[0] if restaurants else None,
        dinner=restaurants[1 % len(restaurants)] if restaurants else None,
        first_activity=activities[0] if activities else None,
        second_activity=activities[1 % len(activities)] if activities else None,
        seed=seed,
    )

    outbound = selected_transport["outbound"]
    response = {
        "plan_options": [
            {
                "plan_option_number": 1,
                "plan": plan,
            }
        ],
        "assumptions": [
            "交通数据来自 database/transport/aero.json。",
            "酒店、餐厅、景点来自 frontend/frontend/src/data/poi_database.json。",
            f"目的地已从用户输入解析为 {destination_city}。",
            f"首日出发时间为 {start_time}；到机场用时暂按 60 分钟估算，后续可替换为 Google Maps 路线时间。",
            f"航班选择规则：到机场时间 {airport_arrival_time} 之后，选择前往目的地最早可赶上的航班。",
            "航班落地后到下一个地点默认 60 分钟；景点停留按 2-3 小时估算。",
            "午餐安排在 11:30-13:00，晚餐安排在 17:00-20:00。",
            f"POI 数据是本地 Demo 城市数据，尚未和 {destination_city} 真实地理位置绑定。",
        ],
        "trip_summary": (
            f"已按时间顺序生成前往 {destination_city} 的行程：{start_time} 出发，"
            f"{airport_arrival_time} 到机场，选择可赶上的最早航班 "
            f"{outbound['flight_number']}（{outbound['departure_airport']} 到 {outbound['arrival_airport']}）。"
        ),
    }
    _remember_trip_context(
        destination_city=destination_city,
        message=message,
        outbound_date=outbound_date,
        return_date=return_date,
        start_time=start_time,
        airport_arrival_time=airport_arrival_time,
        transport_options=transport_options,
        selected_transport=selected_transport,
        local_data=result["local_data"],
        seed=seed,
    )
    return response


def _poi_to_plan_item(item: dict[str, Any], index: int, time: str | None = None) -> dict[str, Any]:
    return {
        "time": time or _default_time(index),
        "domain": item["domain"],
        "item_id": item["item_id"],
        "name": item["name"],
        "location": item.get("location"),
        "price": item.get("price", 0),
        "booking_required": item.get("booking_required", True),
        "notes": item.get("notes", ""),
    }


def _flight_to_plan_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "time": item["departure_at"][11:16],
        "domain": "flight",
        "item_id": item["candidate_id"],
        "name": f"{item['flight_number']} ({item['departure_airport']} to {item['arrival_airport']})",
        "location": f"{item['departure_airport']} to {item['arrival_airport']}",
        "price": item["price"],
        "booking_required": True,
        "notes": f"Departs {item['departure_at']}, arrives {item['arrival_at']}. Baggage {item.get('baggage_allowance')}; meal {item.get('meal_service')}.",
    }


def _transfer_item(
    item_id: str,
    time_value: str,
    name: str,
    location: str | None,
    duration_minutes: int,
) -> dict[str, Any]:
    return {
        "time": time_value,
        "domain": "transport",
        "item_id": item_id,
        "name": name,
        "location": location,
        "price": 0,
        "booking_required": False,
        "notes": (
            f"Estimated transfer time: {duration_minutes} minutes. "
            "This is a placeholder for future Google Maps route duration."
        ),
    }


def _build_sequential_timeline(
    *,
    destination_city: str,
    outbound_date: str,
    return_date: str,
    start_time: str,
    airport_arrival_time: str,
    transport: dict[str, Any],
    hotel: dict[str, Any] | None,
    lunch: dict[str, Any] | None,
    dinner: dict[str, Any] | None,
    first_activity: dict[str, Any] | None,
    second_activity: dict[str, Any] | None,
    seed: int,
) -> list[dict[str, Any]]:
    outbound = transport["outbound"]
    inbound = transport["return"]
    arrival_next_place = _datetime_to_time(
        _parse_api_datetime(outbound["arrival_at"]) + timedelta(minutes=_travel_minutes_from_airport())
    )

    day1_items = [
        _transfer_item(
            "tbd-origin-to-airport",
            start_time,
            "Depart for airport",
            f"Current location to {outbound['departure_airport']}",
            _travel_minutes_to_airport(),
        ),
        _transfer_item(
            "tbd-arrive-origin-airport",
            airport_arrival_time,
            f"Arrive at {outbound['departure_airport']}",
            outbound["departure_airport"],
            0,
        ),
        _flight_to_plan_item(outbound),
        _transfer_item(
            "tbd-destination-airport-transfer",
            arrival_next_place,
            "Transfer from destination airport",
            f"{outbound['arrival_airport']} to next stop",
            _travel_minutes_from_airport(),
        ),
    ]
    if hotel:
        day1_items.append(_poi_to_plan_item(hotel, 0, time=arrival_next_place))

    dinner_time = _first_valid_meal_time(
        earliest_time=_add_minutes(arrival_next_place, 30),
        window_start="17:00",
        window_end="20:00",
        seed=seed,
    )
    if dinner and dinner_time:
        day1_items.append(_poi_to_plan_item(dinner, 1, time=dinner_time))

    attraction_minutes = _activity_duration_minutes(seed)
    activity_start = _activity_start_time(seed)
    lunch_time = _meal_time_in_window("11:30", "13:00", seed + 3)
    second_activity_start = _add_minutes(lunch_time, 90)

    day2_items = []
    if first_activity:
        item = _poi_to_plan_item(first_activity, 0, time=activity_start)
        item["notes"] = _append_note(item["notes"], f"Planned stay: {attraction_minutes} minutes.")
        day2_items.append(item)
    if lunch:
        day2_items.append(_poi_to_plan_item(lunch, 1, time=lunch_time))
    if second_activity:
        second_minutes = _activity_duration_minutes(seed + 5)
        item = _poi_to_plan_item(second_activity, 2, time=second_activity_start)
        item["notes"] = _append_note(item["notes"], f"Planned stay: {second_minutes} minutes.")
        day2_items.append(item)

    day2_dinner_time = _meal_time_in_window("17:00", "20:00", seed + 7)
    if dinner:
        day2_items.append(_poi_to_plan_item(dinner, 3, time=day2_dinner_time))

    return [
        {
            "date": outbound_date,
            "title": f"Depart and arrive in {destination_city}",
            "items": day1_items,
        },
        {
            "date": _next_date(outbound_date),
            "title": f"{destination_city} timed local day",
            "items": day2_items,
        },
        {
            "date": return_date,
            "title": "Return plan",
            "items": [_flight_to_plan_item(inbound)],
        },
    ]


def build_disruption_response(message: str) -> dict[str, Any] | None:
    disruption = _detect_flight_disruption(message)
    if not disruption:
        return None
    if not LAST_TRIP_CONTEXT:
        return {
            "reply": "我还没有上一份可调整的行程。请先让我安排一次行程，再告诉我航班延误或取消。",
        }

    context = LAST_TRIP_CONTEXT
    if disruption["type"] == "delay":
        return _build_delay_recovery(context, disruption["delay_minutes"])
    if disruption["type"] == "cancel":
        return _build_cancel_recovery(context)
    return None


def _build_delay_recovery(context: dict[str, Any], delay_minutes: int) -> dict[str, Any]:
    selected_transport = _delay_transport(context["selected_transport"], delay_minutes)
    response = _build_recovery_plan_response(
        context=context,
        selected_transport=selected_transport,
        recovery_title=f"航班延误 {delay_minutes} 分钟后的调整方案",
        recovery_note=(
            f"原航班 {context['selected_transport']['outbound']['flight_number']} 延误 "
            f"{delay_minutes} 分钟，后续到达、转场、入住和晚餐顺延重排。"
        ),
    )
    _remember_trip_context(
        destination_city=context["destination_city"],
        message=context["message"],
        outbound_date=context["outbound_date"],
        return_date=context["return_date"],
        start_time=context["start_time"],
        airport_arrival_time=context["airport_arrival_time"],
        transport_options=context["transport_options"],
        selected_transport=selected_transport,
        local_data=context["local_data"],
        seed=context["seed"],
    )
    return response


def _build_cancel_recovery(context: dict[str, Any]) -> dict[str, Any]:
    original_departure = _parse_api_datetime(context["selected_transport"]["outbound"]["departure_at"])
    original_candidate_id = context["selected_transport"]["outbound"]["candidate_id"]
    alternatives = [
        option
        for option in context["transport_options"]
        if option["outbound"]["candidate_id"] != original_candidate_id
        and _parse_api_datetime(option["outbound"]["departure_at"]) > original_departure
    ]
    if not alternatives:
        outbound = context["selected_transport"]["outbound"]
        return {
            "reply": (
                f"{outbound['flight_number']} 已取消，但本地航班样例库里没有 "
                f"{outbound['departure_at'][11:16]} 之后前往目的地的替代航班。"
            ),
            "debug": {
                "cancelled_flight": original_candidate_id,
                "available_options": context["transport_options"],
            },
        }

    selected_transport = min(
        alternatives,
        key=lambda option: (
            _parse_api_datetime(option["outbound"]["departure_at"]),
            option["total_transport_price"],
        ),
    )
    response = _build_recovery_plan_response(
        context=context,
        selected_transport=selected_transport,
        recovery_title="航班取消后的替代方案",
        recovery_note=(
            f"原航班 {context['selected_transport']['outbound']['flight_number']} 已取消，"
            f"改选下一班可用航班 {selected_transport['outbound']['flight_number']}。"
        ),
    )
    _remember_trip_context(
        destination_city=context["destination_city"],
        message=context["message"],
        outbound_date=context["outbound_date"],
        return_date=context["return_date"],
        start_time=context["start_time"],
        airport_arrival_time=context["airport_arrival_time"],
        transport_options=context["transport_options"],
        selected_transport=selected_transport,
        local_data=context["local_data"],
        seed=context["seed"] + 17,
    )
    return response


def _build_recovery_plan_response(
    *,
    context: dict[str, Any],
    selected_transport: dict[str, Any],
    recovery_title: str,
    recovery_note: str,
) -> dict[str, Any]:
    local_data = context["local_data"]
    seed = context["seed"] + 17
    hotels = _rotate_by_city(local_data["hotels"]["candidates"], seed)
    restaurants = _rotate_by_city(local_data["restaurants"]["candidates"], seed + 1)
    activities = _rotate_by_city(local_data["activities"]["candidates"], seed + 2)
    plan = _build_sequential_timeline(
        destination_city=context["destination_city"],
        outbound_date=context["outbound_date"],
        return_date=context["return_date"],
        start_time=context["start_time"],
        airport_arrival_time=context["airport_arrival_time"],
        transport=selected_transport,
        hotel=hotels[0] if hotels else None,
        lunch=restaurants[0] if restaurants else None,
        dinner=restaurants[1 % len(restaurants)] if restaurants else None,
        first_activity=activities[0] if activities else None,
        second_activity=activities[1 % len(activities)] if activities else None,
        seed=seed,
    )
    outbound = selected_transport["outbound"]
    return {
        "plan_options": [
            {
                "plan_option_number": 1,
                "plan": plan,
            }
        ],
        "assumptions": [
            recovery_note,
            "恢复规划沿用上一份行程的目的地、日期、用户出发时间和本地 POI 候选。",
            "落地后到下一个地点仍按 60 分钟估算，后续可替换为 Google Maps 路线时间。",
        ],
        "trip_summary": (
            f"{recovery_title}：已重新按时间顺序安排。当前航班为 "
            f"{outbound['flight_number']}，{outbound['departure_at'][11:16]} 出发，"
            f"{outbound['arrival_at'][11:16]} 到达。"
        ),
    }


def _detect_flight_disruption(message: str) -> dict[str, Any] | None:
    lowered = message.lower()
    if any(word in message for word in ["取消", "取消了", "航班取消"]) or "cancel" in lowered:
        return {"type": "cancel"}
    if any(word in message for word in ["延误", "晚点", "推迟"]) or "delay" in lowered:
        return {"type": "delay", "delay_minutes": _extract_delay_minutes(message)}
    return None


def _extract_delay_minutes(message: str) -> int:
    hour_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:个)?小时", message)
    if hour_match:
        return int(float(hour_match.group(1)) * 60)
    minute_match = re.search(r"(\d+)\s*分钟", message)
    if minute_match:
        return int(minute_match.group(1))
    chinese_hour_match = re.search(r"([零〇一二两三四五六七八九十]{1,3})\s*(?:个)?小时", message)
    if chinese_hour_match:
        value = _chinese_number_to_int(chinese_hour_match.group(1))
        if value is not None:
            return value * 60
    return 120


def _delay_transport(transport: dict[str, Any], delay_minutes: int) -> dict[str, Any]:
    adjusted = copy.deepcopy(transport)
    outbound = adjusted["outbound"]
    outbound["departure_at"] = _shift_api_datetime(outbound["departure_at"], delay_minutes)
    outbound["arrival_at"] = _shift_api_datetime(outbound["arrival_at"], delay_minutes)
    outbound["candidate_id"] = f"{outbound['candidate_id']}+delay{delay_minutes}"
    outbound["notes"] = f"Delayed by {delay_minutes} minutes."
    return adjusted


def _shift_api_datetime(value: str, minutes: int) -> str:
    shifted = _parse_api_datetime(value) + timedelta(minutes=minutes)
    return shifted.isoformat().replace("+00:00", "Z")


def _remember_trip_context(
    *,
    destination_city: str,
    message: str,
    outbound_date: str,
    return_date: str,
    start_time: str,
    airport_arrival_time: str,
    transport_options: list[dict[str, Any]],
    selected_transport: dict[str, Any],
    local_data: dict[str, Any],
    seed: int,
) -> None:
    global LAST_TRIP_CONTEXT
    LAST_TRIP_CONTEXT = {
        "destination_city": destination_city,
        "message": message,
        "outbound_date": outbound_date,
        "return_date": return_date,
        "start_time": start_time,
        "airport_arrival_time": airport_arrival_time,
        "transport_options": copy.deepcopy(transport_options),
        "selected_transport": copy.deepcopy(selected_transport),
        "local_data": copy.deepcopy(local_data),
        "seed": seed,
    }


def _default_time(index: int) -> str:
    return ["09:00", "12:00", "15:00", "18:00", "20:00"][min(index, 4)]


def _city_seed(value: str) -> int:
    seed = 0
    for char in value:
        seed = (seed * 131 + ord(char)) % 1000003
    return seed


def _rotate_by_city(items: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    if not items:
        return items
    offset = seed % len(items)
    return items[offset:] + items[:offset]


def _time_profile(seed: int, option_index: int) -> dict[str, str]:
    profiles = [
        {"checkin": "14:00", "dinner": "18:30", "activity": "09:30", "lunch": "12:00"},
        {"checkin": "15:00", "dinner": "19:30", "activity": "10:30", "lunch": "13:00"},
        {"checkin": "16:00", "dinner": "20:00", "activity": "11:00", "lunch": "13:30"},
    ]
    return profiles[(seed + option_index) % len(profiles)]


def _extract_start_time(message: str) -> str:
    match = re.search(r"(\d{1,2})[:：](\d{2})", message)
    if match:
        return _normalize_hhmm(int(match.group(1)), int(match.group(2)))

    match = re.search(r"(\d{1,2})\s*点\s*(半|(\d{1,2})分?)?", message)
    if match:
        hour = int(match.group(1))
        minute = 30 if match.group(2) == "半" else int(match.group(3) or 0)
        return _normalize_hhmm(hour, minute)

    match = re.search(r"([零〇一二两三四五六七八九十]{1,3})\s*点\s*(半|([零〇一二两三四五六七八九十]{1,3})分?)?", message)
    if match:
        hour = _chinese_number_to_int(match.group(1))
        minute = 30 if match.group(2) == "半" else _chinese_number_to_int(match.group(3) or "")
        if hour is not None and minute is not None:
            return _normalize_hhmm(hour, minute)

    return "08:00"


def _chinese_number_to_int(value: str) -> int | None:
    if not value:
        return 0
    digits = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if value in digits:
        return digits[value]
    if value == "十":
        return 10
    if "十" in value:
        left, _, right = value.partition("十")
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return tens * 10 + ones
    return None


def _normalize_hhmm(hour: int, minute: int) -> str:
    hour = max(0, min(hour, 23))
    minute = max(0, min(minute, 59))
    return f"{hour:02d}:{minute:02d}"


def _travel_minutes_to_airport() -> int:
    return 60


def _travel_minutes_from_airport() -> int:
    return 60


def _select_earliest_reachable_transport(
    transport_options: list[dict[str, Any]],
    outbound_date: str,
    airport_arrival_time: str,
) -> dict[str, Any] | None:
    cutoff = _combine_date_time(outbound_date, airport_arrival_time)
    reachable = [
        option
        for option in transport_options
        if _parse_api_datetime(option["outbound"]["departure_at"]) >= cutoff
    ]
    if not reachable:
        return None
    return min(
        reachable,
        key=lambda option: (
            _parse_api_datetime(option["outbound"]["departure_at"]),
            option["total_transport_price"],
            _parse_api_datetime(option["return"]["departure_at"]),
        ),
    )


def _activity_duration_minutes(seed: int) -> int:
    return [120, 150, 180][seed % 3]


def _activity_start_time(seed: int) -> str:
    return ["09:00", "09:30", "10:00"][seed % 3]


def _meal_time_in_window(window_start: str, window_end: str, seed: int) -> str:
    start = _minutes_from_hhmm(window_start)
    end = _minutes_from_hhmm(window_end)
    slots = list(range(start, end + 1, 20))
    return _hhmm_from_minutes(slots[seed % len(slots)])


def _first_valid_meal_time(
    *,
    earliest_time: str,
    window_start: str,
    window_end: str,
    seed: int,
) -> str | None:
    earliest = _minutes_from_hhmm(earliest_time)
    start = max(earliest, _minutes_from_hhmm(window_start))
    end = _minutes_from_hhmm(window_end)
    if start > end:
        return None
    slots = list(range(start, end + 1, 20))
    return _hhmm_from_minutes(slots[seed % len(slots)])


def _add_minutes(hhmm: str, minutes: int) -> str:
    return _hhmm_from_minutes(_minutes_from_hhmm(hhmm) + minutes)


def _minutes_from_hhmm(hhmm: str) -> int:
    hour, minute = [int(part) for part in hhmm.split(":")]
    return hour * 60 + minute


def _hhmm_from_minutes(minutes: int) -> str:
    minutes = minutes % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _parse_api_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _combine_date_time(date_value: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{date_value}T{hhmm}:00+00:00")


def _datetime_to_time(value: datetime) -> str:
    return value.strftime("%H:%M")


def _next_date(date_value: str) -> str:
    return (datetime.fromisoformat(date_value) + timedelta(days=1)).date().isoformat()


def _append_note(notes: str, extra: str) -> str:
    return f"{notes}; {extra}" if notes else extra


def _strip_search_words(message: str) -> str:
    query = message.strip()
    for word in [
        "模糊搜索",
        "模糊查询",
        "搜索",
        "查询",
        "查找",
        "找一下",
        "找",
        "search",
        "fuzzy",
        "match",
    ]:
        query = query.replace(word, " ")
    return " ".join(query.split()).strip(" ：:，,。.")


def _extract_destination_city(message: str) -> str:
    result = fuzzy_search(query=message, kind="city", top_k=3)
    top_match = result.get("top_match")
    if top_match and top_match.get("score", 0) >= 0.56:
        metadata = top_match.get("metadata", {})
        return metadata.get("city") or top_match["label"]
    return "Paris"


def handle_message(message: str) -> dict[str, Any]:
    disruption_response = build_disruption_response(message)
    if disruption_response:
        return disruption_response

    fuzzy_response = build_fuzzy_response(message)
    if fuzzy_response:
        return fuzzy_response

    poi_response = build_poi_response(message)
    if poi_response:
        return poi_response

    if any(word in message for word in ["规划", "旅行", "行程", "旅游", "出发", "去", "trip", "travel", "plan", "Paris"]):
        return build_sequential_trip_response(_extract_destination_city(message), message)

    return {
        "reply": "你好，我是小团。可以输入“餐厅”“酒店”“景点”，或让我规划一段包含交通和本地生活候选的行程。"
    }


class AgentHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        self._send_json({})

    def do_POST(self) -> None:
        if self.path != "/api/agent/chat":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        response = handle_message(str(payload.get("message", "")))
        self._send_json(response)

    def _send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), AgentHandler)
    print(f"Serving local Agent API at http://{HOST}:{PORT}/api/agent/chat")
    server.serve_forever()


if __name__ == "__main__":
    main()
