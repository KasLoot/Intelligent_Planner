import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

import type { DayPlan, PlanDomain, PlanItem } from '../../types/travel';
import {
  getPlanItemKind,
  getPlanItemLocation,
  getPlanItemName,
  getPlanItemTimeLabel,
  isFlightItem,
} from '../../types/travel';
import { findPOIByName, type POI } from '../../data/poiDatabase';

interface DayTimelineProps {
  dayPlan: DayPlan;
  dayIndex: number;
  dayTitle?: string;
  onActionMenu?: (item: PlanItem, itemIndex: number, dayIndex: number) => void;
  onItemTap?: (item: PlanItem) => void;
  onNavigate?: () => void;
}

const TYPE_COLOR: Record<PlanDomain, string> = {
  flight: '#C4B5FD',
  hotel: '#DDD6FE',
  restaurant: '#E9D5FF',
  entertainment: '#D8B4FE',
  transport: '#BFDBFE',
};

const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.08 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3 } },
};

function formatPrice(item: PlanItem): string {
  if (!item.price) return '价格未知';
  return `${item.currency ? `${item.currency} ` : ''}${item.price}`;
}

function getSubtitle(item: PlanItem): string {
  if (isFlightItem(item)) return `航班 - ${formatPrice(item)}`;
  return getPlanItemLocation(item) ?? item.notes ?? '';
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

function POIDetailInline({ poi }: { poi: POI }) {
  const cost = poi.average_cost === '0' ? '免费' : `${poi.average_cost}/人`;
  const suitable = poi.suitable_for?.slice(0, 3).join(' - ') ?? '';
  return (
    <div className="divide-y divide-zinc-200/70">
      <DetailRow label="人均消费" value={cost} />
      <DetailRow label="营业时间" value={poi.opening_hours} />
      {suitable && <DetailRow label="适合" value={suitable} />}
      {poi.tags?.length > 0 && (
        <div className="flex items-start justify-between gap-3 py-2">
          <span className="text-[12.5px] text-zinc-500 flex-shrink-0">标签</span>
          <div className="flex flex-wrap gap-1 justify-end min-w-0">
            {poi.tags.slice(0, 4).map((tag, index) => (
              <span
                key={`${tag}-${index}`}
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
  const time = getPlanItemTimeLabel(item);
  const location = getPlanItemLocation(item);
  const domainMap: Record<string, string> = {
    flight: '航班',
    hotel: '酒店',
    restaurant: '餐厅',
    entertainment: '景点',
    transport: '交通',
  };
  return (
    <div className="divide-y divide-zinc-200/70">
      <DetailRow label="名称" value={item.name} />
      {time && <DetailRow label="时间" value={time} />}
      <DetailRow label="类型" value={domainMap[item.domain] ?? item.domain} />
      {location && <DetailRow label="地点" value={location} />}
      <DetailRow label="价格" value={formatPrice(item)} />
      {item.notes && <DetailRow label="备注" value={item.notes} />}
    </div>
  );
}

function ExpandedPanel({
  item,
  onNavigate,
}: {
  item: PlanItem;
  onNavigate?: () => void;
}) {
  const poi = !isFlightItem(item) ? findPOIByName(item.name) : null;
  const body = poi ? <POIDetailInline poi={poi} /> : <ItemFallback item={item} />;

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
          onClick={(event) => {
            event.stopPropagation();
            onNavigate?.();
          }}
          aria-label="Open"
          className="absolute bottom-2 right-2 w-7 h-7 rounded-full bg-white/90 flex items-center justify-center text-zinc-500 hover:bg-white active:scale-95 transition shadow-sm"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="9 6 15 12 9 18" />
          </svg>
        </button>
      </div>
    </motion.div>
  );
}

export default function DayTimeline({
  dayPlan,
  dayIndex,
  dayTitle,
  onActionMenu,
  onNavigate,
}: DayTimelineProps) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  const handleToggle = (index: number) => {
    setExpandedIndex((prev) => (prev === index ? null : index));
  };

  return (
    <motion.div
      className="space-y-3"
      variants={containerVariants}
      initial="hidden"
      animate="show"
      key={dayIndex}
    >
      <div className="px-1 text-[13px] font-semibold text-zinc-500">
        {dayTitle ?? dayPlan.title}
      </div>

      <AnimatePresence initial={false}>
        {dayPlan.items.map((item, index) => {
          const kind = getPlanItemKind(item);
          const isExpanded = expandedIndex === index;
          const timeLabel = getPlanItemTimeLabel(item);
          return (
            <motion.div
              key={`${kind}-${item.item_id}`}
              variants={itemVariants}
              initial={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0, marginBottom: 0, transition: { duration: 0.25, ease: [0.32, 0.72, 0, 1] } }}
              className="flex items-stretch gap-2 overflow-hidden"
            >
            <div className="w-[84px] flex-shrink-0 text-right pt-3">
              <span className={`block text-[13px] tabular-nums whitespace-nowrap ${timeLabel ? 'text-zinc-400' : 'text-zinc-300'}`}>
                {timeLabel || '待定'}
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
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
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
                    </div>
                  </div>

                  <AnimatePresence initial={false}>
                    {isExpanded && <ExpandedPanel item={item} onNavigate={onNavigate} />}
                  </AnimatePresence>
                </div>
              </div>
            </div>
          </motion.div>
          );
        })}
      </AnimatePresence>

      {dayPlan.items.length === 0 && (
        <div className="text-center text-zinc-400 text-sm py-8">
          当天暂无行程项目。
        </div>
      )}
    </motion.div>
  );
}
