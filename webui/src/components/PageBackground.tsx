import { motion } from "framer-motion";

export default function PageBackground() {
  return (
    <div className="fixed inset-0 -z-10 overflow-hidden bg-gradient-to-br from-indigo-50 via-white to-pink-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      {/* 左上 primary — 12s 呼吸 */}
      <motion.div
        className="absolute top-[-10%] left-[-10%] w-[500px] h-[500px] rounded-full bg-primary-200/40 blur-[100px]"
        animate={{ scale: [1, 1.15, 1], rotate: [0, 30, 0], opacity: [0.5, 1, 0.5] }}
        transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
      />
      {/* 中右 secondary — 15s 呼吸 */}
      <motion.div
        className="absolute top-[20%] right-[-10%] w-[400px] h-[400px] rounded-full bg-secondary-200/40 blur-[90px]"
        animate={{ scale: [1, 1.15, 1], rotate: [0, 30, 0], opacity: [0.5, 1, 0.5] }}
        transition={{ duration: 15, repeat: Infinity, ease: "easeInOut" }}
      />
      {/* 底部 pink — 18s 呼吸 */}
      <motion.div
        className="absolute bottom-[-10%] left-[20%] w-[600px] h-[600px] rounded-full bg-pink-200/30 blur-[110px]"
        animate={{ scale: [1, 1.15, 1], rotate: [0, 30, 0], opacity: [0.5, 1, 0.5] }}
        transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
      />
    </div>
  );
}
