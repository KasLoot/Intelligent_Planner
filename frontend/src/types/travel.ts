export type PlanDomain =
  | 'flight'
  | 'hotel'
  | 'restaurant'
  | 'entertainment'
  | 'transport';

export interface PlanItem {
  start_time: string | null;
  end_time: string | null;
  domain: PlanDomain;
  item_id: string;
  name: string;
  address: string | null;
  national_phone_number: string | null;
  international_phone_number: string | null;
  rating: number;
  price: number;
  currency: string | null;
  booking_required: boolean;
  notes: string;
  details: Record<string, unknown>;
  time?: string | null;
  location?: string | null;
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
  plan_summary?: string;
  plan: DayPlan[];
}

export interface AgentTravelResponse {
  assumptions: string[];
  plan_options: PlanOption[];
  response_to_user: string;
  trip_summary?: string;
  origin_city?: string;
  destination_city?: string;
}

export type TravelPlan = AgentTravelResponse;

export function isFlightItem(item: PlanItem): item is FlightItem {
  return item.domain === 'flight';
}

export function getPlanItemName(item: PlanItem): string {
  return item.name;
}

export function getPlanItemKind(item: PlanItem): PlanDomain {
  return item.domain;
}

export function getPlanItemTime(item: PlanItem): string | null {
  return item.start_time ?? item.time ?? null;
}

export function formatPlanTime(time: string | null | undefined): string {
  if (!time) return '';

  const normalized = time.trim().toLowerCase();
  if (normalized === 'null' || normalized === 'none' || normalized === 'undefined') {
    return '';
  }

  const isoMatch = time.match(/T(\d{2}:\d{2})/);
  if (isoMatch) return isoMatch[1];

  const timeMatch = time.match(/\b(\d{1,2}:\d{2})\b/);
  if (timeMatch) return timeMatch[1];

  return time;
}

export function getPlanItemTimeLabel(item: PlanItem): string {
  const start = formatPlanTime(item.start_time ?? item.time);
  const end = formatPlanTime(item.end_time);
  if (start && end) return `${start}-${end}`;
  return start;
}

export function getPlanItemLocation(item: PlanItem): string | null {
  return item.address ?? item.location ?? null;
}

export function getAgentResponseText(response: AgentTravelResponse): string {
  return response.response_to_user || response.trip_summary || '';
}

export function hasRenderablePlan(response: AgentTravelResponse): boolean {
  return response.plan_options.some((option) => option.plan.length > 0);
}

export function isAgentTravelResponse(value: unknown): value is AgentTravelResponse {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<AgentTravelResponse>;
  return Array.isArray(candidate.assumptions) && Array.isArray(candidate.plan_options);
}
