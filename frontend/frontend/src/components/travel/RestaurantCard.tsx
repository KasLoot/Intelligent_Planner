import { motion } from 'framer-motion';
import type { MouseEvent } from 'react';
import type { RestaurantItem } from '../../types/travel';

interface RestaurantCardProps {
  item: RestaurantItem;
  onAction?: () => void;
  onTap?: () => void;
}

export default function RestaurantCard({ item, onAction, onTap }: RestaurantCardProps) {
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
        🍜 {item.name}
      </div>

      {/* 已删�?rating / price / tags 展示：新数据格式中不存在这些字段 */}
    </motion.div>
  );
}
