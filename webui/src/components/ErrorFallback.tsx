import { Button } from "@heroui/button";
import { MdError } from "react-icons/md";

interface ErrorFallbackProps {
  error: unknown;
  resetErrorBoundary: () => void;
}

/** 页面级错误回退 — NapCat 同款: 中性排版 + primary 粉重试 */
export default function ErrorFallback({
  error,
  resetErrorBoundary,
}: ErrorFallbackProps) {
  const errorMessage = error instanceof Error ? error.message : String(error);
  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] p-4 gap-4">
      <MdError className="text-danger" size={48} />
      <h2 className="text-xl font-bold text-default-900 dark:text-white">
        出错了
      </h2>
      <p className="text-default-500">错误信息</p>
      <code className="rounded-md bg-default-100 dark:bg-default-50/20 px-2 py-1 text-sm font-mono text-default-600 dark:text-default-400">
        {errorMessage}
      </code>
      <Button
        color="primary"
        variant="shadow"
        radius="full"
        onPress={resetErrorBoundary}
      >
        重试
      </Button>
    </div>
  );
}
