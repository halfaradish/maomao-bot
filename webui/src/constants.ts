/**
 * 全局样式常量 — 与 NapCat nc_pink 主题对齐的统一规范
 */

/** 玻璃拟态卡片统一 className(NapCat 规范) */
export const GLASS_CARD_CLASS =
  "bg-white/60 dark:bg-black/40 backdrop-blur-xl border border-white/40 dark:border-white/10 shadow-sm rounded-2xl transition-all";

/** 表格三件套(HeroUI Table classNames),全站表格共用 */
export const TABLE_CLASS_NAMES = {
  wrapper: "bg-transparent shadow-none",
  th: "bg-white/40 dark:bg-white/5 backdrop-blur-md text-default-600",
  td: "group-data-[first=true]:first:before:rounded-none",
};

/** 列表分页大小 */
export const PAGE_SIZE = 20;
