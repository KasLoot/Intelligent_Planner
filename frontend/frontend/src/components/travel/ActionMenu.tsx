import { AnimatePresence, motion } from 'framer-motion';

interface ActionMenuProps {
  visible: boolean;
  onClose: () => void;
  onQuote?: () => void;
  onDelete?: () => void;
}

export default function ActionMenu({
  visible,
  onClose,
  onQuote,
  onDelete,
}: ActionMenuProps) {
  const handle = (fn?: () => void) => () => {
    fn?.();
    onClose();
  };

  return (
    <AnimatePresence>
      {visible && (
        <div className="fixed inset-0 z-50 max-w-[430px] mx-auto">
          <motion.div
            key="mask"
            className="absolute inset-0 bg-black/30"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
          />

          <motion.div
            key="sheet"
            className="absolute bottom-0 left-0 right-0 bg-white rounded-t-2xl pb-8"
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
          >
            {/* 拖拽指示条 */}
            <div className="mx-auto w-10 h-1 bg-zinc-300 rounded-full mt-3 mb-2" />

            <button
              onClick={handle(onQuote)}
              className="w-full flex items-center gap-3 px-6 py-3 text-zinc-800 border-b border-zinc-100 text-[15px]"
            >
              引用
            </button>

            <button
              onClick={handle(onDelete)}
              className="w-full flex items-center gap-3 px-6 py-3 text-red-500 border-b border-zinc-100 text-[15px]"
            >
              删除
            </button>

            <button
              onClick={onClose}
              className="w-full text-center py-3 text-zinc-400 text-[15px]"
            >
              取消
            </button>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
