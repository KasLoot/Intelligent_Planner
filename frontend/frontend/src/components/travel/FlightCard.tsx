import { motion } from 'framer-motion';
import type { MouseEvent } from 'react';
import type { FlightItem } from '../../types/travel';

interface FlightCardProps {
  item: FlightItem;
  onAction?: () => void;
  onTap?: () => void;
}

export default function FlightCard({ item, onAction, onTap }: FlightCardProps) {
  const stop = (e: MouseEvent) => e.stopPropagation();
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      onClick={onTap}
      className="bg-[#F8F7FB] rounded-2xl p-3 shadow-sm mb-2 relative cursor-pointer active:scale-[0.99] transition-transform"
    >
      <button
        onClick={(e) => { stop(e); onAction?.(); }}
        aria-label="更多操作"
        className="absolute top-2 right-2 w-11 h-11 flex items-center justify-center text-zinc-400 text-lg"
      >
        ⋯
      </button>

      <div className="font-medium text-zinc-800 pr-8">
        ✈️ {item.name}
      </div>

      <div className="flex justify-between mt-1">
        <span className="text-sm text-zinc-500">{item.time}</span>
        <span className="text-sm font-medium text-zinc-700">¥{item.price}</span>
      </div>

      <div className="flex gap-2 mt-3">
        <button onClick={stop} className="bg-zinc-100 text-zinc-600 px-3 py-1.5 rounded-full text-xs min-h-[32px]">
          更便宜
        </button>
        <button onClick={stop} className="bg-zinc-100 text-zinc-600 px-3 py-1.5 rounded-full text-xs min-h-[32px]">
          更快
        </button>
      </div>
    </motion.div>
  );
}
