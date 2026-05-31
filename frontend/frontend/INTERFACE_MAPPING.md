# Frontend / Agent Interface Mapping

This document records the frontend interface names that were changed to match the existing Python agent output contract.

Source of truth:
- Backend final JSON contract: `configs/instructions.md`
- Current sample output: root `output.json`

## Response Envelope

| Frontend before | Backend / aligned name | Notes |
| --- | --- | --- |
| `{ "__structured": true, "data": TravelPlan }` | raw `{ "plan_options": [...], "assumptions": [...], "trip_summary": "..." }` | The frontend now parses the raw agent JSON directly. The old `__structured` mock wrapper is still accepted for compatibility. |
| `TravelPlan` | `AgentTravelResponse` | Renamed frontend type to reflect the real agent response. |
| `title` | derived UI label | The backend does not return a top-level title. The UI now renders a neutral "Trip options" title. |
| `budget` | removed from top-level UI | The backend does not return a top-level budget. Item prices remain on each item. |
| `days` | `plan_options[].plan` | Backend groups days inside each plan option. |

## Plan Option Fields

| Frontend before | Backend / aligned name | Notes |
| --- | --- | --- |
| no option layer | `plan_options[]` | Added option tabs in `TravelPlanCard`. |
| no option number | `plan_option_number` | Rendered as `Option N`. |
| `days[]` | `plan_options[selected].plan[]` | Day tabs now come from the selected option. |

## Day Fields

| Frontend before | Backend / aligned name | Notes |
| --- | --- | --- |
| `day` | removed | Backend does not return a numeric day index. The UI uses array order. |
| `date` | `date` | Kept. |
| no title in type usage | `title` | Day title is now displayed above the timeline. |
| `items` | `items` | Kept. |

## Item Fields

| Frontend before | Backend / aligned name | Notes |
| --- | --- | --- |
| `category` | `domain` | Backend uses `domain` for all items, including `flight`, `hotel`, `restaurant`, `entertainment`, and `transport`. |
| `poi_name` | `name` | Backend uses one `name` field for flights and non-flight items. |
| partial POI-only item | full backend item object | Non-flight items now use the same item shape as flight items. |
| `time` | `time` | Kept, now supports `null`. |
| `item_id` | `item_id` | Kept. |
| `location` | `location` | Kept, now supports `null`. |
| `price` | `price` | Kept. |
| `booking_required` | `booking_required` | Kept. |
| `notes` | `notes` | Kept. |

## Updated Frontend Files

| File | Change |
| --- | --- |
| `src/types/travel.ts` | Replaced old `TravelPlan.days` model with `AgentTravelResponse.plan_options` model. |
| `src/mock/travelPlan.ts` | Mock data now follows the backend `output.json` shape. |
| `src/App.tsx` | API parsing accepts raw agent JSON, wrapped `reply/message/content`, and legacy `__structured` mock payloads. |
| `src/components/travel/TravelPlanCard.tsx` | Added plan option tabs and switched days source to `plan_options[selected].plan`. |
| `src/components/travel/DayTimeline.tsx` | Switched item rendering from `category/poi_name` to `domain/name`. |
| `src/components/travel/POIDetail.tsx` | Switched detail lookup and fallback display from `poi_name/category` to `name/domain`. |
| `src/components/travel/*Card.tsx` | Replaced `item.poi_name` references with `item.name`. |

## Compatibility Notes

- The frontend still falls back to mock data if `/api/agent/chat` is unavailable.
- The frontend accepts the old mock wrapper `{ "__structured": true, "data": ... }`, but new mocks use the backend shape directly.
- Reorder/delete currently mutate the first `plan_options[0]` option in state. Option-specific state can be added later if editing multiple options becomes a product requirement.
