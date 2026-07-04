import { useState } from "react";
import { Card, CardBody } from "@heroui/card";
import { Input } from "@heroui/input";
import { Button } from "@heroui/button";
import { Tabs, Tab } from "@heroui/tabs";
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
  useWhitelistUsers,
  useAddWhitelistUser,
  useRemoveWhitelistUser,
  useWhitelistGroups,
  useAddWhitelistGroup,
  useRemoveWhitelistGroup,
} from "@/api/hooks";
import { useListManager } from "@/hooks/useListManager";
import ConfirmDialog from "@/components/ConfirmDialog";
import type { WhitelistUser, WhitelistGroup } from "@/types/api";

export default function WhitelistPage() {
  // User whitelist
  const [userId, setUserId] = useState("");
  const [userReason, setUserReason] = useState("");

  const userList = useListManager<WhitelistUser, { user_id: number; reason?: string }, number>({
    useList: useWhitelistUsers,
    useAdd: useAddWhitelistUser,
    useRemove: useRemoveWhitelistUser,
    getId: (item) => item.user_id,
    getLabel: (item) => String(item.user_id),
    confirmDeleteMessage: (item) => `确定要将用户 ${item.user_id} 从白名单移除吗？`,
  });

  // Group whitelist
  const [groupId, setGroupId] = useState("");
  const [groupReason, setGroupReason] = useState("");

  const groupList = useListManager<WhitelistGroup, { group_id: number; reason?: string }, number>({
    useList: useWhitelistGroups,
    useAdd: useAddWhitelistGroup,
    useRemove: useRemoveWhitelistGroup,
    getId: (item) => item.group_id,
    getLabel: (item) => String(item.group_id),
    confirmDeleteMessage: (item) => `确定要将群 ${item.group_id} 从白名单移除吗？`,
  });

  const handleAddUser = async (e: React.FormEvent) => {
    e.preventDefault();
    const id = parseInt(userId);
    if (isNaN(id)) return;
    await userList.addMutation.mutateAsync({
      user_id: id,
      reason: userReason.trim() || undefined,
    });
    setUserId("");
    setUserReason("");
  };

  const handleAddGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    const id = parseInt(groupId);
    if (isNaN(id)) return;
    await groupList.addMutation.mutateAsync({
      group_id: id,
      reason: groupReason.trim() || undefined,
    });
    setGroupId("");
    setGroupReason("");
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="space-y-4"
    >
      <h1 className="text-2xl font-bold text-default-900">白名单管理</h1>

      <Tabs aria-label="白名单">
        {/* User whitelist */}
        <Tab key="users" title="用户白名单">
          <Card className="bg-white/60 dark:bg-black/40 backdrop-blur-xl border border-white/40 dark:border-white/10 shadow-sm">
            <CardBody className="space-y-4">
              <form onSubmit={handleAddUser} className="flex gap-2">
                <Input
                  placeholder="QQ号"
                  value={userId}
                  onValueChange={setUserId}
                  variant="bordered"
                  radius="lg"
                  isRequired
                />
                <Input
                  placeholder="原因（可选）"
                  value={userReason}
                  onValueChange={setUserReason}
                  variant="bordered"
                  radius="lg"
                  className="flex-1"
                />
                <Button
                  type="submit"
                  color="success"
                  isLoading={userList.addMutation.isPending}
                  startContent={<MdAdd size={18} />}
                >
                  加白
                </Button>
              </form>

              <Table
                radius="sm"
                classNames={{
                  wrapper: "bg-transparent shadow-none",
                  th: "bg-white/40 dark:bg-white/5 backdrop-blur-md text-default-600",
                }}
              >
                <TableHeader>
                  <TableColumn>QQ号</TableColumn>
                  <TableColumn>原因</TableColumn>
                  <TableColumn>操作人</TableColumn>
                  <TableColumn>时间</TableColumn>
                  <TableColumn>操作</TableColumn>
                </TableHeader>
                <TableBody
                  isLoading={userList.isLoading}
                  loadingContent={<Spinner />}
                  emptyContent="暂无白名单用户"
                >
                  {userList.items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>{item.user_id}</TableCell>
                      <TableCell>{item.reason || "-"}</TableCell>
                      <TableCell>{item.created_by}</TableCell>
                      <TableCell>
                        {item.created_at
                          ? new Date(item.created_at).toLocaleString("zh-CN")
                          : "-"}
                      </TableCell>
                      <TableCell>
                        <Button
                          isIconOnly
                          size="sm"
                          variant="light"
                          onPress={() => userList.handleDelete(item)}
                        >
                          <MdDelete size={18} className="text-danger" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {userList.totalPages > 1 && (
                <div className="flex justify-center">
                  <Pagination
                    total={userList.totalPages}
                    page={userList.page}
                    onChange={userList.setPage}
                    showControls
                  />
                </div>
              )}
            </CardBody>
          </Card>
        </Tab>

        {/* Group whitelist */}
        <Tab key="groups" title="群白名单">
          <Card className="bg-white/60 dark:bg-black/40 backdrop-blur-xl border border-white/40 dark:border-white/10 shadow-sm">
            <CardBody className="space-y-4">
              <form onSubmit={handleAddGroup} className="flex gap-2">
                <Input
                  placeholder="群号"
                  value={groupId}
                  onValueChange={setGroupId}
                  variant="bordered"
                  radius="lg"
                  isRequired
                />
                <Input
                  placeholder="原因（可选）"
                  value={groupReason}
                  onValueChange={setGroupReason}
                  variant="bordered"
                  radius="lg"
                  className="flex-1"
                />
                <Button
                  type="submit"
                  color="success"
                  isLoading={groupList.addMutation.isPending}
                  startContent={<MdAdd size={18} />}
                >
                  加白
                </Button>
              </form>

              <Table
                radius="sm"
                classNames={{
                  wrapper: "bg-transparent shadow-none",
                  th: "bg-white/40 dark:bg-white/5 backdrop-blur-md text-default-600",
                }}
              >
                <TableHeader>
                  <TableColumn>群号</TableColumn>
                  <TableColumn>原因</TableColumn>
                  <TableColumn>操作人</TableColumn>
                  <TableColumn>时间</TableColumn>
                  <TableColumn>操作</TableColumn>
                </TableHeader>
                <TableBody
                  isLoading={groupList.isLoading}
                  loadingContent={<Spinner />}
                  emptyContent="暂无白名单群"
                >
                  {groupList.items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>{item.group_id}</TableCell>
                      <TableCell>{item.reason || "-"}</TableCell>
                      <TableCell>{item.created_by}</TableCell>
                      <TableCell>
                        {item.created_at
                          ? new Date(item.created_at).toLocaleString("zh-CN")
                          : "-"}
                      </TableCell>
                      <TableCell>
                        <Button
                          isIconOnly
                          size="sm"
                          variant="light"
                          onPress={() => groupList.handleDelete(item)}
                        >
                          <MdDelete size={18} className="text-danger" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {groupList.totalPages > 1 && (
                <div className="flex justify-center">
                  <Pagination
                    total={groupList.totalPages}
                    page={groupList.page}
                    onChange={groupList.setPage}
                    showControls
                  />
                </div>
              )}
            </CardBody>
          </Card>
        </Tab>
      </Tabs>

      <ConfirmDialog
        isOpen={userList.confirmState.isOpen}
        title={userList.confirmState.options?.title ?? ""}
        message={userList.confirmState.options?.message ?? ""}
        confirmText={userList.confirmState.options?.confirmText}
        onConfirm={userList.confirmState.handleConfirm}
        onCancel={userList.confirmState.handleCancel}
      />
      <ConfirmDialog
        isOpen={groupList.confirmState.isOpen}
        title={groupList.confirmState.options?.title ?? ""}
        message={groupList.confirmState.options?.message ?? ""}
        confirmText={groupList.confirmState.options?.confirmText}
        onConfirm={groupList.confirmState.handleConfirm}
        onCancel={groupList.confirmState.handleCancel}
      />
    </motion.div>
  );
}
