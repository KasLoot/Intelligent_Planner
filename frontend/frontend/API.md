# API Contract

## Agent Chat

- Endpoint: `/api/agent/chat`
- Method: `POST`
- Content-Type: `application/json`

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

The frontend is now aligned with the existing Python agent output contract:

```json
{
  "plan_options": [
    {
      "plan_option_number": 1,
      "plan": [
        {
          "date": "2026-05-29",
          "title": "Fly London to Paris",
          "items": [
            {
              "time": "08:00",
              "domain": "flight",
              "item_id": "aero-LHR-CDG-BA123#0",
              "name": "BA123 (LHR to CDG)",
              "location": "London Heathrow (LHR) to Paris Charles de Gaulle (CDG)",
              "price": 150,
              "booking_required": true,
              "notes": "Departs 08:00Z, arrives 09:30Z."
            }
          ]
        }
      ]
    }
  ],
  "assumptions": [],
  "trip_summary": "Recommended option summary."
}
```

### Compatible Wrapped Response

The frontend also accepts string-wrapped responses for compatibility:

```json
{
  "reply": "{\"plan_options\":[],\"assumptions\":[],\"trip_summary\":\"...\"}"
}
```

The wrapper field can be `reply`, `message`, or `content`.

### Local Configuration

Set `VITE_API_BASE_URL` to point at the backend host. If omitted, the frontend uses:

```text
http://localhost:8000
```

If the backend is unavailable, the UI falls back to mock data for travel queries.

### Fuzzy Search Debug Response

For local debugging, messages such as `模糊搜索 Wagas`, `搜索 巴黎`, or `找 酒店` may return:

```json
{
  "reply": "模糊搜索结果摘要",
  "fuzzy_search": {
    "status": "matched",
    "top_match": {},
    "candidates": []
  }
}
```

The status can be `matched`, `ambiguous`, `context_override`, or `no_match`.
