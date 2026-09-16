import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardBody } from "@heroui/card";
import { Input } from "@heroui/input";
import { Button } from "@heroui/button";
import {
  Table,
  TableHeader,
  TableColumn,
  TableBody,
  TableRow,
  TableCell,
} from "@heroui/table";
import { Pagination } from "@heroui/pagination";
import { Spinner } from "@heroui/spinner";
import { MdAdd, MdDelete } from "react-icons/md";
import { motion } from "framer-motion";

import {
  useGroups,
  useCreateGroup,
  useDeleteGroup,
} from "@/api/hooks";
import { useConfirm } from "@/hooks/useConfirm";
import ConfirmDialog from "@/components/ConfirmDialog";
import { GLASS_CARD_CLASS, TABLE_CLASS_NAMES, PAGE_SIZE } from "@/constants";

export default function GroupsPage() {
  const [page, setPage] = useState(1);
  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [showForm, setShowForm] = useState(false);
  const navigate = useNavigate();

  const { data, isLoading } = useGroups(page);
  const createGroup = useCreateGroup();
  const deleteGroup = useDeleteGroup();
  const { isOpen, options, confirm, handleConfirm, handleCancel } = useConfirm();

  const groups = data?.data?.items ?? [];
  const total = data?.data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    await createGroup.mutateAsync({
      name: name.trim(),
      display_name: displayName.trim() || undefined,
      description: description.trim() || undefined,
    });

    setName("");
    setDisplayName("");
    setDescription("");
    setShowForm(false);
  };

  const handleDelete = (id: number, groupName: string) => {
    confirm({
      title: "删除权限组",
      message: `确定要删除权限组「${groupName}」吗？此操作不可撤销。`,
      confirmText: "删除",
      color: "danger",
      onConfirm: () => deleteGroup.mutate(id),
    });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="space-y-4"
    >
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-default-900 dark:text-white">
          权限组管理
        </h1>
        <Button
          color="primary"
          radius="full"
          variant="shadow"
          className="font-medium"
          startContent={<MdAdd size={18} />}
          onPress={() => setShowForm(!showForm)}
        >
          创建权限组
        </Button>
      </div>

      {/* Create form */}
      {showForm && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          className="overflow-hidden"
        >
          <Card className={GLASS_CARD_CLASS}>
            <CardBody>
              <form onSubmit={handleCreate} className="flex flex-col gap-3">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <Input
                    label="标识名（英文）"
                    placeholder="例如: admin"
                    value={name}
                    onValueChange={setName}
                    isRequired
                    variant="bordered"
                    radius="lg"
                  />
                  <Input
                    label="显示名称"
                    placeholder="例如: 管理员"
                    value={displayName}
                    onValueChange={setDisplayName}
                    variant="bordered"
                    radius="lg"
                  />
                  <Input
                    label="描述"
                    placeholder="可选描述"
                    value={description}
                    onValueChange={setDescription}
                    variant="bordered"
                    radius="lg"
                  />
                </div>
                <div className="flex justify-end gap-2">
                  <Button
                    variant="flat"
                    radius="full"
                    className="bg-default-100 dark:bg-default-50/50 text-default-600 font-medium"
                    onPress={() => setShowForm(false)}
                  >
                    取消
                  </Button>
                  <Button
                    type="submit"
                    color="primary"
                    radius="full"
                    variant="shadow"
                    className="font-medium"
                    isLoading={createGroup.isPending}
                  >
                    创建
                  </Button>
                </div>
              </form>
            </CardBody>
          </Card>
        </motion.div>
      )}

      {/* Table */}
      <Card className={GLASS_CARD_CLASS}>
        <CardBody className="p-0">
          <Table
            radius="sm"
            classNames={{
              ...TABLE_CLASS_NAMES,
              tr: "cursor-pointer hover:bg-default-100 transition-colors",
            }}
            onRowAction={(key) => navigate(`/permissions/groups/${key}`)}
          >
            <TableHeader>
              <TableColumn>ID</TableColumn>
              <TableColumn>标识名</TableColumn>
              <TableColumn>显示名称</TableColumn>
              <TableColumn>描述</TableColumn>
              <TableColumn>操作</TableColumn>
            </TableHeader>
            <TableBody
              isLoading={isLoading}
              loadingContent={<Spinner />}
              emptyContent="暂无权限组"
            >
              {groups.map((group) => (
                <TableRow key={group.id}>
                  <TableCell>{group.id}</TableCell>
                  <TableCell className="font-medium">{group.name}</TableCell>
                  <TableCell>{group.display_name || "-"}</TableCell>
                  <TableCell className="max-w-xs truncate">
                    {group.description || "-"}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button
                        isIconOnly
                        size="sm"
                        variant="light"
                        onPress={() => handleDelete(group.id, group.name)}
                      >
                        <MdDelete size={18} className="text-danger" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardBody>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center">
          <Pagination
            total={totalPages}
            page={page}
            onChange={setPage}
            showControls
          />
        </div>
      )}

      <ConfirmDialog
        isOpen={isOpen}
        title={options?.title ?? ""}
        message={options?.message ?? ""}
        confirmText={options?.confirmText}
        color={options?.color}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </motion.div>
  );
}
