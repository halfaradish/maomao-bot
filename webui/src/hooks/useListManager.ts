import { useState } from "react";
import { useConfirm } from "./useConfirm";
import type { UseMutationResult } from "@tanstack/react-query";

interface ListManagerOptions<T, TAdd = unknown, TRemove = unknown> {
  useList: (page: number, size: number) => {
    data?: { data?: { items: T[]; total: number } };
    isLoading: boolean;
  };
  useAdd: () => UseMutationResult<unknown, Error, TAdd, unknown> & {
    isPending: boolean;
  };
  useRemove: () => UseMutationResult<unknown, Error, TRemove, unknown> & {
    isPending: boolean;
  };
  getId: (item: T) => string | number;
  getLabel: (item: T) => string;
  confirmDeleteMessage: (item: T) => string;
}

export function useListManager<T, TAdd = unknown, TRemove = unknown>(
  options: ListManagerOptions<T, TAdd, TRemove>
) {
  const [page, setPage] = useState(1);
  const {
    isOpen,
    options: confirmOptions,
    confirm,
    handleConfirm,
    handleCancel,
  } = useConfirm();

  const { data, isLoading } = options.useList(page, 20);
  const addMutation = options.useAdd();
  const removeMutation = options.useRemove();

  const items = data?.data?.items ?? [];
  const total = data?.data?.total ?? 0;
  const totalPages = Math.ceil(total / 20);

  const handleDelete = (item: T) => {
    confirm({
      title: "确认删除",
      message: options.confirmDeleteMessage(item),
      confirmText: "删除",
      onConfirm: () => removeMutation.mutateAsync(options.getId(item) as TRemove),
    });
  };

  return {
    items,
    total,
    totalPages,
    page,
    setPage,
    isLoading,
    addMutation,
    removeMutation,
    handleDelete,
    confirmState: {
      isOpen,
      options: confirmOptions,
      handleConfirm,
      handleCancel,
    },
  };
}
