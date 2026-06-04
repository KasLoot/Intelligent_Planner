import { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface LockScreenProps {
  onEnter: () => void;
  isReplanFlow?: boolean;
}

function formatTime(date: Date): string {
  const h = date.getHours().toString().padStart(2, '0');
  const m = date.getMinutes().toString().padStart(2, '0');
  return `${h}:${m}`;
}

function formatDate(date: Date): string {
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const weekdays = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];
  return `${month}月${day}日 ${weekdays[date.getDay()]}`;
}

export default function LockScreen({ onEnter, isReplanFlow }: LockScreenProps) {
  const [now, setNow] = useState(new Date());
  const [showNotification, setShowNotification] = useState(false);

  // tick clock every 30s
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);

  // surface notification after 3s
  useEffect(() => {
    const id = setTimeout(() => {
      setShowNotification(true);
      // subtle haptic feedback if supported
      if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
        try { navigator.vibrate?.(15); } catch { /* noop */ }
      }
    }, 3000);
    return () => clearTimeout(id);
  }, []);

  const timeStr = useMemo(() => formatTime(now), [now]);
  const dateStr = useMemo(() => formatDate(now), [now]);

  return (
    <div className="w-full h-full relative overflow-hidden bg-black select-none">

      {/* status bar */}
      <div className="relative flex justify-between items-center px-6 pt-3 text-white text-[15px] font-medium">
        <span className="tracking-tight text-[13px]">中国联通</span>
        <span className="flex items-center gap-1.5 text-[13px]">
          <span>5G</span>
          <span>🔋</span>
        </span>
      </div>

      {/* main center area */}
      <div className="relative flex flex-col items-center justify-center mt-16">
        <div className="text-white text-7xl font-light tracking-tight leading-none">
          {timeStr}
        </div>
        <div className="text-white/80 text-lg font-light mt-3">
          {dateStr}
        </div>
      </div>

      {/* notification slot */}
      <div className="relative">
        <AnimatePresence>
          {showNotification && (
            <motion.button
              key="meituan-notification"
              type="button"
              onClick={onEnter}
              initial={{ y: -100, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: -100, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 280, damping: 26 }}
              className="block w-[calc(100%-2rem)] mx-4 mt-8 text-left bg-white/90 backdrop-blur-xl rounded-2xl p-4 shadow-lg active:scale-[0.99] transition-transform"
            >
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-[#FFC300] flex items-center justify-center shadow-sm">
                  <span className="font-bold text-white text-sm">团</span>
                </div>
                <span className="text-sm font-medium text-zinc-800">美团</span>
                <span className="text-xs text-zinc-400 ml-auto">现在</span>
              </div>
              <div className="text-[15px] font-semibold text-zinc-900 mt-2">
                {isReplanFlow ? '航班延误通知' : '别辜负好时光，出发去旅行吧！'}
              </div>
              <div className="text-[14px] text-zinc-600 mt-1 leading-relaxed">
                {isReplanFlow
                  ? '您预订的 MU5102 北京→上海航班延误约2小时，新起飞时间 11:30。打开小团可为您重新规划行程…'
                  : '想去哪里玩？打开小团，一键为您自动规划专属行程…'}
              </div>
            </motion.button>
          )}
        </AnimatePresence>
      </div>

      {/* bottom controls */}
      <div className="absolute inset-x-0 bottom-0 pb-8">
        <div className="flex justify-between items-center px-12 mb-6">
          <button
            type="button"
            aria-label="手电筒"
            className="w-12 h-12 rounded-full bg-white/15 backdrop-blur-xl flex items-center justify-center text-white text-xl border border-white/30 shadow-[inset_0_1px_1px_rgba(255,255,255,0.3),0_2px_8px_rgba(0,0,0,0.2)]"
          >
            🔦
          </button>
          <button
            type="button"
            aria-label="相机"
            className="w-12 h-12 rounded-full bg-white/15 backdrop-blur-xl flex items-center justify-center text-white text-xl border border-white/30 shadow-[inset_0_1px_1px_rgba(255,255,255,0.3),0_2px_8px_rgba(0,0,0,0.2)]"
          >
            📷
          </button>
        </div>

        <div className="flex flex-col items-center gap-3">
          <motion.div
            animate={{ y: [0, -4, 0] }}
            transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
            className="text-sm text-white/50"
          >
            向上滑动解锁
          </motion.div>
          <div className="w-32 h-[5px] rounded-full bg-white/90" />
        </div>
      </div>
    </div>
  );
}
