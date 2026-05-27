import json
from unittest import mock
import tempfile
import unittest
from pathlib import Path

import llm_api


class RestaurantSearchTests(unittest.TestCase):
    def test_european_near_silicon_way_returns_pasta_palace(self):
        results = llm_api.search_restaurants(
            cuisine_query="European",
            location="London",
            date="2026-05-27",
        )

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Pasta Palace")
        self.assertEqual(results[0]["id"], "restaurant-pasta-palace")
        self.assertLessEqual(len(results), 5)

    def test_italian_directly_returns_pasta_palace(self):
        results = llm_api.search_restaurants(cuisine_query="Italian", location="London")

        self.assertEqual(results[0]["name"], "Pasta Palace")

    def test_broad_recommendation_does_not_require_exact_time_slots(self):
        results = llm_api.search_restaurants(
            cuisine_query="European",
            location="London",
            date="2026-05-27",
        )

        names = {result["name"] for result in results}
        self.assertIn("Pasta Palace", names)

    def test_explicit_available_filter_excludes_required_booking(self):
        results = llm_api.search_restaurants(
            cuisine_query="European",
            location="London",
            booking_preference="available",
        )

        names = {result["name"] for result in results}
        self.assertNotIn("Pasta Palace", names)


class DomainSearchTests(unittest.TestCase):
    def test_google_places_restaurants_are_used_when_configured(self):
        fake_places = {
            "places": [
                {
                    "id": "abc123",
                    "displayName": {"text": "Real Bistro"},
                    "formattedAddress": "10 Example Street, Paris",
                    "rating": 4.6,
                    "priceLevel": "PRICE_LEVEL_MODERATE",
                    "googleMapsUri": "https://maps.google.com/example",
                }
            ]
        }

        with mock.patch.dict("os.environ", {llm_api.GOOGLE_API_KEY_ENV: "fake-key"}):
            with mock.patch("llm_api.request_json", return_value=fake_places) as request_json:
                results = llm_api.search_restaurants(
                    cuisine_query="French",
                    location="Paris",
                    limit=3,
                )

        self.assertEqual(results[0]["name"], "Real Bistro")
        self.assertEqual(results[0]["provider"], "google")
        self.assertEqual(results[0]["price_level"], 2)
        request_json.assert_called_once()

    def test_google_directions_are_used_for_origin_destination_transport(self):
        fake_directions = {
            "status": "OK",
            "routes": [
                {
                    "summary": "Transit route",
                    "legs": [
                        {
                            "start_address": "London",
                            "end_address": "Paris",
                            "duration": {"text": "2 hours 20 mins"},
                            "distance": {"text": "450 km"},
                        }
                    ],
                }
            ],
        }

        with mock.patch.dict("os.environ", {llm_api.GOOGLE_API_KEY_ENV: "fake-key"}):
            with mock.patch("llm_api.request_json", return_value=fake_directions):
                results = llm_api.search_transport(
                    origin="London",
                    destination="Paris",
                    mode="transit",
                )

        self.assertEqual(results[0]["provider"], "google")
        self.assertEqual(results[0]["name"], "Transit route")
        self.assertEqual(results[0]["availability"]["duration"], "2 hours 20 mins")

    def test_unmatched_dates_return_candidates_with_fallback_reason(self):
        flight_results = llm_api.search_flights(
            origin="London",
            destination="Paris",
            departure_date="2026-05-30",
            traveler_count=2,
            limit=2,
        )
        restaurant_results = llm_api.search_restaurants(
            cuisine_query="European",
            location="London",
            date="2026-05-30",
            time="19:00",
            party_size=2,
            limit=2,
        )

        self.assertGreaterEqual(len(flight_results), 1)
        self.assertGreaterEqual(len(restaurant_results), 1)
        self.assertEqual(restaurant_results[0]["name"], "Pasta Palace")
        self.assertIn("no exact mock", " ".join(flight_results[0]["match_reasons"]))
        self.assertIn("no exact mock", " ".join(restaurant_results[0]["match_reasons"]))

    def test_each_search_tool_returns_bounded_candidates(self):
        flight_results = llm_api.search_flights(
            origin="London",
            destination="Paris",
            departure_date="2026-06-05",
            traveler_count=2,
            limit=1,
        )
        hotel_results = llm_api.search_hotels(destination="Paris", guests=2, limit=1)
        entertainment_results = llm_api.search_entertainment(
            destination="Paris",
            date="2026-06-06",
            party_size=2,
            limit=1,
        )
        transport_results = llm_api.search_transport(
            location="Paris",
            date="2026-06-05",
            passengers=2,
            limit=1,
        )

        for results in [flight_results, hotel_results, entertainment_results, transport_results]:
            self.assertEqual(len(results), 1)
            self.assertIn("id", results[0])
            self.assertIn("score", results[0])
            self.assertIn("match_reasons", results[0])
            self.assertIn("constraints_failed", results[0])

    def test_itinerary_requires_confirmation(self):
        itinerary = llm_api.create_itinerary(
            trip_summary="Weekend in Paris",
            selected_items=[{"domain": "flight", "item_id": "flight-lon-par-2026-06-05-morning"}],
        )

        self.assertTrue(itinerary["confirmation_required"])
        self.assertEqual(itinerary["trip_summary"], "Weekend in Paris")

    def test_system_prompt_requires_frontend_json_contract(self):
        self.assertIn("PLAN_TEXT", llm_api.SYSTEM_PROMPT)
        self.assertIn("PLAN_JSON", llm_api.SYSTEM_PROMPT)
        self.assertIn("\"confirmation_required\": true", llm_api.SYSTEM_PROMPT)
        self.assertIn(llm_api.DEFAULT_DEMO_START_DATE, llm_api.SYSTEM_PROMPT)
        self.assertIn("Google Maps Platform", llm_api.SYSTEM_PROMPT)


class BookingTests(unittest.TestCase):
    def test_confirm_booking_without_confirmation_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = Path(tmpdir) / "bookings.json"
            result = llm_api.confirm_booking(
                selected_items=[{"domain": "flight", "item_id": "flight-1", "price": 100}],
                traveler_count=2,
                confirmation_text="please show me the plan",
                ledger_path=ledger,
            )

            self.assertEqual(result["status"], "confirmation_required")
            self.assertFalse(ledger.exists())

    def test_confirm_booking_appends_to_ledger_without_mutating_inventory(self):
        restaurants_before = json.dumps(llm_api.STORE.load("restaurants.json"), sort_keys=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = Path(tmpdir) / "bookings.json"
            result = llm_api.confirm_booking(
                selected_items=[
                    {
                        "domain": "restaurant",
                        "item_id": "restaurant-pasta-palace",
                        "date_time": "2026-06-05T19:00:00",
                        "price": 32,
                    }
                ],
                traveler_count=2,
                confirmation_text="yes, confirm these bookings",
                ledger_path=ledger,
            )

            self.assertEqual(result["status"], "confirmed")
            saved = json.loads(ledger.read_text(encoding="utf-8"))
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["item_id"], "restaurant-pasta-palace")
            self.assertEqual(saved[0]["status"], "confirmed")

        restaurants_after = json.dumps(llm_api.STORE.load("restaurants.json"), sort_keys=True)
        self.assertEqual(restaurants_before, restaurants_after)


if __name__ == "__main__":
    unittest.main()
