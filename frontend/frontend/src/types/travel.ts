export type PlanDomain =
  | 'flight'
  | 'hotel'
  | 'restaurant'
  | 'entertainment'
  | 'transport';

export interface PlanItem {
  time: string | null;
  domain: PlanDomain;
  item_id: string;
  name: string;
  location: string | null;
  price: number;
  booking_required: boolean;
  notes: string;
}

export type FlightItem = PlanItem & { domain: 'flight' };
export type HotelItem = PlanItem & { domain: 'hotel' };
export type RestaurantItem = PlanItem & { domain: 'restaurant' };
export type AttractionItem = PlanItem & { domain: 'entertainment' };

export interface DayPlan {
  date: string;
  title: string;
  items: PlanItem[];
}

export interface PlanOption {
  plan_option_number: number;
  plan: DayPlan[];
}

export interface AgentTravelResponse {
  plan_options: PlanOption[];
  assumptions: string[];
  trip_summary: string;
}

export function isFlightItem(item: PlanItem): item is FlightItem {
  return item.domain === 'flight';
}

export function getPlanItemName(item: PlanItem): string {
  return item.name;
}

export function getPlanItemKind(item: PlanItem): PlanDomain {
  return item.domain;
}

export function isAgentTravelResponse(value: unknown): value is AgentTravelResponse {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<AgentTravelResponse>;
  return Array.isArray(candidate.plan_options);
}
