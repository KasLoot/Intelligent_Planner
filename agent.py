import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from tools import call_tool, get_available_tool_names


MODEL = "gpt-5.4-mini"
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
    "Turn hint: resolve relative dates with location/time tools before final JSON. "
    "If origin is omitted, call get_current_location and draft with sensible defaults."
)
TRIP_EDIT_HINT = (
    "Turn hint: this is an edit/follow-up. Preserve the chosen option's full trip "
    "coverage; if adding flights, keep or retrieve lodging, food, POIs, and local transport too."
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
    digit_match = re.search(r"(\d+)\s*(?:天|day|days)", user_message, re.IGNORECASE)
    if digit_match:
        return max(1, int(digit_match.group(1)))
    chinese_match = re.search(r"([一两二三四五六七])\s*天", user_message)
    if chinese_match:
        return CHINESE_DAY_NUMBERS[chinese_match.group(1)]
    return None


def _extract_start_date(user_message):
    date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", user_message)
    if date_match:
        return date.fromisoformat(date_match.group(1))
    return datetime.now().date()


def _flight_item_from_candidate(candidate, direction):
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
            f"Fixed {direction} flight selected from local database/transport/aero.json. "
            "The model should not replace or re-query this flight."
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
    if not fixed_flights:
        return user_message
    return f"{user_message}\n\n{fixed_flights['instruction']}"


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
        "Flights were fixed by the backend from local database/transport/aero.json; "
        "other itinerary details were planned by the agent."
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
    if not hints:
        return base_instructions
    return f"{base_instructions}\n\n" + "\n\n".join(hints)


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
    for option in payload.get("plan_options", []) or []:
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
        if missing_domains:
            problems.append(
                f"option {option_number} is missing required domains: {', '.join(missing_domains)}"
            )
        first_day_items = days[0].get("items", []) or []
        if len(first_day_items) < 2 or {_item.get("domain") for _item in first_day_items} <= {"flight"}:
            problems.append(
                f"option {option_number} first day only has arrival/flight information; add arrival transfer, hotel check-in, and a light meal or nearby activity"
            )

    if not problems:
        return None

    return (
        "Validation feedback: the itinerary is incomplete. "
        + "; ".join(problems)
        + ". Before final JSON, repair every plan option so each multi-day non-local trip includes "
        "outbound transport, arrival/local transfer, hotel/lodging, restaurants/food, activities/POIs, "
        "and local transport between key stops. "
        "Use available tools for real candidates when possible. "
        "The backend will inject fixed outbound and return flights from local aero.json."
    )


def validate_final_response(output_text, trace):
    return (
        validate_final_response_grounding(output_text, trace)
        or validate_final_response_completeness(output_text)
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
        "instructions": load_text("configs/system_prompt.md"),
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
