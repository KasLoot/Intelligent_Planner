# API Contract

## Agent Chat

- Endpoint: `/api/agent/chat`
- Method: `POST`
- Content-Type: `application/json`

The backend is the source of truth. The frontend calls this endpoint and accepts the raw JSON object produced by the Python agent.

### Request

```json
{
  "message": "Plan a trip for me to Paris this weekend.",
  "timestamp": 1234567890
}
```

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `message` | string | yes | User message. |
| `timestamp` | number | no | Client request timestamp in milliseconds. |

### Preferred Response

```json
{
  "assumptions": ["string"],
  "plan_options": [
    {
      "plan_option_number": 1,
      "plan_summary": "Short option summary and tradeoff.",
      "plan": [
        {
          "date": "2026-05-29",
          "title": "Fly London to Paris",
          "items": [
            {
              "start_time": "2026-05-29T08:00:00Z",
              "end_time": "2026-05-29T09:30:00Z",
              "domain": "flight",
              "item_id": "aero-LHR-CDG-BA123#0",
              "name": "BA123 (LHR to CDG)",
              "address": null,
              "national_phone_number": null,
              "international_phone_number": null,
              "rating": 0,
              "price": 150,
              "currency": "GBP",
              "booking_required": true,
              "notes": "Departs London Heathrow and arrives at Paris Charles de Gaulle.",
              "details": {
                "candidate_id": "aero-LHR-CDG-BA123#0",
                "source_tool": "search_flights"
              }
            }
          ]
        }
      ]
    }
  ],
  "response_to_user": "Recommended option summary."
}
```

### Compatibility

The frontend still accepts these old wrapper formats:

```json
{
  "reply": "{\"assumptions\":[],\"plan_options\":[],\"response_to_user\":\"...\"}"
}
```

The wrapper field can be `reply`, `message`, or `content`.

Old item fields `time` and `location`, and old top-level `trip_summary`, are tolerated only as fallbacks.

### Local Configuration

Set `VITE_API_BASE_URL` to point at the backend host. If omitted, the frontend uses:

```text
http://localhost:8000
```
