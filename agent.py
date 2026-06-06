import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from tools import call_tool, get_available_tool_names


MODEL = "gpt-5.4-mini"
SYSTEM_PROMPT_PATH = "configs/system_prompt_zh.md"
MAX_TOOL_ROUNDS = 20
DEFAULT_TRACE_PATH = "agent_debug_trace.json"
ANSI_RESET = "\033[0m"
ANSI_WHITE = "\033[97m"
ANSI_LIGHT_BLUE = "\033[94m"
ANSI_GREEN = "\033[92m"
RELATIVE_DATE_PHRASES = (
    "today",
    "tomorrow",
    "this weekend",
    "next weekend",
    "this week",
    "next week",
)
TRIP_EDIT_PHRASES = (
    "option 1",
    "option 2",
    "option 3",
    "search flight",
    "search flights",
    "find flight",
    "find flights",
    "add flight",
    "add flights",
)
CURRENT_LOCATION_ORIGIN_HINT = (
    "本轮提示: 在输出最终 JSON 前，先用位置/时间工具解析相对日期。"
    "如果用户省略出发地，调用 get_current_location，并基于合理默认值起草。"
)
TRIP_EDIT_HINT = (
    "本轮提示: 这是一次编辑/追问。保留用户所选 option 的完整行程覆盖范围；"
    "如果添加航班，也要保留或重新获取住宿、餐饮、POI 和本地交通。"
)
CORE_TRAVEL_EXPERT_CONSTRAINTS = """

最新业务约束:
- 你是一名专业的 AI 智能行程规划专家，根据用户输入和实时状态生成、微调和管理个性化旅游行程。
- 在正式生成行程前，必须先明确锁定出发地、目的地、旅游长度/天数。若任一信息缺失，只返回中文追问 JSON，不要生成草案。
- 所有面向用户展示内容必须完全使用中文；航班编号、机场代码、货币代码、ISO 时间和 JSON 键名可保持原格式。
- 行程保持精炼，只保留航班、酒店、餐厅、景点/活动，以及机场到酒店/目的地、返程去机场的市内短途交通。
- 完整过夜行程必须安排餐厅；不要在 assumptions、plan_summary 或 response_to_user 中说“不包含餐厅”。
- 午餐时间为 11:00-14:00，晚餐时间为 17:00-20:00。正常情况下每个午餐、晚餐时段都必须安排一个 restaurant item，用餐时间约 1 小时。
- 如果午餐或晚餐时段被航班占用，或被前往机场/返程去机场的交通占用，该餐可以不安排；其他情况必须安排。
- 餐厅只能安排在 11:00-14:00 或 17:00-20:00 内。若饭点因航班或机场接驳错过，不要补排深夜、凌晨或错峰餐厅。
- 如果用户没有说明具体行程日期，使用真实当前日期的下一天作为第一天；例如当前日期为 2026-06-06 且用户要 3 天游，则日期为 2026-06-07 至 2026-06-09。
- 如果用户给出日期或日期区间，严格按用户指定日期生成；例如 6.9-6.14 表示第一天 6.9，最后一天 6.14。
- 严禁包含景点之间、酒店与景点之间的城市公交、地铁换乘等市内公共交通。
- 每天最多安排 3 个景点/活动。可以没有景点；如果第一天到达太晚，安排航班、必要接驳和入住酒店即可。
- 去程航班必须是第一天第一个 item，回程航班必须是最后一天最后一个 item。
- 用户确认行程或系统要求 Recovery 行程时，严格输出可解析 JSON 对象，并尽量减少文字。
"""
RESPONSE_TO_USER_INTERNAL_TERMS = (
    "search_flights",
    "compute_route",
    "get_current_location",
    "get_lat_lng_from_address",
    "get_time_zone",
    "get_current_datetime_for_location",
    "search_by_text",
    "search_nearby",
    "candidate_id",
    "item_id",
    "source_tool",
    "tbd",
    "api",
    "json",
    "字段",
    "键",
    "校验",
    "反馈",
    "修正",
    "候选",
)
CITY_ALIASES = {
    "伦敦": "London",
    "上海": "Shanghai",
    "北京": "Beijing",
    "巴黎": "Paris",
    "纽约": "New York",
    "阿姆斯特丹": "Amsterdam",
    "罗马": "Rome",
    "巴塞罗那": "Barcelona",
    "法兰克福": "Frankfurt",
    "苏黎世": "Zurich",
    "迪拜": "Dubai",
}
CITY_NAME_ZH = {v: k for k, v in CITY_ALIASES.items()}
CHINESE_DAY_NUMBERS = {
    "一": 1,
    "两": 2,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
}


def load_json(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def load_text(path):
    with open(path, encoding="utf-8") as file:
        return file.read()


def write_output(path, content):
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)
        if content and not content.endswith("\n"):
            file.write("\n")


def write_json(path, content):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(content, file, indent=2, ensure_ascii=False)
        file.write("\n")


def _supported_airport_cities():
    try:
        data = load_json("database/transport/iata_codes.json")
    except FileNotFoundError:
        return []
    cities = sorted({airport["city"] for airport in data.get("airports", [])})
    return cities


def _extract_city_mentions(user_message):
    normalized = user_message.casefold()
    mentions = []
    for alias, city in CITY_ALIASES.items():
        if alias in user_message and city not in mentions:
            mentions.append(city)
    for city in _supported_airport_cities():
        if city.casefold() in normalized and city not in mentions:
            mentions.append(city)
    return mentions


def _extract_trip_days(user_message):
    # Date range: "6.21-6.25", "6/21-6/25", "6.21~6.25"
    range_match = re.search(
        r"(\d{1,2})[./](\d{1,2})\s*[-~到至]+\s*(\d{1,2})[./](\d{1,2})",
        user_message,
    )
    if range_match:
        start_month, start_day = int(range_match.group(1)), int(range_match.group(2))
        end_month, end_day = int(range_match.group(3)), int(range_match.group(4))
        year = datetime.now().year
        start = date(year, start_month, start_day)
        end = date(year, end_month, end_day)
        days = (end - start).days + 1
        if days >= 1:
            return days

    # Chinese date range: "6月1日到6月5日", "6月21日-6月25日"
    cn_range = re.search(
        r"(\d{1,2})月(\d{1,2})日?\s*[-~到至]+\s*(\d{1,2})月(\d{1,2})日?",
        user_message,
    )
    if cn_range:
        start_month, start_day = int(cn_range.group(1)), int(cn_range.group(2))
        end_month, end_day = int(cn_range.group(3)), int(cn_range.group(4))
        year = datetime.now().year
        start = date(year, start_month, start_day)
        end = date(year, end_month, end_day)
        days = (end - start).days + 1
        if days >= 1:
            return days

    # ISO date range: "2026-06-21" to "2026-06-25"
    iso_range = re.search(
        r"(20\d{2}-\d{2}-\d{2})\s*[-~到至]+\s*(20\d{2}-\d{2}-\d{2})",
        user_message,
    )
    if iso_range:
        start = date.fromisoformat(iso_range.group(1))
        end = date.fromisoformat(iso_range.group(2))
        days = (end - start).days + 1
        if days >= 1:
            return days

    digit_match = re.search(r"(\d+)\s*(?:天|day|days)", user_message, re.IGNORECASE)
    if digit_match:
        return max(1, int(digit_match.group(1)))
    chinese_match = re.search(r"([一两二三四五六七])\s*天", user_message)
    if chinese_match:
        return CHINESE_DAY_NUMBERS[chinese_match.group(1)]
    return None


def _extract_start_date(user_message):
    # ISO format first: "2026-07-01"
    iso_match = re.search(r"(20\d{2}-\d{2}-\d{2})", user_message)
    if iso_match:
        return date.fromisoformat(iso_match.group(1))

    # Short date format: "6.21", "6/21", "6月21日"
    short_match = re.search(r"(\d{1,2})[./月](\d{1,2})(?:日)?", user_message)
    if short_match:
        year = datetime.now().year
        return date(year, int(short_match.group(1)), int(short_match.group(2)))
    return datetime.now().date() + timedelta(days=1)


def _flight_item_from_candidate(candidate, direction):
    direction_label = "去程" if direction == "outbound" else "回程"
    return {
        "start_time": candidate["departure_at"],
        "end_time": candidate["arrival_at"],
        "domain": "flight",
        "item_id": candidate["candidate_id"],
        "name": f"{candidate['airline']} {candidate['flight_number']}",
        "address": None,
        "national_phone_number": None,
        "international_phone_number": None,
        "rating": 0,
        "price": candidate.get("price", 0),
        "currency": candidate.get("currency"),
        "booking_required": True,
        "notes": (
            f"已为本次{direction_label}行程锁定航班，后续安排会围绕该航班时间展开。"
        ),
        "details": {
            "candidate_id": candidate["candidate_id"],
            "flight_id": candidate.get("flight_id"),
            "flight_number": candidate.get("flight_number"),
            "airline": candidate.get("airline"),
            "origin_airport": candidate.get("departure_airport"),
            "destination_airport": candidate.get("arrival_airport"),
            "departure_at": candidate.get("departure_at"),
            "arrival_at": candidate.get("arrival_at"),
            "duration_minutes": candidate.get("duration_minutes"),
            "price": candidate.get("price"),
            "currency": candidate.get("currency"),
            "baggage_allowance": candidate.get("baggage_allowance"),
            "meal_service": candidate.get("meal_service"),
            "source_tool": "local_aero_json",
            "fixed_by_backend": True,
        },
    }


def build_fixed_flight_context(user_message):
    cities = _extract_city_mentions(user_message)
    if len(cities) < 2:
        return None

    origin_city, destination_city = cities[0], cities[1]
    trip_days = _extract_trip_days(user_message) or 3
    start_date = _extract_start_date(user_message)
    return_date = start_date + timedelta(days=max(1, trip_days - 1))

    outbound = call_tool(
        "search_flights",
        {
            "origin_city": origin_city,
            "destination_city": destination_city,
            "travel_date": start_date.isoformat(),
            "max_results": 10,
        },
    )
    inbound = call_tool(
        "search_flights",
        {
            "origin_city": destination_city,
            "destination_city": origin_city,
            "travel_date": return_date.isoformat(),
            "max_results": 10,
        },
    )
    if not outbound.get("ok") or not inbound.get("ok"):
        return None
    if not outbound.get("candidates") or not inbound.get("candidates"):
        return None

    outbound_candidate = sorted(outbound["candidates"], key=lambda item: item["departure_at"])[0]
    return_candidate = sorted(inbound["candidates"], key=lambda item: item["departure_at"])[-1]
    fixed = {
        "origin_city": origin_city,
        "destination_city": destination_city,
        "trip_days": trip_days,
        "start_date": start_date.isoformat(),
        "return_date": return_date.isoformat(),
        "outbound_flight": _flight_item_from_candidate(outbound_candidate, "outbound"),
        "return_flight": _flight_item_from_candidate(return_candidate, "return"),
    }
    fixed["instruction"] = (
        "Backend fixed flight anchors from local database/transport/aero.json. "
        "Do not call or ask for flight search. Do not replace these flights. "
        "Plan hotels, restaurants, attractions, and local transport around these fixed flights. "
        "The outbound flight must be the first flight item on the first day, and the return flight "
        "must be the final flight item on the last day.\n"
        f"{json.dumps(fixed, ensure_ascii=False)}"
    )
    return fixed


def build_agent_message_with_fixed_flights(user_message, fixed_flights):
    hints = []
    if fixed_flights:
        hints.append(fixed_flights["instruction"])

    # Always extract and inject trip duration hint so the agent produces the right number of days
    trip_days = _extract_trip_days(user_message)
    start_date = _extract_start_date(user_message)
    if trip_days:
        end_date = start_date + timedelta(days=max(0, trip_days - 1))
        hints.append(
            f"Backend hint: the user requested exactly {trip_days} day(s). "
            f"Start date: {start_date.isoformat()}, end date: {end_date.isoformat()}. "
            f"You MUST produce exactly {trip_days} plan day objects in each plan option, "
            f"with dates from {start_date.isoformat()} to {end_date.isoformat()} inclusive."
        )

    if not hints:
        return user_message
    return f"{user_message}\n\n" + "\n\n".join(hints)


def _remove_nonfixed_flights(items, allowed_ids):
    return [
        item
        for item in items
        if item.get("domain") != "flight" or item.get("item_id") in allowed_ids
    ]


def apply_fixed_flights_to_payload(payload, fixed_flights):
    if not fixed_flights or not isinstance(payload, dict):
        return payload

    outbound = fixed_flights["outbound_flight"]
    return_flight = fixed_flights["return_flight"]
    allowed_ids = {outbound["item_id"], return_flight["item_id"]}
    for option in payload.get("plan_options", []) or []:
        days = option.get("plan", []) or []
        if not days:
            continue

        first_day = days[0]
        first_items = _remove_nonfixed_flights(first_day.get("items", []) or [], allowed_ids)
        first_items = [item for item in first_items if item.get("item_id") != outbound["item_id"]]
        first_day["items"] = [outbound] + first_items

        last_day = days[-1]
        last_items = _remove_nonfixed_flights(last_day.get("items", []) or [], allowed_ids)
        last_items = [item for item in last_items if item.get("item_id") != return_flight["item_id"]]
        last_day["items"] = last_items + [return_flight]

    assumptions = payload.setdefault("assumptions", [])
    fixed_note = (
        "航班已按可用候选锁定，其余行程围绕航班时间安排。"
    )
    if fixed_note not in assumptions:
        assumptions.append(fixed_note)
    return payload


def load_env_file(path=".env"):
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def to_jsonable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    return value


def validate_tool_config(available_tools):
    configured_names = [tool["name"] for tool in available_tools]
    duplicate_names = sorted(
        name for name in set(configured_names) if configured_names.count(name) > 1
    )
    if duplicate_names:
        raise ValueError(f"Duplicate tools in configs/tools.json: {duplicate_names}")

    callable_names = get_available_tool_names()
    missing = sorted(set(configured_names) - callable_names)
    if missing:
        raise ValueError(f"Tool schemas without call_tool handlers: {missing}")


def _item_attr(item, name, default=None):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _parse_tool_arguments(item):
    raw_arguments = _item_attr(item, "arguments", "{}") or "{}"
    try:
        return json.loads(raw_arguments), raw_arguments, None
    except json.JSONDecodeError as error:
        return {}, raw_arguments, {
            "ok": False,
            "error": f"Invalid JSON tool arguments: {error}",
            "error_type": type(error).__name__,
        }


def colorize(text, color):
    return f"{color}{text}{ANSI_RESET}"


def format_json_for_terminal(value):
    return json.dumps(value, indent=2, ensure_ascii=False)


def needs_relative_date_tool_resolution(user_message):
    normalized = user_message.casefold()
    return any(phrase in normalized for phrase in RELATIVE_DATE_PHRASES)


def needs_trip_edit_context(user_message):
    normalized = user_message.casefold()
    return any(phrase in normalized for phrase in TRIP_EDIT_PHRASES)


def build_turn_instructions(base_instructions, user_message):
    hints = []
    if needs_relative_date_tool_resolution(user_message):
        hints.append(CURRENT_LOCATION_ORIGIN_HINT)
    if needs_trip_edit_context(user_message):
        hints.append(TRIP_EDIT_HINT)
    all_hints = [CORE_TRAVEL_EXPERT_CONSTRAINTS, *hints]
    return f"{base_instructions}\n\n" + "\n\n".join(all_hints)


def _iter_plan_items(plan_payload):
    for option in plan_payload.get("plan_options", []) or []:
        for day in option.get("plan", []) or []:
            for item in day.get("items", []) or []:
                yield item


def _item_text(item):
    parts = [
        item.get("name"),
        item.get("notes"),
        item.get("address"),
    ]
    details = item.get("details") or {}
    parts.extend(
        str(details.get(key) or "")
        for key in ("origin", "destination", "route_summary")
    )
    return " ".join(str(part) for part in parts if part).casefold()


def _has_domain(items, domain):
    return any(item.get("domain") == domain for item in items)


def _has_return_leg(items):
    return any(
        item.get("domain") == "flight"
        and any(keyword in _item_text(item) for keyword in ("return", "back", "lhr", "london"))
        for item in items
    )


def _minutes_from_time_value(value):
    if not value:
        return None
    text = str(value)
    match = re.search(r"(?:T|\b)(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def _item_time_range(item):
    start = _minutes_from_time_value(item.get("start_time") or item.get("time"))
    end = _minutes_from_time_value(item.get("end_time"))
    if start is None:
        return None
    if end is None:
        end = start + 60
    return start, end


def _ranges_overlap(first_start, first_end, second_start, second_end):
    return first_start < second_end and second_start < first_end


def _covers_meal_window(item, window_start, window_end):
    item_range = _item_time_range(item)
    if not item_range:
        return False
    start, end = item_range
    return _ranges_overlap(start, end, window_start, window_end)


def _is_airport_bound_transport(item):
    if item.get("domain") != "transport":
        return False
    text = _item_text(item)
    airport_terms = ("airport", "机场", "航站", "terminal", "lhr", "cdg", "pvg", "pek", "pkx", "sha")
    airport_action_terms = (
        "去机场",
        "到机场",
        "回机场",
        "前往机场",
        "返程",
        "登机",
        "候机",
        "to airport",
        "to cdg",
        "to lhr",
    )
    return any(term in text for term in airport_terms) and (
        any(term in text for term in airport_action_terms)
        or "destination" in text
        or "回" in text
    )


def _meal_window_is_exempt(items, window_start, window_end):
    for item in items:
        if not _covers_meal_window(item, window_start, window_end):
            continue
        if item.get("domain") == "flight":
            return True
        if _is_airport_bound_transport(item):
            return True
    return False


def _meal_window_has_restaurant(items, window_start, window_end):
    return any(
        item.get("domain") == "restaurant"
        and _covers_meal_window(item, window_start, window_end)
        for item in items
    )


def _restaurant_is_in_allowed_meal_window(item):
    item_range = _item_time_range(item)
    if not item_range:
        return False
    start, end = item_range
    meal_windows = (
        (11 * 60, 14 * 60),
        (17 * 60, 20 * 60),
    )
    return any(_ranges_overlap(start, end, window_start, window_end) for window_start, window_end in meal_windows)


def _search_flight_candidate_ids(trace):
    candidate_ids = set()
    for round_trace in trace.get("rounds", []):
        for tool_call in round_trace.get("tool_calls", []):
            if tool_call.get("name") != "search_flights":
                continue
            for candidate in tool_call.get("result", {}).get("candidates", []) or []:
                candidate_id = candidate.get("candidate_id")
                if candidate_id:
                    candidate_ids.add(candidate_id)
    return candidate_ids


def _is_fixed_local_aero_item(item_id, details):
    return (
        isinstance(item_id, str)
        and item_id.startswith("aero-")
        and (
            details.get("source_tool") in {"local_aero_json", "search_flights"}
            or details.get("candidate_id") == item_id
            or details.get("flight_id", "").startswith("aero-")
        )
    )


def validate_final_response_grounding(output_text, trace):
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError:
        return None

    candidate_ids = _search_flight_candidate_ids(trace)
    ungrounded_flights = []
    for item in _iter_plan_items(payload):
        if item.get("domain") != "flight":
            continue

        item_id = item.get("item_id") or ""
        details = item.get("details") or {}
        if details.get("source_tool") == "local_aero_json" and details.get("fixed_by_backend"):
            continue
        if _is_fixed_local_aero_item(item_id, details):
            continue
        if item_id.startswith("tbd-") or details.get("source_tool") != "search_flights":
            ungrounded_flights.append(item_id or item.get("name") or "unnamed flight")
            continue
        if item_id not in candidate_ids:
            ungrounded_flights.append(item_id)

    if not ungrounded_flights:
        return None

    return (
        "Validation feedback: the draft contains flight items that are not grounded "
        f"in search_flights candidates: {', '.join(ungrounded_flights)}. "
        "Before final JSON, call search_flights for each supported outbound/return "
        "flight leg and use the returned candidate_id exactly as item_id. If no "
        "candidate exists, remove the flight item or state that no local demo flight "
        "was found; do not use tbd-flight IDs or invented flight details."
    )


def validate_final_response_completeness(output_text):
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError:
        return None

    problems = []
    if "plan_options" not in payload:
        return None

    plan_options = payload.get("plan_options", []) or []
    if not plan_options:
        problems.append("no plan options were produced")

    for option in plan_options:
        option_number = option.get("plan_option_number", "?")
        days = option.get("plan", []) or []
        if len(days) < 2:
            continue

        items = [
            item
            for day in days
            for item in (day.get("items", []) or [])
        ]
        missing_domains = [
            domain
            for domain in ("hotel", "restaurant", "entertainment", "transport")
            if not _has_domain(items, domain)
        ]
        for day_index, day in enumerate(days, start=1):
            day_items = day.get("items", []) or []
            attractions = [
                item for item in day_items
                if item.get("domain") == "entertainment"
            ]
            if len(attractions) > 3:
                problems.append(
                    f"option {option_number} day {day_index} has more than 3 attractions"
                )
            for item in day_items:
                if item.get("domain") == "restaurant" and not _restaurant_is_in_allowed_meal_window(item):
                    problems.append(
                        f"option {option_number} day {day_index} has restaurant outside lunch/dinner windows"
                    )
            meal_windows = (
                ("lunch", 11 * 60, 14 * 60),
                ("dinner", 17 * 60, 20 * 60),
            )
            for meal_name, window_start, window_end in meal_windows:
                if _meal_window_is_exempt(day_items, window_start, window_end):
                    continue
                if not _meal_window_has_restaurant(day_items, window_start, window_end):
                    problems.append(
                        f"option {option_number} day {day_index} is missing {meal_name} restaurant"
                    )
        if missing_domains:
            problems.append(
                f"option {option_number} is missing required domains: {', '.join(missing_domains)}"
            )
        first_day_items = days[0].get("items", []) or []
        if len(first_day_items) < 2 or {_item.get("domain") for _item in first_day_items} <= {"flight"}:
            problems.append(
                f"option {option_number} first day only has arrival/flight information; add airport transfer and hotel check-in"
            )

    if not problems:
        return None

    return (
        "Validation feedback: the itinerary is incomplete. "
        + "; ".join(problems)
        + ". Before final JSON, repair every plan option so each multi-day non-local trip includes "
        "outbound/return flights, airport transfer, hotel/lodging, restaurants/food, and up to 3 activities/POIs per day. "
        "Add restaurant meals around 11:00-14:00 for lunch and 17:00-20:00 for dinner, about 1 hour each, unless that meal window overlaps a flight or airport-bound transfer. "
        "Do not add late-night, early-morning, or off-window restaurants to compensate for a missed meal. "
        "Remove city transit between attractions. "
        "Use available tools for real candidates when possible. "
        "The backend will inject fixed outbound and return flights from local aero.json."
    )


def validate_response_to_user_copy(output_text):
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError:
        return None

    response_to_user = payload.get("response_to_user")
    if not isinstance(response_to_user, str) or not response_to_user.strip():
        return None

    normalized = response_to_user.casefold()
    leaked_terms = sorted(
        term
        for term in RESPONSE_TO_USER_INTERNAL_TERMS
        if term.casefold() in normalized
    )
    if not leaked_terms:
        return None

    return (
        "文案反馈: response_to_user 是直接展示给最终用户的友好总结，"
        f"不要包含内部实现、字段名、工具名或调试/校验措辞: {', '.join(leaked_terms)}。"
        "请保留完整 JSON 结构和行程内容，只把 response_to_user 重写为自然、亲切、"
        "面向旅行体验的中文建议；不要复述本反馈。"
    )


def validate_final_response(output_text, trace):
    return (
        validate_final_response_grounding(output_text, trace)
        or validate_final_response_completeness(output_text)
        or validate_response_to_user_copy(output_text)
    )


def create_agent_runtime():
    load_env_file()

    from openai import OpenAI

    available_tools = [
        tool
        for tool in load_json("configs/tools.json")
        if tool.get("name") != "search_flights"
    ]
    validate_tool_config(available_tools)
    return {
        "client": OpenAI(),
        "available_tools": available_tools,
        "instructions": load_text(SYSTEM_PROMPT_PATH),
    }


def process_agent_turn(runtime, input_list, trace, user_message, turn_number, show_tools=False):
    input_list.append({"role": "user", "content": user_message})
    force_first_tool_call = needs_relative_date_tool_resolution(user_message)
    force_next_tool_call = False
    turn_instructions = build_turn_instructions(runtime["instructions"], user_message)

    for round_index in range(MAX_TOOL_ROUNDS):
        request = {
            "model": MODEL,
            "instructions": turn_instructions,
            "tools": runtime["available_tools"],
            "input": input_list,
        }
        if force_next_tool_call or (force_first_tool_call and round_index == 0):
            request["tool_choice"] = "required"
            force_next_tool_call = False

        response = runtime["client"].responses.create(
            **request,
        )
        round_trace = {
            "turn": turn_number,
            "round": round_index + 1,
            "user_message": user_message,
            "request": to_jsonable(request),
            "input": to_jsonable(input_list),
            "response": to_jsonable(response),
            "tool_calls": [],
        }
        trace["rounds"].append(round_trace)
        input_list += response.output

        function_calls = [
            item for item in response.output if _item_attr(item, "type") == "function_call"
        ]
        if not function_calls:
            validation_feedback = validate_final_response(response.output_text, trace)
            if validation_feedback:
                round_trace["validation_feedback"] = validation_feedback
                if show_tools:
                    print(colorize(f"\nValidation> {validation_feedback}\n", ANSI_LIGHT_BLUE))
                input_list.append({"role": "user", "content": validation_feedback})
                force_next_tool_call = True
                continue
            return response

        for item in function_calls:
            arguments, raw_arguments, parse_error = _parse_tool_arguments(item)
            tool_name = _item_attr(item, "name")
            if show_tools:
                print(
                    colorize(
                        f"\nTool call> {tool_name}({format_json_for_terminal(arguments)})",
                        ANSI_LIGHT_BLUE,
                    )
                )

            if parse_error:
                result = parse_error
            else:
                result = call_tool(tool_name, arguments)

            if show_tools:
                print(
                    colorize(
                        f"Tool response> {format_json_for_terminal(result)}\n",
                        ANSI_LIGHT_BLUE,
                    )
                )

            round_trace["tool_calls"].append(
                {
                    "call_id": _item_attr(item, "call_id"),
                    "name": tool_name,
                    "raw_arguments": raw_arguments,
                    "arguments": arguments,
                    "result": result,
                }
            )
            input_list.append(
                {
                    "type": "function_call_output",
                    "call_id": _item_attr(item, "call_id"),
                    "output": json.dumps(result, ensure_ascii=False),
                }
            )

    raise RuntimeError("The agent reached the maximum number of tool-call rounds.")


def new_trace(user_message=None, interactive=False):
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "interactive": interactive,
        "user_message": user_message,
        "rounds": [],
    }


def run_agent(user_message, trace_path=DEFAULT_TRACE_PATH):
    runtime = create_agent_runtime()
    input_list = []
    trace = new_trace(user_message=user_message)

    try:
        response = process_agent_turn(
            runtime=runtime,
            input_list=input_list,
            trace=trace,
            user_message=user_message,
            turn_number=1,
        )
        trace["completed_at"] = datetime.now(timezone.utc).isoformat()
        trace["final_input_list"] = to_jsonable(input_list)
        trace["final_response"] = to_jsonable(response)
        return response
    finally:
        trace["last_input_list"] = to_jsonable(input_list)
        write_json(trace_path, trace)


def run_interactive_agent(trace_path=DEFAULT_TRACE_PATH):
    runtime = create_agent_runtime()
    input_list = []
    trace = new_trace(interactive=True)
    turn_number = 0
    last_response = None

    print("Interactive travel agent. Type /exit or /quit to stop.")
    try:
        while True:
            try:
                user_message = input(f"{ANSI_WHITE}You> ").strip()
                print(ANSI_RESET, end="")
            except EOFError:
                print(ANSI_RESET, end="")
                break

            if not user_message:
                continue
            if user_message.lower() in {"/exit", "/quit"}:
                break

            turn_number += 1
            last_response = process_agent_turn(
                runtime=runtime,
                input_list=input_list,
                trace=trace,
                user_message=user_message,
                turn_number=turn_number,
                show_tools=True,
            )
            print(colorize(f"\nAgent> {last_response.output_text}\n", ANSI_GREEN))
            write_output("output.json", last_response.output_text)
            write_output("full_api_response.json", last_response.model_dump_json(indent=2))

            trace["last_response"] = to_jsonable(last_response)
            trace["last_input_list"] = to_jsonable(input_list)
            write_json(trace_path, trace)
    except KeyboardInterrupt:
        print(f"{ANSI_RESET}\nExiting interactive session.")
    finally:
        trace["completed_at"] = datetime.now(timezone.utc).isoformat()
        trace["last_input_list"] = to_jsonable(input_list)
        write_json(trace_path, trace)

    return last_response


if __name__ == "__main__":
    run_interactive_agent()
    # response = run_agent("Plan a trip for me to Paris this weekend.")
    # write_output("output.json", response.output_text)
    # write_output("full_api_response.json", response.model_dump_json(indent=2))
    # print("Full API Response:")
    # print(response.model_dump_json(indent=2))
    
    # print("\n\n\n\nOutput Text:")
    # print("-" * 50)
    # print(response.output_text)
    # print("\nSaved model output to output.md")
