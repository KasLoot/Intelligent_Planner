from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from agent import (
    apply_fixed_flights_to_payload,
    build_agent_message_with_fixed_flights,
    build_fixed_flight_context,
    run_agent,
)


HOST = "127.0.0.1"
PORT = 8000


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
        return payload

    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError:
        parsed = output_text

    return {
        "assumptions": [],
        "plan_options": [],
        "response_to_user": str(parsed),
    }


def handle_message(message: str) -> dict[str, Any]:
    if not message.strip():
        return {
            "assumptions": [],
            "plan_options": [],
            "response_to_user": "Please enter a travel planning request.",
        }

    fixed_flights = build_fixed_flight_context(message)
    agent_message = build_agent_message_with_fixed_flights(message, fixed_flights)
    response = run_agent(agent_message)
    payload = _parse_agent_output(response.output_text)
    result = apply_fixed_flights_to_payload(payload, fixed_flights)

    # Inject origin/destination city for frontend title display
    if fixed_flights:
        result["origin_city"] = fixed_flights.get("origin_city", "")
        result["destination_city"] = fixed_flights.get("destination_city", "")
    else:
        from agent import _extract_city_mentions
        cities = _extract_city_mentions(message)
        if len(cities) >= 2:
            result["origin_city"] = cities[0]
            result["destination_city"] = cities[1]
        elif len(cities) == 1:
            result["destination_city"] = cities[0]

    # Convert English city names to Chinese where available
    from agent import CITY_NAME_ZH
    for key in ("origin_city", "destination_city"):
        city = result.get(key, "")
        if city and city in CITY_NAME_ZH:
            result[key] = CITY_NAME_ZH[city]

    return result


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
            response = handle_message(str(payload.get("message", "")))
            self._send_json(response)
        except Exception as error:
            self._send_json(
                {
                    "assumptions": [],
                    "plan_options": [],
                    "response_to_user": "The agent backend failed while processing this request.",
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
