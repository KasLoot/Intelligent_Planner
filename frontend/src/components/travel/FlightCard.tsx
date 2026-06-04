import { motion } from 'framer-motion';
import type { MouseEvent } from 'react';
import type { FlightItem } from '../../types/travel';
import { getPlanItemTime } from '../../types/travel';

interface FlightCardProps {
  item: FlightItem;
  onAction?: () => void;
  onTap?: () => void;
}

export default function FlightCard({ item, onAction, onTap }: FlightCardProps) {
  const stop = (event: MouseEvent) => event.stopPropagation();
  const price = `${item.currency ? `${item.currency} ` : ''}${item.price}`;

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

      <div className="font-medium text-zinc-800 pr-8">Flight {item.name}</div>

      <div className="flex justify-between mt-1">
        <span className="text-sm text-zinc-500">{getPlanItemTime(item)}</span>
        <span className="text-sm font-medium text-zinc-700">{price}</span>
      </div>
    </motion.div>
  );
}
