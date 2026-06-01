import { useEffect, useState } from 'react';
import { motion, AnimatePresence, type Variants } from 'framer-motion';

interface AgentThinkingProps {
  onComplete?: () => void;
}

const STEPS = ['分析预算', '匹配酒店', '推荐餐厅', '优化路线'] as const;

const STEP_DURATION = 800;
const COMPLETE_DELAY = 500;

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.6,
    },
  },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, x: -10 },
  visible: {
    opacity: 1,
    x: 0,
    transition: { duration: 0.3 },
  },
};

const CheckIcon = () => (
  <svg
    viewBox="0 0 16 16"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className="w-4 h-4 text-emerald-500"
  >
    <path
      d="M3.5 8.5L6.5 11.5L12.5 5"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const Spinner = () => (
  <span className="inline-block w-4 h-4 rounded-full border-2 border-zinc-300 border-t-zinc-600 animate-spin" />
);

export default function AgentThinking({ onComplete }: AgentThinkingProps) {
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    if (activeStep >= STEPS.length) {
      const timer = window.setTimeout(() => {
        onComplete?.();
      }, COMPLETE_DELAY);
      return () => window.clearTimeout(timer);
    }

    const timer = window.setTimeout(() => {
      setActiveStep((prev) => prev + 1);
    }, STEP_DURATION);

    return () => window.clearTimeout(timer);
  }, [activeStep, onComplete]);

  return (
    <div className="w-full pl-1">
      <p className="text-sm text-zinc-500 font-medium mb-2">正在规划行程...</p>

      <motion.ul
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        className="flex flex-col gap-1.5"
      >
        <AnimatePresence initial={false}>
          {STEPS.map((label, index) => {
            const isCompleted = index < activeStep;
            const isCurrent = index === activeStep;

            return (
              <motion.li
                key={label}
                variants={itemVariants}
                className="flex items-center gap-2"
              >
                <span className="w-4 h-4 flex items-center justify-center shrink-0">
                  {isCompleted ? (
                    <CheckIcon />
                  ) : isCurrent ? (
                    <Spinner />
                  ) : null}
                </span>
                <span
                  className={`text-sm ${
                    isCompleted ? 'text-zinc-800' : 'text-zinc-600'
                  }`}
                >
                  {label}
                </span>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </motion.ul>
    </div>
  );
}
