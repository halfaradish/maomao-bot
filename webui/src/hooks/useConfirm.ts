import { useState, useCallback } from "react";

interface ConfirmOptions {
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  onConfirm: () => void;
}

export function useConfirm() {
  const [isOpen, setIsOpen] = useState(false);
  const [options, setOptions] = useState<ConfirmOptions | null>(null);

  const confirm = useCallback((opts: ConfirmOptions) => {
    setOptions(opts);
    setIsOpen(true);
  }, []);

  const handleConfirm = useCallback(() => {
    options?.onConfirm();
    setIsOpen(false);
    setOptions(null);
  }, [options]);

  const handleCancel = useCallback(() => {
    setIsOpen(false);
    setOptions(null);
  }, []);

  return {
    isOpen,
    options,
    confirm,
    handleConfirm,
    handleCancel,
  };
}
