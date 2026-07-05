import { Button } from "@heroui/button";
import { Card, CardBody } from "@heroui/card";
import { MdError } from "react-icons/md";

interface ErrorFallbackProps {
  error: unknown;
  resetErrorBoundary: () => void;
}

export default function ErrorFallback({
  error,
  resetErrorBoundary,
}: ErrorFallbackProps) {
  const errorMessage = error instanceof Error ? error.message : String(error);
  return (
    <div className="flex items-center justify-center min-h-[400px] p-4">
      <Card className="max-w-md w-full bg-danger-50 dark:bg-danger-900/20 border border-danger-200 dark:border-danger-800">
        <CardBody className="text-center gap-4 p-8">
          <MdError className="mx-auto text-danger" size={48} />
          <h2 className="text-xl font-bold text-danger">出错了</h2>
          <p className="text-default-600">{errorMessage}</p>
          <Button
            color="danger"
            variant="flat"
            onPress={resetErrorBoundary}
          >
            重试
          </Button>
        </CardBody>
      </Card>
    </div>
  );
}
