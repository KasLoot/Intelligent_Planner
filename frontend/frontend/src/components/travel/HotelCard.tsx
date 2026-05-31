import { motion } from 'framer-motion';
import type { MouseEvent } from 'react';
import type { HotelItem } from '../../types/travel';

interface HotelCardProps {
  item: HotelItem;
  onAction?: () => void;
  onTap?: () => void;
}

export default function HotelCard({ item, onAction, onTap }: HotelCardProps) {
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
        �?      </button>

      <div className="font-medium text-zinc-800 pr-8">
        🏨 {item.name}
      </div>

      {/* 已删�?rating / price / distance 展示：新数据格式中不存在这些字段 */}

      <div className="flex gap-2 mt-3">
        <button onClick={stop} className="bg-zinc-100 text-zinc-600 px-3 py-1.5 rounded-full text-xs min-h-[32px]">
          换一�?        </button>
        <button onClick={stop} className="bg-meituan-light text-meituan-dark px-3 py-1.5 rounded-full text-xs font-medium min-h-[32px]">
          看地�?        </button>
      </div>
    </motion.div>
  );
}
