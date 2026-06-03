import { motion } from 'framer-motion';
import type { MouseEvent } from 'react';
import type { HotelItem } from '../../types/travel';
import { getPlanItemLocation } from '../../types/travel';

interface HotelCardProps {
  item: HotelItem;
  onAction?: () => void;
  onTap?: () => void;
}

export default function HotelCard({ item, onAction, onTap }: HotelCardProps) {
  const stop = (event: MouseEvent) => event.stopPropagation();
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      onClick={onTap}
      className="bg-[#F8F7FB] rounded-2xl p-3 shadow-sm mb-2 relative cursor-pointer active:scale-[0.99] transition-transform"
    >
      <button
        onClick={(event) => {
          stop(event);
          onAction?.();
        }}
        aria-label="Actions"
        className="absolute top-2 right-2 w-11 h-11 flex items-center justify-center text-zinc-400 text-lg"
      >
        ...
      </button>

      <div className="font-medium text-zinc-800 pr-8">Hotel {item.name}</div>
      {getPlanItemLocation(item) && (
        <div className="text-zinc-500 text-sm truncate mt-1">{getPlanItemLocation(item)}</div>
      )}
    </motion.div>
  );
}
