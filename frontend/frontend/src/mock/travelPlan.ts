import type { AgentTravelResponse } from '../types/travel';

export const mockTravelPlan: AgentTravelResponse = {
  assumptions: [
    'Mock data follows the backend output contract in configs/system_prompt.md.',
    'The mock uses local demo flight candidates from database/transport/aero.json.',
  ],
  plan_options: [
    {
      plan_option_number: 1,
      plan_summary: 'Earlier outbound and later return, best for more time in Paris.',
      plan: [
        {
          date: '2026-05-29',
          title: 'Fly London to Paris',
          items: [
            {
              start_time: '2026-05-29T08:00:00Z',
              end_time: '2026-05-29T09:30:00Z',
              domain: 'flight',
              item_id: 'aero-LHR-CDG-BA123#0',
              name: 'BA123 (LHR to CDG)',
              address: null,
              national_phone_number: null,
              international_phone_number: null,
              rating: 0,
              price: 150,
              currency: 'GBP',
              booking_required: true,
              notes: 'Departs London Heathrow and arrives at Paris Charles de Gaulle.',
              details: {
                candidate_id: 'aero-LHR-CDG-BA123#0',
                source_tool: 'search_flights',
              },
            },
          ],
        },
        {
          date: '2026-05-31',
          title: 'Return to London',
          items: [
            {
              start_time: '2026-05-31T20:30:00Z',
              end_time: '2026-05-31T22:00:00Z',
              domain: 'flight',
              item_id: 'aero-CDG-LHR-BA124#2',
              name: 'BA124 (CDG to LHR)',
              address: null,
              national_phone_number: null,
              international_phone_number: null,
              rating: 0,
              price: 150,
              currency: 'GBP',
              booking_required: true,
              notes: 'Evening return gives the longest final day.',
              details: {
                candidate_id: 'aero-CDG-LHR-BA124#2',
                source_tool: 'search_flights',
              },
            },
          ],
        },
      ],
    },
    {
      plan_option_number: 2,
      plan_summary: 'Later outbound with a mid-afternoon return, easier pacing.',
      plan: [
        {
          date: '2026-05-29',
          title: 'Fly London to Paris',
          items: [
            {
              start_time: '2026-05-29T13:00:00Z',
              end_time: '2026-05-29T14:30:00Z',
              domain: 'flight',
              item_id: 'aero-LHR-CDG-BA123#1',
              name: 'BA123 (LHR to CDG)',
              address: null,
              national_phone_number: null,
              international_phone_number: null,
              rating: 0,
              price: 150,
              currency: 'GBP',
              booking_required: true,
              notes: 'Early afternoon outbound flight.',
              details: {
                candidate_id: 'aero-LHR-CDG-BA123#1',
                source_tool: 'search_flights',
              },
            },
          ],
        },
        {
          date: '2026-05-31',
          title: 'Return to London',
          items: [
            {
              start_time: '2026-05-31T15:30:00Z',
              end_time: '2026-05-31T17:00:00Z',
              domain: 'flight',
              item_id: 'aero-CDG-LHR-BA124#1',
              name: 'BA124 (CDG to LHR)',
              address: null,
              national_phone_number: null,
              international_phone_number: null,
              rating: 0,
              price: 150,
              currency: 'GBP',
              booking_required: true,
              notes: 'Mid-afternoon return flight.',
              details: {
                candidate_id: 'aero-CDG-LHR-BA124#1',
                source_tool: 'search_flights',
              },
            },
          ],
        },
      ],
    },
  ],
  response_to_user:
    'Option 1 is recommended because it gives you the most usable destination time while keeping the flight plan simple.',
};
