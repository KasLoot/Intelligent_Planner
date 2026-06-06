import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import api_server


def _bad_model_payload():
    item_base = {
        "start_time": "10:00",
        "end_time": "11:00",
        "address": None,
        "national_phone_number": None,
        "international_phone_number": None,
        "rating": 0,
        "price": 0,
        "currency": None,
        "booking_required": False,
        "notes": "中文说明",
        "details": {},
    }
    return {
        "assumptions": ["中文假设"],
        "plan_options": [
            {
                "plan_option_number": 1,
                "plan_summary": "节奏轻松的中文方案。",
                "plan": [
                    {
                        "date": "2026-07-01",
                        "title": "第一天",
                        "items": [
                            {
                                **item_base,
                                "domain": "flight",
                                "item_id": "mock-flight-out",
                                "name": "BA123",
                            },
                            {
                                **item_base,
                                "domain": "transport",
                                "item_id": "airport-transfer-in",
                                "name": "机场到酒店接驳",
                                "details": {"origin": "CDG Airport", "destination": "酒店"},
                            },
                            {
                                **item_base,
                                "domain": "hotel",
                                "item_id": "hotel-1",
                                "name": "市中心酒店",
                            },
                            {
                                **item_base,
                                "start_time": "12:00",
                                "end_time": "13:00",
                                "domain": "restaurant",
                                "item_id": "restaurant-lunch-1",
                                "name": "午餐餐厅",
                            },
                            {
                                **item_base,
                                "start_time": "18:00",
                                "end_time": "19:00",
                                "domain": "restaurant",
                                "item_id": "restaurant-dinner-1",
                                "name": "晚餐餐厅",
                            },
                            {
                                **item_base,
                                "domain": "transport",
                                "item_id": "metro-1",
                                "name": "地铁换乘",
                                "details": {"origin": "酒店", "destination": "景点"},
                            },
                            *[
                                {
                                    **item_base,
                                    "domain": "entertainment",
                                    "item_id": f"poi-{index}",
                                    "name": f"景点{index}",
                                }
                                for index in range(1, 5)
                            ],
                        ],
                    },
                    {
                        "date": "2026-07-02",
                        "title": "第二天",
                        "items": [
                            {
                                **item_base,
                                "start_time": "12:00",
                                "end_time": "13:00",
                                "domain": "restaurant",
                                "item_id": "restaurant-lunch-2",
                                "name": "午餐餐厅",
                            },
                            {
                                **item_base,
                                "domain": "transport",
                                "item_id": "airport-transfer-out",
                                "name": "酒店到机场接驳",
                                "details": {"origin": "酒店", "destination": "CDG Airport"},
                            },
                            {
                                **item_base,
                                "domain": "flight",
                                "item_id": "mock-flight-back",
                                "name": "BA124",
                            }
                        ],
                    },
                ],
            }
        ],
        "response_to_user": "我给你整理好了这版中文行程。",
    }


def _assert_contract(testcase, payload):
    testcase.assertIsInstance(payload, dict)
    testcase.assertIn("response_to_user", payload)
    testcase.assertRegex(payload["response_to_user"], r"[\u4e00-\u9fff]")
    for option in payload.get("plan_options", []):
        has_restaurant = False
        for day_index, day in enumerate(option.get("plan", [])):
            attractions = 0
            for item in day.get("items", []):
                if item.get("domain") == "restaurant":
                    has_restaurant = True
                if item.get("domain") == "entertainment":
                    attractions += 1
                if item.get("domain") == "transport":
                    text = json.dumps(item, ensure_ascii=False).casefold()
                    testcase.assertIn("airport", text)
                    testcase.assertIn(day_index, {0, len(option.get("plan", [])) - 1})
            testcase.assertLessEqual(attractions, 3)
        testcase.assertTrue(has_restaurant)
        first_items = option.get("plan", [{}])[0].get("items", [])
        last_items = option.get("plan", [{}])[-1].get("items", [])
        if first_items:
            testcase.assertEqual(first_items[0].get("domain"), "flight")
        if last_items:
            testcase.assertEqual(last_items[-1].get("domain"), "flight")


class BusinessContractTests(unittest.TestCase):
    def setUp(self):
        api_server._LAST_PLAN = None
        api_server._SESSIONS.clear()

    def test_ten_inputs_follow_business_contract(self):
        messages = [
            "我想去巴黎玩3天",
            "从伦敦出发玩3天",
            "从伦敦到巴黎",
            "从伦敦到巴黎玩2天",
            "伦敦去北京3天",
            "从北京到上海旅游4天",
            "从伦敦到阿姆斯特丹玩2天",
            "从伦敦到迪拜玩3天",
            "确定",
            "航班延误了，需要更改",
        ]
        saved_path = Path("test_saved_itinerary.json")

        def fake_run_agent(_message):
            return SimpleNamespace(output_text=json.dumps(_bad_model_payload(), ensure_ascii=False))

        with patch.object(api_server, "SAVED_ITINERARY_PATH", saved_path):
            with patch.object(api_server, "run_agent", side_effect=fake_run_agent):
                outputs = [api_server.handle_message(message) for message in messages[:8]]
                api_server._LAST_PLAN = outputs[3]
                outputs.append(api_server.handle_message(messages[8]))
                outputs.append(api_server.handle_message(messages[9]))

        if saved_path.exists():
            saved_path.unlink()

        for output in outputs[:3]:
            self.assertEqual(output["plan_options"], [])
            self.assertRegex(output["response_to_user"], r"[\u4e00-\u9fff]")

        for output in outputs[3:]:
            _assert_contract(self, output)

    def test_fixed_local_aero_flights_are_accepted_by_grounding_validation(self):
        import agent

        payload = {
            "assumptions": [],
            "plan_options": [
                {
                    "plan_option_number": 1,
                    "plan": [
                        {
                            "date": "2026-07-01",
                            "title": "第一天",
                            "items": [
                                {
                                    "domain": "flight",
                                    "item_id": "aero-LHR-CDG-BA123#0",
                                    "details": {
                                        "candidate_id": "aero-LHR-CDG-BA123#0",
                                        "flight_id": "aero-LHR-CDG-BA123",
                                        "source_tool": "local_aero_json",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
            "response_to_user": "中文说明",
        }

        self.assertIsNone(agent.validate_final_response_grounding(json.dumps(payload), {"rounds": []}))

    def test_empty_plan_options_are_not_accepted_as_complete(self):
        import agent

        payload = {
            "assumptions": [],
            "plan_options": [],
            "response_to_user": "中文说明",
        }

        feedback = agent.validate_final_response_completeness(json.dumps(payload, ensure_ascii=False))
        self.assertIsNotNone(feedback)
        self.assertIn("no plan options", feedback)

    def test_saved_itinerary_removes_stale_no_restaurant_assumptions(self):
        saved_path = Path("test_saved_itinerary.json")
        saved_path.write_text(
            json.dumps(
                {
                    "assumptions": ["不包含餐厅，也不安排城市公共交通。", "保留这一条。"],
                    "plan_options": [],
                    "response_to_user": "中文说明",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        try:
            with patch.object(api_server, "SAVED_ITINERARY_PATH", saved_path):
                loaded = api_server._load_saved_itinerary()
        finally:
            saved_path.unlink(missing_ok=True)

        self.assertEqual(loaded["assumptions"], ["保留这一条。"])

    def test_unspecified_trip_date_starts_tomorrow(self):
        import agent
        from datetime import datetime, timedelta

        expected = datetime.now().date() + timedelta(days=1)

        self.assertEqual(agent._extract_start_date("从伦敦到巴黎玩3天"), expected)

    def test_explicit_short_date_range_controls_start_and_length(self):
        import agent
        from datetime import date, datetime

        self.assertEqual(agent._extract_trip_days("从伦敦到巴黎玩6.9-6.14"), 6)
        self.assertEqual(
            agent._extract_start_date("从伦敦到巴黎玩6.9-6.14"),
            date(datetime.now().year, 6, 9),
        )

    def test_missing_lunch_and_dinner_restaurants_are_rejected(self):
        import agent

        payload = {
            "assumptions": [],
            "plan_options": [
                {
                    "plan_option_number": 1,
                    "plan": [
                        {
                            "date": "2026-06-07",
                            "title": "第一天",
                            "items": [
                                {"domain": "hotel", "start_time": "09:00", "end_time": "10:00"},
                                {"domain": "entertainment", "start_time": "10:00", "end_time": "11:00"},
                                {"domain": "restaurant", "start_time": "15:00", "end_time": "16:00"},
                                {"domain": "transport", "start_time": "08:00", "end_time": "09:00", "name": "机场到酒店接驳", "details": {"origin": "CDG Airport", "destination": "酒店"}},
                            ],
                        },
                        {
                            "date": "2026-06-08",
                            "title": "第二天",
                            "items": [
                                {"domain": "hotel", "start_time": "09:00", "end_time": "10:00"},
                                {"domain": "entertainment", "start_time": "10:00", "end_time": "11:00"},
                                {"domain": "restaurant", "start_time": "12:00", "end_time": "13:00"},
                                {"domain": "restaurant", "start_time": "18:00", "end_time": "19:00"},
                                {"domain": "transport", "start_time": "21:00", "end_time": "22:00", "name": "酒店到机场接驳", "details": {"origin": "酒店", "destination": "CDG Airport"}},
                            ],
                        },
                    ],
                }
            ],
            "response_to_user": "中文说明",
        }

        feedback = agent.validate_final_response_completeness(json.dumps(payload, ensure_ascii=False))
        self.assertIn("missing lunch restaurant", feedback)
        self.assertIn("missing dinner restaurant", feedback)
        self.assertIn("restaurant outside lunch/dinner windows", feedback)

    def test_late_night_restaurant_after_exempted_flight_is_rejected(self):
        import agent

        payload = {
            "assumptions": [],
            "plan_options": [
                {
                    "plan_option_number": 1,
                    "plan": [
                        {
                            "date": "2026-06-07",
                            "title": "晚到上海",
                            "items": [
                                {"domain": "flight", "start_time": "11:30", "end_time": "23:50", "name": "BA BA169"},
                                {"domain": "transport", "start_time": "00:10", "end_time": "00:45", "name": "浦东机场到酒店的夜间接驳", "details": {"origin": "PVG Airport", "destination": "酒店"}},
                                {"domain": "hotel", "start_time": "01:00", "end_time": "01:40", "name": "上海酒店"},
                                {"domain": "restaurant", "start_time": "00:55", "end_time": "01:40", "name": "Linlongfang", "details": {"meal": "晚餐/宵夜"}},
                            ],
                        },
                        {
                            "date": "2026-06-08",
                            "title": "正常游览",
                            "items": [
                                {"domain": "hotel", "start_time": "09:00", "end_time": "10:00"},
                                {"domain": "entertainment", "start_time": "10:00", "end_time": "11:00"},
                                {"domain": "restaurant", "start_time": "12:00", "end_time": "13:00"},
                                {"domain": "restaurant", "start_time": "18:00", "end_time": "19:00"},
                                {"domain": "transport", "start_time": "21:00", "end_time": "22:00", "name": "酒店到机场接驳", "details": {"origin": "酒店", "destination": "PVG Airport"}},
                            ],
                        },
                    ],
                }
            ],
            "response_to_user": "中文说明",
        }

        feedback = agent.validate_final_response_completeness(json.dumps(payload, ensure_ascii=False))
        self.assertIn("restaurant outside lunch/dinner windows", feedback)

    def test_meal_windows_can_be_exempted_by_flight_or_airport_transfer(self):
        import agent

        payload = {
            "assumptions": [],
            "plan_options": [
                {
                    "plan_option_number": 1,
                    "plan": [
                        {
                            "date": "2026-06-07",
                            "title": "第一天",
                            "items": [
                                {"domain": "flight", "start_time": "11:30", "end_time": "13:30"},
                                {"domain": "restaurant", "start_time": "18:00", "end_time": "19:00"},
                                {"domain": "hotel", "start_time": "15:00", "end_time": "16:00"},
                                {"domain": "entertainment", "start_time": "16:00", "end_time": "17:00"},
                                {"domain": "transport", "start_time": "14:00", "end_time": "15:00", "name": "机场到酒店接驳", "details": {"origin": "CDG Airport", "destination": "酒店"}},
                            ],
                        },
                        {
                            "date": "2026-06-08",
                            "title": "第二天",
                            "items": [
                                {"domain": "restaurant", "start_time": "12:00", "end_time": "13:00"},
                                {"domain": "transport", "start_time": "17:30", "end_time": "18:30", "name": "酒店到机场接驳", "details": {"origin": "酒店", "destination": "CDG Airport"}},
                                {"domain": "flight", "start_time": "20:00", "end_time": "21:30"},
                                {"domain": "hotel", "start_time": "09:00", "end_time": "10:00"},
                                {"domain": "entertainment", "start_time": "10:00", "end_time": "11:00"},
                            ],
                        },
                    ],
                }
            ],
            "response_to_user": "中文说明",
        }

        feedback = agent.validate_final_response_completeness(json.dumps(payload, ensure_ascii=False))
        self.assertIsNone(feedback)

    def test_api_session_remembers_slots_across_turns(self):
        calls = []

        def fake_run_agent(message):
            calls.append(message)
            return SimpleNamespace(output_text=json.dumps(_bad_model_payload(), ensure_ascii=False))

        with patch.object(api_server, "run_agent", side_effect=fake_run_agent):
            first = api_server.handle_message("我想从伦敦去巴黎", session_id="session-a")
            second = api_server.handle_message("玩3天", session_id="session-a")

        self.assertEqual(first["plan_options"], [])
        self.assertIn("旅游天数", first["response_to_user"])
        self.assertEqual(len(second["plan_options"]), 1)
        self.assertEqual(len(calls), 1)
        self.assertIn("从伦敦到巴黎玩3天", calls[0])

    def test_save_actions_persist_itinerary_and_recovery_uses_it(self):
        saved_path = Path("test_saved_itinerary.json")
        api_server._LAST_PLAN = None
        api_server._SESSIONS.clear()
        sample_plan = {
            "assumptions": ["原始保存行程"],
            "plan_options": [
                {
                    "plan_option_number": 1,
                    "plan_summary": "原方案",
                    "plan": [
                        {
                            "date": "2026-06-07",
                            "title": "原第一天",
                            "items": [
                                {
                                    "domain": "flight",
                                    "item_id": "flight-original",
                                    "name": "BA123",
                                    "start_time": "08:00",
                                    "end_time": "09:30",
                                    "details": {},
                                },
                                {
                                    "domain": "hotel",
                                    "item_id": "hotel-original",
                                    "name": "原酒店",
                                    "start_time": "15:00",
                                    "end_time": "16:00",
                                    "details": {},
                                },
                            ],
                        }
                    ],
                }
            ],
            "response_to_user": "原方案已生成",
        }
        captured_messages = []

        def fake_run_agent(message):
            captured_messages.append(message)
            return SimpleNamespace(output_text=json.dumps(sample_plan, ensure_ascii=False))

        try:
            with patch.object(api_server, "SAVED_ITINERARY_PATH", saved_path):
                saved = api_server.handle_message(
                    "保存行程",
                    plan=sample_plan,
                    action="save",
                    session_id="recovery-session",
                )
                saved_file = json.loads(saved_path.read_text(encoding="utf-8"))

                api_server._LAST_PLAN = sample_plan
                confirmed = api_server.handle_message("确定", session_id="recovery-session")

                with patch.object(api_server, "run_agent", side_effect=fake_run_agent):
                    recovery = api_server.handle_message(
                        "航班延误了，需要更改",
                        session_id="recovery-session",
                    )
        finally:
            saved_path.unlink(missing_ok=True)

        self.assertTrue(saved["saved"])
        self.assertTrue(saved_file["saved"])
        self.assertEqual(confirmed["response_to_user"], "好的，已经为你保存这版行程。")
        self.assertEqual(len(captured_messages), 1)
        prompt = captured_messages[0]
        self.assertIn("此前保存行程", prompt)
        self.assertIn("flight-original", prompt)
        self.assertIn("hotel-original", prompt)
        self.assertIn("必须以此前保存行程为基线调整", prompt)
        self.assertIn("不要重新生成一份全新行程", prompt)
        self.assertTrue(recovery["plan_options"])

    def test_backend_unwraps_json_string_in_response_to_user(self):
        nested = _bad_model_payload()
        bad_outer = {
            "assumptions": [],
            "plan_options": [],
            "response_to_user": json.dumps(nested, ensure_ascii=False),
        }

        parsed = api_server._parse_agent_output(json.dumps(bad_outer, ensure_ascii=False))

        self.assertEqual(len(parsed["plan_options"]), 1)
        self.assertEqual(parsed["response_to_user"], nested["response_to_user"])

    def test_backend_unwraps_embedded_json_text_in_response_to_user(self):
        nested = _bad_model_payload()
        bad_outer = {
            "assumptions": [],
            "plan_options": [],
            "response_to_user": "好的，下面是行程：" + json.dumps(nested, ensure_ascii=False),
        }

        parsed = api_server._parse_agent_output(json.dumps(bad_outer, ensure_ascii=False))

        self.assertEqual(len(parsed["plan_options"]), 1)
        self.assertEqual(parsed["response_to_user"], nested["response_to_user"])


if __name__ == "__main__":
    unittest.main()
