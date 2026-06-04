import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import type { AgentTravelResponse, PlanItem } from '../../types/travel';
import DayTimeline from './DayTimeline';

interface TravelPlanCardProps {
  plan: AgentTravelResponse;
  onActionMenu?: (item: PlanItem, itemIndex: number, dayIndex: number) => void;
  onItemTap?: (item: PlanItem) => void;
  onSavePlan?: () => void;
  onReplan?: () => void;
  onNavigate?: () => void;
}

function formatDateLabel(dateValue: string): string {
  const [, month, day] = dateValue.split('-');
  if (month && day) return `${Number(month)}.${Number(day)}`;
  return dateValue;
}

function isTodayOrTomorrow(dateStr: string): boolean {
  const d = new Date(dateStr + 'T00:00:00');
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diffDays = Math.round((d.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
  return diffDays === 0 || diffDays === 1;
}

function areDatesGeneric(days: { date: string }[]): boolean {
  if (days.length === 0) return true;
  if (!isTodayOrTomorrow(days[0].date)) return false;
  for (let i = 1; i < days.length; i++) {
    const prev = new Date(days[i - 1].date + 'T00:00:00');
    const curr = new Date(days[i].date + 'T00:00:00');
    const diff = Math.round((curr.getTime() - prev.getTime()) / (1000 * 60 * 60 * 24));
    if (diff !== 1) return false;
  }
  return true;
}


export default function TravelPlanCard({
  plan,
  onActionMenu,
  onItemTap,
  onSavePlan,
  onReplan,
  onNavigate,
}: TravelPlanCardProps) {
  const [selectedOption, setSelectedOption] = useState(0);
  const [selectedDay, setSelectedDay] = useState(0);
  const [saved, setSaved] = useState(false);
  const currentOption = plan.plan_options[selectedOption];
  const days = currentOption?.plan ?? [];

  const useGenericLabels = useMemo(() => areDatesGeneric(days), [days]);

  const dateLabels = useMemo(
    () => days.map((day, index) =>
      useGenericLabels ? `D${index + 1}` : formatDateLabel(day.date),
    ),
    [days, useGenericLabels],
  );

  const dayTitles = useMemo(
    () => days.map((day, index) =>
      useGenericLabels ? `Day ${index + 1}` : day.title,
    ),
    [days, useGenericLabels],
  );

  const currentDay = days[selectedDay];

  const handleSave = () => {
    setSaved(true);
    onSavePlan?.();
  };

  const handleReplan = () => {
    setSaved(true);
    onReplan?.();
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="w-full"
    >
      <div className="px-1 mb-3">
        <h2 className="text-[18px] font-bold text-zinc-900 tracking-tight">
          行程方案
        </h2>
        <div className="flex flex-wrap gap-3 mt-1">
          <span className="text-zinc-900 text-xs">{plan.plan_options.length} 个方案</span>
          <span className="text-zinc-900 text-xs">{days.length} 天</span>
        </div>
        {currentOption?.plan_summary && (
          <p className="text-xs text-zinc-500 mt-2 leading-relaxed">
            {currentOption.plan_summary}
          </p>
        )}
      </div>

      {plan.plan_options.length > 1 && (
        <div className="flex gap-2 mb-3 px-1 overflow-x-auto hide-scrollbar">
          {plan.plan_options.map((option, index) => {
            const active = index === selectedOption;
            return (
              <button
                key={option.plan_option_number}
                type="button"
                onClick={() => {
                  setSelectedOption(index);
                  setSelectedDay(0);
                }}
                className={`px-3 h-8 rounded-full text-xs font-semibold transition-all duration-200 ${
                  active
                    ? 'bg-[#7C3AED] text-white shadow-sm'
                    : 'bg-[#F8F7FB] text-zinc-500 hover:bg-[#EDE7F6]/60'
                }`}
              >
                方案 {option.plan_option_number}
              </button>
            );
          })}
        </div>
      )}

      <div className="flex items-center justify-between mb-4 px-1">
        <div className="flex items-center gap-3">
          {days.map((_, index) => {
            const active = index === selectedDay;
            return (
              <button
                key={index}
                type="button"
                onClick={() => setSelectedDay(index)}
                className={`w-12 h-12 rounded-full flex items-center justify-center text-sm font-semibold tabular-nums transition-all duration-200 ${
                  active
                    ? 'bg-[#EDE7F6] text-[#5B21B6] shadow-sm'
                    : 'bg-[#F8F7FB] text-zinc-500 hover:bg-[#EDE7F6]/60'
                }`}
                aria-label={`Select day ${index + 1}`}
              >
                {dateLabels[index]}
              </button>
            );
          })}
        </div>
      </div>

      {currentDay && (
        <DayTimeline
          key={`${selectedOption}-${selectedDay}`}
          dayPlan={currentDay}
          dayIndex={selectedDay}
          dayTitle={dayTitles[selectedDay]}
          onActionMenu={onActionMenu}
          onItemTap={onItemTap}
          onNavigate={onNavigate}
        />
      )}

      {!saved && (
        <div className="flex items-center gap-3 mt-5 pb-2">
          <button
            type="button"
            onClick={handleSave}
            className="flex-1 h-11 rounded-full bg-zinc-800 text-white text-[15px] font-medium transition-opacity active:opacity-80"
          >
            保存行程
          </button>
          <button
            type="button"
            onClick={handleReplan}
            className="w-[108px] h-11 rounded-full bg-white text-black text-[15px] font-medium border border-zinc-300 transition-opacity active:opacity-80"
          >
            重新规划
          </button>
        </div>
      )}
    </motion.div>
  );
}
