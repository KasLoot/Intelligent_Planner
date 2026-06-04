import json
import re
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import agent
import api_server
import tools


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class GoogleFirstAgentTests(unittest.TestCase):
    def test_tool_config_matches_callable_tools(self):
        configured = {tool["name"] for tool in agent.load_json("configs/tools.json")}
        self.assertEqual(configured, tools.get_available_tool_names())

    def test_system_prompt_uses_current_google_first_tools(self):
        prompt = Path(agent.SYSTEM_PROMPT_PATH).read_text(encoding="utf-8")
        self.assertLessEqual(len(prompt.splitlines()), 90)
        stale_tool_names = [
            "get_current_date",
            "search_pois",
            "fuzzy_search",
            "plan_trip_with_local_data",
            "plan_trip_transport",
        ]
        for name in stale_tool_names:
            self.assertIsNone(re.search(rf"\b{re.escape(name)}\b", prompt))

        self.assertIn('"plan_options": []', prompt)
        self.assertIn("get_lat_lng_from_address", prompt)
        self.assertIn("compute_route", prompt)
        self.assertIn("database/transport/aero.json", prompt)
        self.assertIn("search_flights 只搜索 database/transport/aero.json", prompt)
        self.assertIn("Flight items must come from returned candidates", prompt)
        self.assertIn("set item_id to candidate_id exactly", prompt)
        self.assertIn("Flight search alone is not a complete trip update", prompt)
        self.assertIn("工具解析失败前，不要询问 \"which weekend\"", prompt)
        self.assertIn("默认使用用户当前位置", prompt)
        self.assertIn('"response_to_user"', prompt)
        self.assertIn('"plan_summary"', prompt)
        self.assertIn("正好产出 3 个 plan options", prompt)
        self.assertIn("Option 1 永远是最推荐方案", prompt)
        self.assertIn("行程天数按日期升序排序", prompt)
        self.assertIn("每天 items 按 start_time 排序", prompt)
        self.assertIn("Use \"response_to_user\"; do not use \"trip_summary\"", prompt)
        self.assertIn("先给草案，再让用户细化", prompt)
        self.assertIn("第一版草案前不要询问偏好问题", prompt)
        self.assertIn("preserve the rest of that option", prompt)
        self.assertIn("One-night stay means two calendar days", prompt)
        self.assertIn("priceAmount, priceCurrency, and priceDescription", prompt)
        self.assertIn("Use priceAmount, priceCurrency, and priceDescription when returned", prompt)
        self.assertIn("travel_mode 是必填项", prompt)
        self.assertIn("公共交通用 TRANSIT", prompt)
        self.assertIn("包含 departure_time 或 arrival_time", prompt)
        self.assertIn("完整行程清单", prompt)
        self.assertIn("outbound/return transport", prompt)
        self.assertIn("hotel/lodging", prompt)
        self.assertIn("restaurants/food", prompt)
        self.assertIn("activities/POIs", prompt)
        self.assertIn("local transport", prompt)
        self.assertIn('"details": {}', prompt)
        self.assertIn("Details object guidance", prompt)
        self.assertIn("- transport: include transport_mode", prompt)
        self.assertIn("- hotel: include check_in_date", prompt)
        self.assertIn("- restaurant: include meal", prompt)
        self.assertIn("- entertainment: include activity_type", prompt)
        self.assertIn("- flight: copy candidate_id", prompt)

    def test_places_search_requests_and_normalizes_price_fields(self):
        captured_headers = []

        def fake_post(url, json, headers, timeout):
            captured_headers.append(headers)
            return FakeResponse(
                {
                    "places": [
                        {
                            "displayName": {"text": "Fat Hippo Birmingham"},
                            "priceLevel": "PRICE_LEVEL_MODERATE",
                            "priceRange": {
                                "startPrice": {"currencyCode": "GBP", "units": "10"},
                                "endPrice": {"currencyCode": "GBP", "units": "20"},
                            },
                        },
                        {
                            "displayName": {"text": "Tattu Birmingham"},
                            "priceLevel": "PRICE_LEVEL_EXPENSIVE",
                        },
                    ]
                }
            )

        with patch.object(tools.requests, "post", side_effect=fake_post):
            result = tools.search_by_text("restaurants near Birmingham city centre")

        field_mask = captured_headers[0]["X-Goog-FieldMask"]
        self.assertIn("places.priceLevel", field_mask)
        self.assertIn("places.priceRange", field_mask)
        self.assertEqual(result["places"][0]["priceAmount"], 15)
        self.assertEqual(result["places"][0]["priceCurrency"], "GBP")
        self.assertEqual(
            result["places"][0]["priceDescription"],
            "GBP 10-20 from Google Places priceRange",
        )
        self.assertEqual(
            result["places"][1]["priceDescription"],
            "Google Places price level: expensive",
        )

    def test_compute_route_builds_payload_for_supported_location_types(self):
        captured_payloads = []

        def fake_post(url, json, headers, timeout):
            captured_payloads.append(json)
            return FakeResponse({"routes": []})

        with patch.object(tools.requests, "post", side_effect=fake_post):
            tools.compute_route(
                origin={"latitude": 1.0, "longitude": 2.0},
                destination={"latitude": 3.0, "longitude": 4.0},
                location_input_type="lat_lng",
                travel_mode="DRIVE",
            )
            tools.compute_route(
                origin="1600 Amphitheatre Parkway, Mountain View, CA",
                destination="450 Serra Mall, Stanford, CA 94305, USA",
                location_input_type="address",
                travel_mode="WALK",
                routing_preference=None,
            )
            tools.compute_route(
                origin="origin-place-id",
                destination="destination-place-id",
                location_input_type="id",
                travel_mode="DRIVE",
            )
            tools.compute_route(
                origin="London, UK",
                destination="British Museum, London, UK",
                location_input_type="address",
                travel_mode="TRANSIT",
                departure_time="2026-06-06T09:00:00Z",
            )

        self.assertEqual(
            captured_payloads[0]["origin"]["location"]["latLng"],
            {"latitude": 1.0, "longitude": 2.0},
        )
        self.assertEqual(
            captured_payloads[1]["origin"],
            {"address": "1600 Amphitheatre Parkway, Mountain View, CA"},
        )
        self.assertNotIn("routingPreference", captured_payloads[1])
        self.assertEqual(captured_payloads[1]["travelMode"], "WALK")
        self.assertEqual(captured_payloads[2]["destination"], {"placeId": "destination-place-id"})
        self.assertNotIn("routingPreference", captured_payloads[3])
        self.assertEqual(captured_payloads[3]["travelMode"], "TRANSIT")
        self.assertEqual(captured_payloads[3]["departureTime"], "2026-06-06T09:00:00Z")

    def test_search_flights_uses_aero_json_candidates_for_london_paris(self):
        result = tools.search_flights(
            origin_city="London",
            destination_city="Paris",
            travel_date="2026-06-06",
            max_results=3,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["source_file"], "database/transport/aero.json")
        self.assertGreaterEqual(result["database_total_flights"], result["matched_flight_count"])
        self.assertEqual(result["matched_flight_count"], 1)
        self.assertEqual(result["matched_candidate_count"], 3)
        self.assertEqual(result["returned_count"], 3)
        self.assertLessEqual(len(result["candidates"]), result["max_results"])
        self.assertEqual(result["candidates"][0]["candidate_id"], "aero-LHR-CDG-BA123#0")
        self.assertEqual(result["candidates"][0]["flight_number"], "BA123")
        self.assertEqual(result["candidates"][0]["departure_airport"], "LHR")
        self.assertEqual(result["candidates"][0]["arrival_airport"], "CDG")
        self.assertEqual(result["candidates"][0]["price"], 150.0)

    def test_search_flights_is_bounded_even_with_large_max_results(self):
        result = tools.search_flights(
            origin_city="London",
            destination_city="Paris",
            travel_date="2026-06-06",
            max_results=999,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["max_results"], tools.MAX_FLIGHT_SEARCH_RESULTS)
        self.assertLessEqual(len(result["candidates"]), tools.MAX_FLIGHT_SEARCH_RESULTS)

    def test_search_flights_finds_beijing_dummy_ticket(self):
        result = tools.search_flights(
            origin_city="London",
            destination_city="Beijing",
            travel_date="2026-06-02",
            max_results=5,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["destination_airports"], ["PKX"])
        self.assertEqual(result["matched_flight_count"], 1)
        self.assertEqual(result["candidates"][0]["candidate_id"], "aero-LHR-PKX-BA178#0")
        self.assertEqual(result["candidates"][0]["flight_number"], "BA178")
        self.assertEqual(result["candidates"][0]["arrival_airport"], "PKX")

    def test_search_flights_suggests_supported_country_cities(self):
        result = tools.search_flights(
            origin_city="London",
            destination_city="China",
            travel_date="2026-06-02",
            max_results=5,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["available_cities_for_country"], ["Beijing", "Shanghai"])
        self.assertIn("available China cities", result["hint"])

    def test_api_parser_extracts_embedded_json_instead_of_returning_raw_text(self):
        raw_output = (
            "好的，下面是行程 JSON：\n"
            '{"assumptions":[],"plan_options":[{"plan_option_number":1,'
            '"plan":[{"date":"2026-06-08","title":"Day 1","items":[]}]}],'
            '"response_to_user":"已生成行程。"}'
        )

        payload = api_server._parse_agent_output(raw_output)

        self.assertEqual(payload["response_to_user"], "已生成行程。")
        self.assertEqual(len(payload["plan_options"]), 1)

    def test_compute_route_requests_transit_times(self):
        captured_headers = []

        def fake_post(url, json, headers, timeout):
            captured_headers.append(headers)
            return FakeResponse({"routes": []})

        with patch.object(tools.requests, "post", side_effect=fake_post):
            tools.compute_route(
                origin="London, UK",
                destination="Birmingham New Street, Birmingham, UK",
                location_input_type="address",
                travel_mode="TRANSIT",
                arrival_time="2026-06-06T12:00:00Z",
            )

        field_mask = captured_headers[0]["X-Goog-FieldMask"]
        self.assertNotIn("polyline", field_mask)
        self.assertNotIn("encodedPolyline", field_mask)
        self.assertIn("routes.legs.steps.transitDetails.stopDetails.departureTime", field_mask)
        self.assertIn("routes.legs.steps.transitDetails.stopDetails.arrivalTime", field_mask)
        self.assertIn("routes.legs.steps.transitDetails.localizedValues.departureTime", field_mask)
        self.assertIn("routes.legs.steps.transitDetails.localizedValues.arrivalTime", field_mask)

    def test_compute_route_rejects_both_departure_and_arrival_time(self):
        result = tools.call_tool(
            "compute_route",
            {
                "origin": "London, UK",
                "destination": "Birmingham New Street, Birmingham, UK",
                "location_input_type": "address",
                "travel_mode": "TRANSIT",
                "departure_time": "2026-06-06T09:00:00Z",
                "arrival_time": "2026-06-06T12:00:00Z",
            },
        )

        self.assertFalse(result["ok"])
        self.assertIn("either departure_time or arrival_time", result["error"])

    def test_compute_route_schema_requires_travel_mode(self):
        compute_route_schema = next(
            tool for tool in agent.load_json("configs/tools.json")
            if tool["name"] == "compute_route"
        )

        self.assertIn("TRANSIT", compute_route_schema["parameters"]["properties"]["travel_mode"]["enum"])
        self.assertIn("travel_mode", compute_route_schema["parameters"]["required"])
        self.assertIn("departure_time", compute_route_schema["parameters"]["properties"])
        self.assertIn("arrival_time", compute_route_schema["parameters"]["properties"])

    def test_geocode_and_current_datetime_helpers(self):
        def fake_get(url, headers, timeout):
            self.assertIn("1600%20Amphitheatre%20Parkway", url)
            return FakeResponse({"location": {"latitude": 37.422, "longitude": -122.084}})

        with patch.object(tools.requests, "get", side_effect=fake_get):
            geocode_result = tools.get_lat_lng_from_address(
                "1600 Amphitheatre Parkway, Mountain View, CA"
            )

        self.assertEqual(geocode_result["location"]["latitude"], 37.422)

        with patch.object(
            tools,
            "get_time_zone",
            return_value={
                "status": "OK",
                "timeZoneId": "Europe/London",
                "timeZoneName": "British Summer Time",
                "rawOffset": 0,
                "dstOffset": 3600,
            },
        ):
            datetime_result = tools.get_current_datetime_for_location(51.5, -0.01)

        self.assertTrue(datetime_result["ok"])
        self.assertEqual(datetime_result["timezone"], "Europe/London")
        self.assertIn("current_date", datetime_result)
        self.assertIn("current_time", datetime_result)

    def test_call_tool_returns_structured_errors(self):
        unknown = tools.call_tool("missing_tool")
        self.assertFalse(unknown["ok"])
        self.assertIn("Unknown tool", unknown["error"])

        failed = tools.call_tool(
            "compute_route",
            {
                "origin": "a",
                "destination": "b",
                "location_input_type": "address",
                "travel_mode": "BIKE",
            },
        )
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["error_type"], "ValueError")
        self.assertEqual(failed["tool"], "compute_route")

    def test_run_agent_writes_debug_trace_for_tool_calls(self):
        class FakeItem:
            def __init__(self, item_type, **kwargs):
                self.type = item_type
                for key, value in kwargs.items():
                    setattr(self, key, value)

            def model_dump(self, mode="json"):
                return self.__dict__

        class FakeModelResponse:
            def __init__(self, output, output_text=""):
                self.output = output
                self.output_text = output_text

            def model_dump(self, mode="json"):
                return {"output": [item.model_dump(mode=mode) for item in self.output]}

            def model_dump_json(self, indent=None):
                return json.dumps(self.model_dump(), indent=indent)

        class FakeResponses:
            def __init__(self):
                self.calls = 0

            def create(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return FakeModelResponse(
                        [
                            FakeItem(
                                "function_call",
                                name="get_lat_lng_from_address",
                                arguments='{"address": "Paris, France"}',
                                call_id="call_1",
                            )
                        ]
                    )
                return FakeModelResponse([FakeItem("message", content=[])], "{}")

        class FakeClient:
            def __init__(self):
                self.responses = FakeResponses()

        fake_openai_module = types.SimpleNamespace(OpenAI=lambda: FakeClient())

        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "trace.json"
            with patch.dict(sys.modules, {"openai": fake_openai_module}):
                with patch.object(
                    agent,
                    "call_tool",
                    return_value={"ok": True, "location": {"latitude": 48.8566, "longitude": 2.3522}},
                ):
                    response = agent.run_agent("Plan Paris", trace_path=str(trace_path))

            trace = json.loads(trace_path.read_text(encoding="utf-8"))

        self.assertEqual(response.output_text, "{}")
        self.assertEqual(len(trace["rounds"]), 2)
        self.assertEqual(trace["rounds"][0]["tool_calls"][0]["name"], "get_lat_lng_from_address")
        self.assertTrue(trace["rounds"][0]["tool_calls"][0]["result"]["ok"])
        self.assertIn("final_input_list", trace)

    def test_interactive_agent_preserves_context_between_terminal_inputs(self):
        class FakeItem:
            def __init__(self, item_type, **kwargs):
                self.type = item_type
                for key, value in kwargs.items():
                    setattr(self, key, value)

            def model_dump(self, mode="json"):
                return self.__dict__

        class FakeModelResponse:
            def __init__(self, text):
                self.output = [FakeItem("message", content=[{"text": text}])]
                self.output_text = text

            def model_dump(self, mode="json"):
                return {"output": [item.model_dump(mode=mode) for item in self.output]}

            def model_dump_json(self, indent=None):
                return json.dumps(self.model_dump(), indent=indent)

        class FakeResponses:
            def __init__(self):
                self.inputs = []

            def create(self, **kwargs):
                self.inputs.append(list(kwargs["input"]))
                return FakeModelResponse(f"response {len(self.inputs)}")

        fake_responses = FakeResponses()

        class FakeClient:
            def __init__(self):
                self.responses = fake_responses

        fake_openai_module = SimpleNamespace(OpenAI=lambda: FakeClient())

        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "interactive_trace.json"
            with patch.dict(sys.modules, {"openai": fake_openai_module}):
                with patch("builtins.input", side_effect=["Plan Paris", "From London", "/exit"]):
                    with patch("builtins.print"):
                        with patch.object(agent, "write_output"):
                            response = agent.run_interactive_agent(trace_path=str(trace_path))

            trace = json.loads(trace_path.read_text(encoding="utf-8"))

        self.assertEqual(response.output_text, "response 2")
        self.assertEqual(len(fake_responses.inputs), 2)
        self.assertEqual(fake_responses.inputs[0], [{"role": "user", "content": "Plan Paris"}])
        self.assertEqual(fake_responses.inputs[1][-1], {"role": "user", "content": "From London"})
        self.assertEqual(fake_responses.inputs[1][1].type, "message")
        self.assertTrue(trace["interactive"])
        self.assertEqual(len(trace["rounds"]), 2)

    def test_relative_date_turn_requires_first_tool_call(self):
        class FakeItem:
            type = "message"

            def model_dump(self, mode="json"):
                return {"type": self.type, "content": []}

        class FakeResponse:
            output = [FakeItem()]
            output_text = "{}"

            def model_dump(self, mode="json"):
                return {"output": [item.model_dump(mode=mode) for item in self.output]}

        class FakeResponses:
            def __init__(self):
                self.requests = []

            def create(self, **kwargs):
                self.requests.append(kwargs)
                return FakeResponse()

        responses = FakeResponses()
        runtime = {
            "client": SimpleNamespace(responses=responses),
            "available_tools": [],
            "instructions": "test",
        }
        trace = {"rounds": []}
        input_list = []

        agent.process_agent_turn(
            runtime,
            input_list,
            trace,
            "I want to travel to Birmingham this weekend",
            1,
        )

        self.assertEqual(responses.requests[0]["tool_choice"], "required")
        self.assertEqual(trace["rounds"][0]["request"]["tool_choice"], "required")
        self.assertIn("先用位置/时间工具解析相对日期", responses.requests[0]["instructions"])
        self.assertIn("调用 get_current_location", responses.requests[0]["instructions"])
        self.assertIn("基于合理默认值起草", responses.requests[0]["instructions"])

    def test_option_flight_followup_preserves_full_trip_context(self):
        class FakeItem:
            type = "message"

            def model_dump(self, mode="json"):
                return {"type": self.type, "content": []}

        class FakeResponse:
            output = [FakeItem()]
            output_text = "{}"

            def model_dump(self, mode="json"):
                return {"output": [item.model_dump(mode=mode) for item in self.output]}

        class FakeResponses:
            def __init__(self):
                self.requests = []

            def create(self, **kwargs):
                self.requests.append(kwargs)
                return FakeResponse()

        responses = FakeResponses()
        runtime = {
            "client": SimpleNamespace(responses=responses),
            "available_tools": [],
            "instructions": "base instructions",
        }
        trace = {"rounds": []}
        input_list = []

        agent.process_agent_turn(
            runtime,
            input_list,
            trace,
            "Search flight to China for option 1.",
            1,
        )

        instructions = responses.requests[0]["instructions"]
        self.assertIn("保留用户所选 option 的完整行程覆盖范围", instructions)
        self.assertIn("保留或重新获取住宿、餐饮、POI 和本地交通", instructions)

    def test_ungrounded_flight_draft_forces_search_flights_retry(self):
        class FakeMessage:
            type = "message"

            def model_dump(self, mode="json"):
                return {"type": self.type, "content": []}

        class FakeFunctionCall:
            type = "function_call"
            name = "search_flights"
            call_id = "call_1"
            arguments = json.dumps(
                {
                    "origin_city": "London",
                    "destination_city": "Beijing",
                    "travel_date": "2026-06-08",
                }
            )

            def model_dump(self, mode="json"):
                return {
                    "type": self.type,
                    "name": self.name,
                    "call_id": self.call_id,
                    "arguments": self.arguments,
                }

        class FakeResponse:
            def __init__(self, output, output_text):
                self.output = output
                self.output_text = output_text

            def model_dump(self, mode="json"):
                return {"output": [item.model_dump(mode=mode) for item in self.output]}

        class FakeResponses:
            def __init__(self):
                self.requests = []
                self.responses = [
                    FakeResponse(
                        [FakeMessage()],
                        json.dumps(
                            {
                                "assumptions": [],
                                "plan_options": [
                                    {
                                        "plan_option_number": 1,
                                        "plan_summary": "Draft",
                                        "plan": [
                                            {
                                                "date": "2026-06-08",
                                                "title": "Depart",
                                                "items": [
                                                    {
                                                        "domain": "flight",
                                                        "item_id": "tbd-flight-outbound",
                                                        "details": {},
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                                "response_to_user": "Draft",
                            }
                        ),
                    ),
                    FakeResponse([FakeFunctionCall()], ""),
                    FakeResponse(
                        [FakeMessage()],
                        json.dumps(
                            {
                                "assumptions": [],
                                "plan_options": [
                                    {
                                        "plan_option_number": 1,
                                        "plan_summary": "Grounded",
                                        "plan": [
                                            {
                                                "date": "2026-06-08",
                                                "title": "Depart",
                                                "items": [
                                                    {
                                                        "domain": "flight",
                                                        "item_id": "aero-LHR-PKX-BA178#0",
                                                        "details": {
                                                            "source_tool": "search_flights"
                                                        },
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                                "response_to_user": "Grounded",
                            }
                        ),
                    ),
                ]

            def create(self, **kwargs):
                self.requests.append(kwargs)
                return self.responses.pop(0)

        responses = FakeResponses()
        runtime = {
            "client": SimpleNamespace(responses=responses),
            "available_tools": [{"name": "search_flights"}],
            "instructions": "base instructions",
        }
        trace = {"rounds": []}
        input_list = []
        tool_result = {
            "ok": True,
            "candidates": [
                {
                    "candidate_id": "aero-LHR-PKX-BA178#0",
                    "flight_number": "BA178",
                }
            ],
        }

        with patch.object(agent, "call_tool", return_value=tool_result) as call_tool:
            response = agent.process_agent_turn(
                runtime,
                input_list,
                trace,
                "Plan a week trip to China",
                1,
            )

        self.assertIn("aero-LHR-PKX-BA178#0", response.output_text)
        self.assertEqual(len(responses.requests), 3)
        self.assertIn("validation_feedback", trace["rounds"][0])
        self.assertEqual(responses.requests[1]["tool_choice"], "required")
        call_tool.assert_called_once_with(
            "search_flights",
            {
                "origin_city": "London",
                "destination_city": "Beijing",
                "travel_date": "2026-06-08",
            },
        )


if __name__ == "__main__":
    unittest.main()
