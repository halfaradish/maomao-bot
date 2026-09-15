import { Spinner } from "@heroui/spinner";

interface PageLoadingProps {
  loading?: boolean;
}

/** 全局加载遮罩(NapCat PageLoading 同款) */
export default function PageLoading({ loading = true }: PageLoadingProps) {
  if (!loading) return null;
  return (
    <div className="fixed inset-0 z-[60] bg-zinc-500/10 backdrop-blur flex items-center justify-center">
      <Spinner size="lg" />
    </div>
  );
}
