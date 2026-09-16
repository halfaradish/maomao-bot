import { useState, useCallback, useRef } from "react";

import type { ComponentProps } from "react";
import type ConfirmDialog from "@/components/ConfirmDialog";

interface ConfirmOptions {
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  color?: ComponentProps<typeof ConfirmDialog>["color"];
  onConfirm: () => void;
}

export function useConfirm() {
  const [isOpen, setIsOpen] = useState(false);
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  // 300ms 延迟清空 options, 保证 HeroUI 关闭淡出动画期间文字不闪空
  const timerRef = useRef<number | undefined>(undefined);

  const confirm = useCallback((opts: ConfirmOptions) => {
    window.clearTimeout(timerRef.current);
    setOptions(opts);
    setIsOpen(true);
  }, []);

  const handleConfirm = useCallback(() => {
    options?.onConfirm();
    setIsOpen(false);
    timerRef.current = window.setTimeout(() => setOptions(null), 300);
  }, [options]);

  const handleCancel = useCallback(() => {
    setIsOpen(false);
    timerRef.current = window.setTimeout(() => setOptions(null), 300);
  }, []);

  return {
    isOpen,
    options,
    confirm,
    handleConfirm,
    handleCancel,
  };
}
