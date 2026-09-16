import { useCallback, useEffect, useReducer, useState } from "react";

/**
 * 主题管理 — 模块级单例 store + 订阅。
 * Toaster(App.tsx) 与 DefaultLayout 需要同步 isDark,必须共用此单例。
 * 与 index.html 的内联脚本共用同一 key 与回退逻辑。
 */

const THEME_KEY = "diting_theme";
type Theme = "light" | "dark";

function readInitial(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* ignore */
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

let current: Theme = readInitial();
const listeners = new Set<() => void>();

function apply(t: Theme) {
  current = t;
  try {
    localStorage.setItem(THEME_KEY, t);
  } catch {
    /* ignore */
  }
  document.documentElement.classList.toggle("dark", t === "dark");
}

// 与 index.html 内联脚本幂等(脚本已先执行,这里再次确保一致)
apply(current);

export function useTheme() {
  const [, force] = useReducer((x) => x + 1, 0);

  useEffect(() => {
    listeners.add(force);
    return () => {
      listeners.delete(force);
    };
  }, []);

  const toggleTheme = useCallback(() => {
    apply(current === "dark" ? "light" : "dark");
    listeners.forEach((l) => l());
  }, []);

  return {
    theme: current,
    isDark: current === "dark",
    toggleTheme,
  };
}

/** 通用 localStorage 持久化状态(侧边栏展开等) */
export function useLocalStorageState<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw !== null ? (JSON.parse(raw) as T) : initial;
    } catch {
      return initial;
    }
  });

  const set = useCallback(
    (v: T | ((prev: T) => T)) => {
      setValue((prev) => {
        const next = typeof v === "function" ? (v as (p: T) => T)(prev) : v;
        try {
          localStorage.setItem(key, JSON.stringify(next));
        } catch {
          /* ignore */
        }
        return next;
      });
    },
    [key]
  );

  return [value, set] as const;
}
