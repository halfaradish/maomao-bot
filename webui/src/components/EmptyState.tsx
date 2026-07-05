import { MdInbox } from "react-icons/md";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title?: string;
  description?: string;
}

export default function EmptyState({
  icon,
  title = "暂无数据",
  description,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-default-500">
      {icon || <MdInbox size={48} className="mb-3 opacity-50" />}
      <p className="text-lg font-medium">{title}</p>
      {description && <p className="text-sm mt-1">{description}</p>}
    </div>
  );
}
