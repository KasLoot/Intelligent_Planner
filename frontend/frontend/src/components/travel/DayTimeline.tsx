import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import type { DayPlan, FlightItem, PlanDomain, PlanItem } from '../../types/travel';
import { getPlanItemKind, getPlanItemName, isFlightItem } from '../../types/travel';
import { findPOIByName, type POI } from '../../data/poiDatabase';

interface DayTimelineProps {
  dayPlan: DayPlan;
  dayIndex: number;
  onActionMenu?: (item: PlanItem, itemIndex: number, dayIndex: number) => void;
  onItemTap?: (item: PlanItem) => void;
  reorderMode?: boolean;
  onMoveItem?: (
    fromDayIndex: number,
    fromItemIndex: number,
    toDayIndex: number,
    toItemIndex: number,
  ) => void;
  totalDays?: number;
}

const TYPE_COLOR: Record<PlanDomain, string> = {
  flight: '#C4B5FD',
  hotel: '#DDD6FE',
  restaurant: '#E9D5FF',
  entertainment: '#D8B4FE',
  transport: '#BFDBFE',
};

function getSubtitle(item: PlanItem): string {
  if (isFlightItem(item)) return `Flight · £${item.price}`;
  return item.location ?? item.notes ?? '';
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5">
      <span className="text-[12.5px] text-zinc-500 flex-shrink-0">{label}</span>
      <span className="text-[13px] text-zinc-700 font-medium text-right break-words min-w-0">
        {value}
      </span>
    </div>
  );
}

function FlightDetail({ item }: { item: FlightItem }) {
  return (
    <div className="divide-y divide-zinc-200/70">
      <DetailRow label="Flight" value={item.name} />
      {item.time && <DetailRow label="Departure" value={item.time} />}
      {item.location && <DetailRow label="Route" value={item.location} />}
      <DetailRow label="Price" value={`£${item.price}`} />
      {item.notes && <DetailRow label="Notes" value={item.notes} />}
    </div>
  );
}

function POIDetailInline({ poi }: { poi: POI }) {
  const cost = poi.average_cost === '0' ? 'Free' : `¥${poi.average_cost}/person`;
  const suitable = poi.suitable_for?.slice(0, 3).join(' · ') ?? '';
  return (
    <div className="divide-y divide-zinc-200/70">
      <DetailRow label="Average cost" value={cost} />
      <DetailRow label="Hours" value={poi.opening_hours} />
      {suitable && <DetailRow label="Best for" value={suitable} />}
      {poi.tags?.length > 0 && (
        <div className="flex items-start justify-between gap-3 py-2">
          <span className="text-[12.5px] text-zinc-500 flex-shrink-0">Tags</span>
          <div className="flex flex-wrap gap-1 justify-end min-w-0">
            {poi.tags.slice(0, 4).map((tag, i) => (
              <span
                key={`${tag}-${i}`}
                className="px-1.5 py-0.5 rounded-md bg-white/70 text-[11px] text-zinc-600 border border-zinc-200/70"
              >
                {tag}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ItemFallback({ item }: { item: PlanItem }) {
  return (
    <div className="divide-y divide-zinc-200/70">
      <DetailRow label="Name" value={item.name} />
      {item.time && <DetailRow label="Time" value={item.time} />}
      <DetailRow label="Type" value={item.domain} />
      {item.location && <DetailRow label="Location" value={item.location} />}
      {item.notes && <DetailRow label="Notes" value={item.notes} />}
    </div>
  );
}

function ExpandedPanel({ item, onCollapse }: { item: PlanItem; onCollapse: () => void }) {
  const poi = !isFlightItem(item) ? findPOIByName(item.name) : null;
  const body = isFlightItem(item)
    ? <FlightDetail item={item} />
    : poi
    ? <POIDetailInline poi={poi} />
    : <ItemFallback item={item} />;

  return (
    <motion.div
      key="expanded"
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: 'auto', opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      transition={{ duration: 0.28, ease: [0.32, 0.72, 0, 1] }}
      className="overflow-hidden"
    >
      <div className="relative bg-zinc-100 px-4 pt-3 pb-9">
        {body}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onCollapse();
          }}
          aria-label="Collapse"
          className="absolute bottom-2 right-2 w-7 h-7 rounded-full bg-white/90 flex items-center justify-center text-zinc-500 hover:bg-white active:scale-95 transition shadow-sm"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="18 15 12 9 6 15" />
          </svg>
        </button>
      </div>
    </motion.div>
  );
}

export default function DayTimeline({
  dayPlan,
  dayIndex,
  onActionMenu,
  reorderMode,
  onMoveItem,
  totalDays = 1,
}: DayTimelineProps) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  const handleToggle = (index: number) => {
    if (reorderMode) return;
    setExpandedIndex((prev) => (prev === index ? null : index));
  };

  const handleMoveUp = (itemIndex: number) => {
    if (itemIndex > 0) {
      onMoveItem?.(dayIndex, itemIndex, dayIndex, itemIndex - 1);
    } else if (dayIndex > 0) {
      onMoveItem?.(dayIndex, itemIndex, dayIndex - 1, -1);
    }
  };

  const handleMoveDown = (itemIndex: number) => {
    if (itemIndex < dayPlan.items.length - 1) {
      onMoveItem?.(dayIndex, itemIndex, dayIndex, itemIndex + 1);
    } else if (dayIndex < totalDays - 1) {
      onMoveItem?.(dayIndex, itemIndex, dayIndex + 1, 0);
    }
  };

  return (
    <motion.div
      className="space-y-3"
      initial="hidden"
      animate="show"
      key={`${dayIndex}-${dayPlan.items.length}`}
    >
      <div className="px-1 text-[13px] font-semibold text-zinc-500">
        {dayPlan.title}
      </div>

      {dayPlan.items.map((item, index) => {
        const kind = getPlanItemKind(item);
        const isExpanded = expandedIndex === index;
        return (
          <motion.div
            key={`${kind}-${item.item_id}-${index}`}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: index * 0.04 }}
            className="flex items-stretch gap-3"
          >
            <div className="w-12 flex-shrink-0 text-right pt-3">
              <span className="text-zinc-400 text-sm tabular-nums">
                {item.time ?? ''}
              </span>
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-stretch gap-2">
                <div
                  className="flex-1 min-w-0 bg-[#F8F7FB] rounded-2xl overflow-hidden"
                  style={{
                    boxShadow: '0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02)',
                  }}
                >
                  <div
                    onClick={() => handleToggle(index)}
                    className="relative z-10 bg-white rounded-2xl flex active:scale-[0.99] transition-transform cursor-pointer"
                  >
                    <div
                      className="w-1 flex-shrink-0 rounded-full my-2 ml-2"
                      style={{ backgroundColor: TYPE_COLOR[kind] }}
                    />
                    <div className="flex-1 min-w-0 px-3 py-3 flex items-center justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-zinc-900 text-[15px] truncate">
                          {getPlanItemName(item)}
                        </div>
                        <div className="text-zinc-500 text-sm truncate mt-0.5">
                          {getSubtitle(item)}
                        </div>
                      </div>
                      {!reorderMode && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onActionMenu?.(item, index, dayIndex);
                          }}
                          aria-label="Actions"
                          className="w-7 h-7 flex-shrink-0 flex items-center justify-center rounded-full text-zinc-400 hover:bg-zinc-50"
                        >
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                            <circle cx="5" cy="12" r="1.6" />
                            <circle cx="12" cy="12" r="1.6" />
                            <circle cx="19" cy="12" r="1.6" />
                          </svg>
                        </button>
                      )}
                    </div>
                  </div>

                  <AnimatePresence initial={false}>
                    {isExpanded && !reorderMode && (
                      <ExpandedPanel
                        item={item}
                        onCollapse={() => setExpandedIndex(null)}
                      />
                    )}
                  </AnimatePresence>
                </div>

                {reorderMode && (
                  <div className="flex flex-col gap-1 flex-shrink-0 justify-center">
                    <button
                      onClick={() => handleMoveUp(index)}
                      disabled={dayIndex === 0 && index === 0}
                      className="w-7 h-7 rounded-full bg-zinc-100 flex items-center justify-center disabled:opacity-30"
                      aria-label="Move up"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="18 15 12 9 6 15" />
                      </svg>
                    </button>
                    <button
                      onClick={() => handleMoveDown(index)}
                      disabled={dayIndex === totalDays - 1 && index === dayPlan.items.length - 1}
                      className="w-7 h-7 rounded-full bg-zinc-100 flex items-center justify-center disabled:opacity-30"
                      aria-label="Move down"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="6 9 12 15 18 9" />
                      </svg>
                    </button>
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        );
      })}

      {dayPlan.items.length === 0 && (
        <div className="text-center text-zinc-400 text-sm py-8">
          No items for this day yet.
        </div>
      )}
    </motion.div>
  );
}
