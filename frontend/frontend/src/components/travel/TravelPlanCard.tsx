import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import type { AgentTravelResponse, PlanItem } from '../../types/travel';
import DayTimeline from './DayTimeline';

interface TravelPlanCardProps {
  plan: AgentTravelResponse;
  onActionMenu?: (item: PlanItem, itemIndex: number, dayIndex: number) => void;
  onItemTap?: (item: PlanItem) => void;
  reorderMode?: boolean;
  onMoveItem?: (
    fromDayIndex: number,
    fromItemIndex: number,
    toDayIndex: number,
    toItemIndex: number,
  ) => void;
  onExitReorder?: () => void;
}

function formatDateLabel(dateValue: string): string {
  const [, month, day] = dateValue.split('-');
  if (month && day) return `${Number(month)}.${Number(day)}`;
  return dateValue;
}

export default function TravelPlanCard({
  plan,
  onActionMenu,
  onItemTap,
  reorderMode,
  onMoveItem,
  onExitReorder,
}: TravelPlanCardProps) {
  const [selectedOption, setSelectedOption] = useState(0);
  const [selectedDay, setSelectedDay] = useState(0);
  const currentOption = plan.plan_options[selectedOption];
  const days = currentOption?.plan ?? [];

  const dateLabels = useMemo(
    () => days.map((day) => formatDateLabel(day.date)),
    [days],
  );

  const currentDay = days[selectedDay];

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="w-full"
    >
      <div className="px-1 mb-3">
        <h2 className="text-[18px] font-bold text-zinc-900 tracking-tight">
          Trip options
        </h2>
        <div className="flex flex-wrap gap-3 mt-1">
          <span className="text-zinc-900 text-xs">
            {plan.plan_options.length} options
          </span>
          <span className="text-zinc-900 text-xs">{days.length} days</span>
        </div>
      </div>

      {plan.plan_options.length > 1 && (
        <div className="flex gap-2 mb-3 px-1 overflow-x-auto hide-scrollbar">
          {plan.plan_options.map((option, i) => {
            const active = i === selectedOption;
            return (
              <button
                key={option.plan_option_number}
                type="button"
                onClick={() => {
                  setSelectedOption(i);
                  setSelectedDay(0);
                }}
                className={`px-3 h-8 rounded-full text-xs font-semibold transition-all duration-200 ${
                  active
                    ? 'bg-[#7C3AED] text-white shadow-sm'
                    : 'bg-[#F8F7FB] text-zinc-500 hover:bg-[#EDE7F6]/60'
                }`}
              >
                Option {option.plan_option_number}
              </button>
            );
          })}
        </div>
      )}

      <div className="flex items-center justify-between mb-4 px-1">
        <div className="flex items-center gap-3">
          {days.map((_, i) => {
            const active = i === selectedDay;
            return (
              <button
                key={i}
                type="button"
                onClick={() => setSelectedDay(i)}
                className={`w-12 h-12 rounded-full flex items-center justify-center text-sm font-semibold tabular-nums transition-all duration-200 ${
                  active
                    ? 'bg-[#EDE7F6] text-[#5B21B6] shadow-sm'
                    : 'bg-[#F8F7FB] text-zinc-500 hover:bg-[#EDE7F6]/60'
                }`}
                aria-label={`Select day ${i + 1}`}
              >
                {dateLabels[i]}
              </button>
            );
          })}
        </div>

        {reorderMode && (
          <button
            type="button"
            onClick={onExitReorder}
            className="px-3 py-1.5 bg-[#7C3AED] text-white text-xs font-medium rounded-full"
          >
            Done
          </button>
        )}
      </div>

      {currentDay && (
        <DayTimeline
          key={`${selectedOption}-${selectedDay}`}
          dayPlan={currentDay}
          dayIndex={selectedDay}
          totalDays={days.length}
          onActionMenu={onActionMenu}
          onItemTap={onItemTap}
          reorderMode={reorderMode}
          onMoveItem={onMoveItem}
        />
      )}
    </motion.div>
  );
}
