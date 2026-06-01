import json
from datetime import datetime, timezone

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


def create_agent_runtime():
    from openai import OpenAI

    available_tools = load_json("configs/tools.json")
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
            validation_feedback = validate_final_response_grounding(response.output_text, trace)
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
