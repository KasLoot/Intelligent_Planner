import type { AgentTravelResponse } from '../types/travel';

export const mockTravelPlan: AgentTravelResponse = {
  plan_options: [
    {
      plan_option_number: 1,
      plan: [
        {
          date: '2026-05-29',
          title: 'Fly London to Paris (AM start)',
          items: [
            {
              time: '08:00',
              domain: 'flight',
              item_id: 'aero-LHR-CDG-BA123#0',
              name: 'BA123 (LHR to CDG)',
              location: 'London Heathrow (LHR) to Paris Charles de Gaulle (CDG)',
              price: 150,
              booking_required: true,
              notes: 'Departs 08:00Z, arrives 09:30Z. Baggage 23kg; meal included.',
            },
          ],
        },
        {
          date: '2026-05-31',
          title: 'Fly Paris to London (evening return)',
          items: [
            {
              time: '20:30',
              domain: 'flight',
              item_id: 'aero-CDG-LHR-BA124#2',
              name: 'BA124 (CDG to LHR)',
              location: 'Paris Charles de Gaulle (CDG) to London Heathrow (LHR)',
              price: 150,
              booking_required: true,
              notes: 'Departs 20:30Z, arrives 22:00Z. Baggage 23kg; meal included.',
            },
          ],
        },
      ],
    },
    {
      plan_option_number: 2,
      plan: [
        {
          date: '2026-05-29',
          title: 'Fly London to Paris (early afternoon)',
          items: [
            {
              time: '13:00',
              domain: 'flight',
              item_id: 'aero-LHR-CDG-BA123#1',
              name: 'BA123 (LHR to CDG)',
              location: 'London Heathrow (LHR) to Paris Charles de Gaulle (CDG)',
              price: 150,
              booking_required: true,
              notes: 'Departs 13:00Z, arrives 14:30Z. Baggage 23kg; meal included.',
            },
          ],
        },
        {
          date: '2026-05-31',
          title: 'Fly Paris to London (mid-afternoon return)',
          items: [
            {
              time: '15:30',
              domain: 'flight',
              item_id: 'aero-CDG-LHR-BA124#1',
              name: 'BA124 (CDG to LHR)',
              location: 'Paris Charles de Gaulle (CDG) to London Heathrow (LHR)',
              price: 150,
              booking_required: true,
              notes: 'Departs 15:30Z, arrives 17:00Z. Baggage 23kg; meal included.',
            },
          ],
        },
      ],
    },
  ],
  assumptions: [
    'Mock data follows the backend output contract in configs/instructions.md.',
    'Only transport items are included because hotel and POI tools are not available in the Python agent yet.',
  ],
  trip_summary:
    'Here are two mock transport options using the same plan_options structure produced by the Python agent. Option 1 is recommended for more destination time.',
};
