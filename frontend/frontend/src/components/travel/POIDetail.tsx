import { AnimatePresence, motion } from 'framer-motion';
import type { PlanItem } from '../../types/travel';
import { isFlightItem } from '../../types/travel';
import { findPOIByName, type POI } from '../../data/poiDatabase';

interface POIDetailProps {
  item: PlanItem | null;
  visible: boolean;
  onClose: () => void;
}

const PRICE_LEVEL_MAP: Record<string, string> = {
  free: 'Free',
  low: '¥',
  medium: '¥¥',
  high: '¥¥¥',
};

const CATEGORY_LABEL: Record<string, string> = {
  restaurant: 'Restaurant',
  hotel: 'Hotel',
  attraction: 'Attraction',
  mall: 'Mall',
  entertainment: 'Entertainment',
  transport: 'Transport',
  resting_area: 'Rest area',
};

function getEmoji(category: string): string {
  switch (category) {
    case 'restaurant':
      return '🍜';
    case 'hotel':
      return '🏨';
    case 'attraction':
      return '📍';
    case 'mall':
      return '🛍️';
    case 'entertainment':
      return '🎵';
    case 'flight':
      return '✈️';
    default:
      return '📌';
  }
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2.5 border-b border-zinc-100 last:border-b-0">
      <span className="text-[13px] text-zinc-500 flex-shrink-0">{label}</span>
      <span className="text-[14px] font-medium text-zinc-800 text-right break-words min-w-0">
        {value}
      </span>
    </div>
  );
}

function TagGroup({
  title,
  tags,
  variant = 'default',
}: {
  title: string;
  tags: string[];
  variant?: 'default' | 'good' | 'bad';
}) {
  if (!tags || tags.length === 0) return null;
  const cls =
    variant === 'good'
      ? 'bg-green-50 text-green-700 border border-green-100'
      : variant === 'bad'
      ? 'bg-red-50 text-red-600 border border-red-100'
      : 'bg-meituan-light text-meituan-dark';
  return (
    <section className="mb-5">
      <h4 className="text-[13px] font-semibold text-zinc-500 mb-2">{title}</h4>
      <div className="flex flex-wrap gap-1.5">
        {tags.map((tag, i) => (
          <span
            key={`${tag}-${i}`}
            className={`px-2.5 py-1 rounded-full text-[12px] ${cls}`}
          >
            {tag}
          </span>
        ))}
      </div>
    </section>
  );
}

function POIRichContent({ poi }: { poi: POI }) {
  return (
    <>
      <section className="bg-zinc-50 rounded-2xl px-4 py-3 mb-5">
        <div className="flex items-center gap-2 mb-2">
          <span className="px-2 py-0.5 rounded-md bg-white text-[11px] text-zinc-600 border border-zinc-200">
            {CATEGORY_LABEL[poi.category] || poi.category}
          </span>
          <span className="px-2 py-0.5 rounded-md bg-white text-[11px] text-zinc-600 border border-zinc-200">
            {poi.sub_category}
          </span>
        </div>
        <StatRow label="Price level" value={PRICE_LEVEL_MAP[poi.price_level] || poi.price_level} />
        <StatRow label="Average cost" value={poi.average_cost === '0' ? 'Free' : `¥${poi.average_cost}`} />
        <StatRow label="Hours" value={poi.opening_hours} />
        <StatRow label="Suggested stay" value={`${poi.stay_duration_minutes} min`} />
        <StatRow label="Indoor/outdoor" value={poi.indoor_or_outdoor} />
      </section>

      <TagGroup title="Tags" tags={poi.tags} />
      <TagGroup title="Best for" tags={poi.suitable_for} variant="good" />
      <TagGroup title="Not ideal for" tags={poi.unsuitable_for} variant="bad" />

      <section className="bg-zinc-50 rounded-2xl px-4 py-3 mb-5">
        <h4 className="text-[13px] font-semibold text-zinc-500 mb-1">Access</h4>
        <StatRow label="Transport" value={poi.transport_accessibility} />
        <StatRow label="Crowd" value={poi.crowd_level} />
        <StatRow label="Service speed" value={poi.service_speed} />
      </section>
    </>
  );
}

function FallbackContent({ item }: { item: PlanItem }) {
  return (
    <section className="bg-zinc-50 rounded-2xl px-4 py-3 mb-5">
      <StatRow label="Name" value={item.name} />
      <StatRow label="Type" value={item.domain} />
      <StatRow label="Time" value={item.time ?? '-'} />
      {item.location && <StatRow label="Location" value={item.location} />}
      <StatRow label="Price" value={`${item.price}`} />
      <StatRow label="Booking" value={item.booking_required ? 'Required' : 'Not required'} />
      {item.notes && <StatRow label="Notes" value={item.notes} />}
    </section>
  );
}

export default function POIDetail({ item, visible, onClose }: POIDetailProps) {
  const itemTitle = item?.name ?? '';
  const itemCategory = item?.domain ?? '';
  const poi = item && !isFlightItem(item) ? findPOIByName(item.name) : null;

  return (
    <AnimatePresence>
      {visible && item && (
        <motion.div
          key="poi-detail"
          className="fixed inset-0 z-50 bg-white flex flex-col max-w-[430px] mx-auto"
          initial={{ y: '100%' }}
          animate={{ y: 0 }}
          exit={{ y: '100%' }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
        >
          <header className="flex justify-between items-center px-5 pt-5 pb-3 flex-shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xl flex-shrink-0">{getEmoji(poi?.category || itemCategory)}</span>
              <h2 className="font-bold text-lg text-zinc-900 truncate">{itemTitle}</h2>
            </div>
            <button
              onClick={onClose}
              aria-label="Close"
              className="w-8 h-8 bg-zinc-100 rounded-full flex items-center justify-center text-zinc-500 active:bg-zinc-200 flex-shrink-0"
            >
              ×
            </button>
          </header>

          {poi && (
            <div className="px-5 pb-3 flex-shrink-0">
              <p className="text-[13px] text-zinc-400">
                {CATEGORY_LABEL[poi.category] || poi.category} · {poi.district}
              </p>
            </div>
          )}

          <div className="flex-1 overflow-y-auto px-5 pb-8 hide-scrollbar">
            {poi ? <POIRichContent poi={poi} /> : <FallbackContent item={item} />}

            {!poi && (
              <p className="text-center text-zinc-400 text-[13px] mt-6">
                No additional POI details are available for this item.
              </p>
            )}

            <div className="mt-6 flex gap-3">
              <button
                onClick={onClose}
                className="flex-1 py-3 rounded-full bg-zinc-100 text-zinc-700 text-[14px] font-medium"
              >
                Close
              </button>
              <button className="flex-1 py-3 rounded-full bg-meituan text-white text-[14px] font-medium">
                View map
              </button>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
