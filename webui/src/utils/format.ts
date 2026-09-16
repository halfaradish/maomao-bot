/**
 * 展示层格式化工具
 */

/** 秒数 → 人性化运行时长（如「3 天 5 小时」「2 小时 15 分」） */
export function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d} 天 ${h} 小时`;
  if (h > 0) return `${h} 小时 ${m} 分`;
  return `${m} 分`;
}

/** Unix 秒时间戳 → 本地时间字符串 */
export function formatTimestamp(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  return new Date(seconds * 1000).toLocaleString("zh-CN", { hour12: false });
}
