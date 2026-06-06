from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from agent import (
    CITY_NAME_ZH,
    apply_fixed_flights_to_payload,
    build_agent_message_with_fixed_flights,
    build_fixed_flight_context,
    run_agent,
    _extract_city_mentions,
    _extract_trip_days,
)


HOST = "127.0.0.1"
PORT = 8000
SAVED_ITINERARY_PATH = Path("saved_itinerary.json")
CONFIRM_PHRASES = ("就这个吧", "确定", "确认", "可以", "保存", "就按这个", "没问题")
REPLAN_PHRASES = ("需要更改", "重新规划", "重做", "调整", "改一下", "延误", "取消")
_LAST_PLAN: dict[str, Any] | None = None
_SESSIONS: dict[str, dict[str, Any]] = {}


def _find_json_object(text: str) -> str | None:
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        start = text.find("{", start + 1)
    return None


def _load_agent_json(output_text: str) -> dict[str, Any] | None:
    candidates = [output_text.strip()]
    fenced_match = re.search(r"```(?:json)?\s*(.*?)```", output_text, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        candidates.insert(0, fenced_match.group(1).strip())

    embedded = _find_json_object(output_text)
    if embedded:
        candidates.append(embedded)

    for candidate in candidates:
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, str):
            nested = _load_agent_json(payload)
            if nested:
                return nested
        if isinstance(payload, dict):
            return payload
    return None


def _parse_agent_output(output_text: str) -> dict[str, Any]:
    payload = _load_agent_json(output_text)
    if isinstance(payload, dict):
        return _canonicalize_agent_payload(payload)

    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError:
        parsed = output_text

    return _canonicalize_agent_payload({
        "assumptions": [],
        "plan_options": [],
        "response_to_user": str(parsed),
    })


def _has_renderable_plan(payload: dict[str, Any]) -> bool:
    return any(
        isinstance(option, dict)
        and isinstance(option.get("plan"), list)
        and len(option.get("plan", [])) > 0
        for option in payload.get("plan_options", []) or []
    )


def _canonicalize_agent_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if _has_renderable_plan(payload):
        return payload

    for key in ("response_to_user", "trip_summary", "reply", "message", "content"):
        value = payload.get(key)
        if not isinstance(value, str) or "plan_options" not in value:
            continue
        nested = _load_agent_json(value)
        if isinstance(nested, dict) and _has_renderable_plan(nested):
            return _canonicalize_agent_payload(nested)

    return payload


def _empty_response(text: str) -> dict[str, Any]:
    return {"assumptions": [], "plan_options": [], "response_to_user": text}


def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    normalized = text.casefold()
    return any(phrase.casefold() in normalized for phrase in phrases)


def _load_saved_itinerary() -> dict[str, Any] | None:
    if not SAVED_ITINERARY_PATH.exists():
        return None
    try:
        saved = json.loads(SAVED_ITINERARY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(saved, dict):
        return None
    assumptions = saved.get("assumptions")
    if isinstance(assumptions, list):
        saved["assumptions"] = [
            item
            for item in assumptions
            if not (
                isinstance(item, str)
                and any(term in item for term in ("不包含餐厅", "无餐厅", "不安排餐厅"))
            )
        ]
    return saved


def _save_itinerary(plan: dict[str, Any]) -> dict[str, Any]:
    global _LAST_PLAN
    payload = dict(plan)
    payload["saved"] = True
    SAVED_ITINERARY_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _LAST_PLAN = payload
    return payload


def _extract_slots(message: str) -> dict[str, Any]:
    cities = _extract_city_mentions(message)
    if len(cities) == 1:
        city = cities[0]
        zh_city = CITY_NAME_ZH.get(city, city)
        is_origin_only = bool(re.search(rf"(?:从|由)\s*{re.escape(zh_city)}|{re.escape(zh_city)}\s*(?:出发|起飞)", message))
        is_destination_only = bool(re.search(rf"(?:去|到|前往|目的地)\s*{re.escape(zh_city)}", message))
        return {
            "origin": city if is_origin_only and not is_destination_only else None,
            "destination": city if not is_origin_only or is_destination_only else None,
            "trip_days": _extract_trip_days(message),
        }
    return {
        "origin": cities[0] if len(cities) >= 2 else None,
        "destination": cities[1] if len(cities) >= 2 else (cities[0] if len(cities) == 1 else None),
        "trip_days": _extract_trip_days(message),
    }


def _merge_slots(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key in ("origin", "destination", "trip_days"):
        if update.get(key):
            merged[key] = update[key]
    return merged


def _get_session(session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    return _SESSIONS.setdefault(
        session_id,
        {
            "slots": {},
            "history": [],
            "last_plan": None,
        },
    )


def _slot_followup_from_slots(slots: dict[str, Any]) -> dict[str, Any] | None:
    missing = []
    if not slots.get("origin"):
        missing.append("出发地")
    if not slots.get("destination"):
        missing.append("目的地")
    if not slots.get("trip_days"):
        missing.append("旅游天数")
    if not missing:
        return None
    if len(missing) == 3:
        text = "为了给你规划准确行程，请告诉我出发地、目的地和旅游天数。"
    else:
        text = f"还需要补充{'、'.join(missing)}，我拿到这些信息后再为你生成行程。"
    return _empty_response(text)


def _slot_followup(message: str) -> dict[str, Any] | None:
    return _slot_followup_from_slots(_extract_slots(message))


def _build_message_from_slots(message: str, slots: dict[str, Any]) -> str:
    if not slots.get("origin") or not slots.get("destination") or not slots.get("trip_days"):
        return message
    origin = CITY_NAME_ZH.get(slots["origin"], slots["origin"])
    destination = CITY_NAME_ZH.get(slots["destination"], slots["destination"])
    return f"从{origin}到{destination}玩{slots['trip_days']}天。\n用户本轮补充: {message}"


def _item_text(item: dict[str, Any]) -> str:
    details = item.get("details") or {}
    parts = [item.get("name"), item.get("notes"), item.get("address")]
    parts.extend(str(details.get(key) or "") for key in ("origin", "destination", "route_summary"))
    return " ".join(str(part) for part in parts if part).casefold()


def _is_airport_transfer(item: dict[str, Any], day_index: int, day_count: int) -> bool:
    if item.get("domain") != "transport":
        return True
    text = _item_text(item)
    airport_terms = ("airport", "机场", "航站", "terminal", "lhr", "cdg", "pvg", "pek", "pkx", "sha")
    if not any(term in text for term in airport_terms):
        return False
    return day_index == 0 or day_index == day_count - 1


def normalize_itinerary(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    for option in payload.get("plan_options", []) or []:
        days = option.get("plan", []) or []
        for day_index, day in enumerate(days):
            attractions_seen = 0
            normalized_items = []
            for item in day.get("items", []) or []:
                domain = item.get("domain")
                if domain == "transport" and not _is_airport_transfer(item, day_index, len(days)):
                    continue
                if domain == "entertainment":
                    attractions_seen += 1
                    if attractions_seen > 3:
                        continue
                normalized_items.append(item)
            day["items"] = normalized_items
    return payload


def _localize_city_fields(result: dict[str, Any]) -> dict[str, Any]:
    for key in ("origin_city", "destination_city"):
        city = result.get(key, "")
        if city and city in CITY_NAME_ZH:
            result[key] = CITY_NAME_ZH[city]
    return result


def handle_message(
    message: str,
    plan: dict[str, Any] | None = None,
    action: str = "chat",
    session_id: str | None = None,
) -> dict[str, Any]:
    global _LAST_PLAN
    session = _get_session(session_id)
    if not message.strip():
        return _empty_response("请输入你的旅行规划需求。")

    if session is not None:
        session["history"].append({"role": "user", "content": message})

    if action == "save" and plan:
        saved = _save_itinerary(normalize_itinerary(plan))
        saved["response_to_user"] = "好的，已经为你保存这版行程。"
        if session is not None:
            session["last_plan"] = saved
        return saved

    session_plan = session.get("last_plan") if session else None
    if _has_any(message, CONFIRM_PHRASES) and (_LAST_PLAN or plan or session_plan):
        saved = _save_itinerary(normalize_itinerary(plan or session_plan or _LAST_PLAN or {}))
        saved["response_to_user"] = "好的，已经为你保存这版行程。"
        if session is not None:
            session["last_plan"] = saved
        return saved

    working_message = message
    if session is not None and action == "chat" and not _has_any(message, REPLAN_PHRASES):
        session["slots"] = _merge_slots(session.get("slots", {}), _extract_slots(message))
        followup = _slot_followup_from_slots(session["slots"])
        if followup:
            session["history"].append({"role": "agent", "content": followup["response_to_user"]})
            return followup
        working_message = _build_message_from_slots(message, session["slots"])

    fixed_flights = build_fixed_flight_context(working_message)
    saved_plan = _load_saved_itinerary()
    if _has_any(message, REPLAN_PHRASES) and saved_plan:
        history_context = ""
        if session is not None and session.get("history"):
            history_context = (
                "本会话此前对话摘要: "
                + json.dumps(session["history"][-8:], ensure_ascii=False)
                + "\n"
            )
        recovery_context = (
            "系统已读取此前保存的行程。请基于用户新的异常或修改信息生成 Recovery 行程，"
            "必须以此前保存行程为基线调整，不要重新生成一份全新行程。"
            "尽量保留原行程中未受影响的航班、酒店、餐厅和景点，并按新时间节点优化。\n"
            f"{history_context}"
            f"此前保存行程: {json.dumps(saved_plan, ensure_ascii=False)}"
        )
        agent_message = f"{message}\n\n{recovery_context}"
    else:
        if session is None:
            followup = _slot_followup(message)
            if followup:
                return followup
        history_context = ""
        if session is not None and session.get("history"):
            history_context = (
                "\n\n本会话最近对话，必须尊重其中偏好和修改: "
                + json.dumps(session["history"][-8:], ensure_ascii=False)
            )
        agent_message = working_message + history_context

    agent_message = build_agent_message_with_fixed_flights(agent_message, fixed_flights)
    response = run_agent(agent_message)
    payload = _parse_agent_output(response.output_text)
    result = normalize_itinerary(apply_fixed_flights_to_payload(payload, fixed_flights))
    _LAST_PLAN = result
    if session is not None:
        session["last_plan"] = result
        session["history"].append({"role": "agent", "content": result.get("response_to_user", "")})

    # Inject origin/destination city for frontend title display
    if fixed_flights:
        result["origin_city"] = fixed_flights.get("origin_city", "")
        result["destination_city"] = fixed_flights.get("destination_city", "")
    else:
        cities = _extract_city_mentions(working_message)
        if len(cities) >= 2:
            result["origin_city"] = cities[0]
            result["destination_city"] = cities[1]
        elif len(cities) == 1:
            result["destination_city"] = cities[0]

    return _localize_city_fields(result)


class AgentHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        self._send_json({})

    def do_POST(self) -> None:
        if self.path != "/api/agent/chat":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            response = handle_message(
                str(payload.get("message", "")),
                plan=payload.get("plan") if isinstance(payload.get("plan"), dict) else None,
                action=str(payload.get("action", "chat")),
                session_id=str(payload.get("session_id", "")) or None,
            )
            self._send_json(response)
        except Exception as error:
            self._send_json(
                {
                    "assumptions": [],
                    "plan_options": [],
                    "response_to_user": "后端处理行程时遇到问题，请稍后再试。",
                    "error": str(error),
                    "error_type": type(error).__name__,
                },
                status=500,
            )

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), AgentHandler)
    print(f"Serving Agent API at http://{HOST}:{PORT}/api/agent/chat")
    server.serve_forever()


if __name__ == "__main__":
    main()
