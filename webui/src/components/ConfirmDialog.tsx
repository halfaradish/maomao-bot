import {
  Modal,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
} from "@heroui/modal";
import { Button } from "@heroui/button";

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  /** 确认按钮颜色: 通用确认默认 primary 樱花粉, 删除类操作显式传 danger */
  color?: "primary" | "secondary" | "success" | "warning" | "danger" | "default";
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmText = "确认",
  cancelText = "取消",
  color = "primary",
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onCancel}
      size="sm"
      backdrop="blur"
      classNames={{
        backdrop: "z-[99] backdrop-blur-sm",
        wrapper: "z-[99]",
      }}
    >
      <ModalContent>
        <ModalHeader className="text-default-900 dark:text-white">
          {title}
        </ModalHeader>
        <ModalBody className="break-all">
          <p className="text-default-600">{message}</p>
        </ModalBody>
        <ModalFooter>
          <Button variant="light" onPress={onCancel}>
            {cancelText}
          </Button>
          <Button color={color} onPress={onConfirm}>
            {confirmText}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
