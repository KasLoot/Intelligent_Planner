import { useEffect } from 'react';
import { motion } from 'framer-motion';

interface SplashScreenProps {
  onFinish: () => void;
}

export default function SplashScreen({ onFinish }: SplashScreenProps) {
  useEffect(() => {
    const id = setTimeout(() => {
      onFinish();
    }, 2000);
    return () => clearTimeout(id);
  }, [onFinish]);

  return (
    <motion.div
      className="w-full h-full flex items-center justify-center bg-white"
      initial={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
    >
      <img
        src="/splash.jpg"
        alt="美团"
        className="w-full h-full object-cover"
      />
    </motion.div>
  );
}
