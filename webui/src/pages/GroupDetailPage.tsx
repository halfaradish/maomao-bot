import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
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
import { Spinner } from "@heroui/spinner";
import { Chip } from "@heroui/chip";
import { MdArrowBack, MdAdd, MdDelete } from "react-icons/md";
import { motion } from "framer-motion";

import {
  useGroup,
  useGroupMembers,
  useAddGroupMembers,
  useRemoveGroupMember,
  useGroupPerms,
  useAddGroupPerms,
  useRemoveGroupPerm,
  useGroupBindings,
  useCreateBinding,
  useDeleteBinding,
} from "@/api/hooks";
import { useConfirm } from "@/hooks/useConfirm";
import ConfirmDialog from "@/components/ConfirmDialog";

export default function GroupDetailPage() {
  const { id } = useParams<{ id: string }>();
  const groupId = Number(id);
  const navigate = useNavigate();

  // Member state
  const [memberInput, setMemberInput] = useState("");
  // Perm state
  const [permInput, setPermInput] = useState("");
  // Binding state
  const [bindingQQGroup, setBindingQQGroup] = useState("");

  const { data: groupData, isLoading: groupLoading } = useGroup(groupId);
  const { data: membersData } = useGroupMembers(groupId);
  const { data: permsData } = useGroupPerms(groupId);
  const { data: bindingsData } = useGroupBindings(groupId);

  const addMembers = useAddGroupMembers(groupId);
  const removeMember = useRemoveGroupMember(groupId);
  const addPerms = useAddGroupPerms(groupId);
  const removePerm = useRemoveGroupPerm(groupId);
  const createBinding = useCreateBinding();
  const deleteBinding = useDeleteBinding();

  const { isOpen, options, confirm, handleConfirm, handleCancel } = useConfirm();

  const group = groupData?.data;
  const members = membersData?.data?.members ?? [];
  const perms = permsData?.data?.permissions ?? [];
  const bindings = bindingsData?.data?.bindings ?? [];

  const handleAddMembers = async (e: React.FormEvent) => {
    e.preventDefault();
    const ids = memberInput
      .split(/[,，\s]+/)
      .map((s) => parseInt(s.trim()))
      .filter((n) => !isNaN(n));
    if (ids.length === 0) return;
    await addMembers.mutateAsync(ids);
    setMemberInput("");
  };

  const handleRemoveMember = (userId: number) => {
    confirm({
      title: "移除成员",
      message: `确定要移除用户 ${userId} 吗？`,
      confirmText: "移除",
      onConfirm: () => removeMember.mutate(userId),
    });
  };

  const handleAddPerms = async (e: React.FormEvent) => {
    e.preventDefault();
    const keys = permInput
      .split(/[,，\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (keys.length === 0) return;
    await addPerms.mutateAsync(keys);
    setPermInput("");
  };

  const handleRemovePerm = (permKey: string) => {
    confirm({
      title: "移除权限点",
      message: `确定要移除权限点「${permKey}」吗？`,
      confirmText: "移除",
      onConfirm: () => removePerm.mutate(permKey),
    });
  };

  const handleCreateBinding = async (e: React.FormEvent) => {
    e.preventDefault();
    const qqGroupId = parseInt(bindingQQGroup);
    if (isNaN(qqGroupId)) return;
    await createBinding.mutateAsync({
      qq_group_id: qqGroupId,
      permission_group_id: groupId,
    });
    setBindingQQGroup("");
  };

  const handleDeleteBinding = (bindingId: number) => {
    confirm({
      title: "删除绑定",
      message: "确定要删除此群绑定吗？",
      confirmText: "删除",
      onConfirm: () => deleteBinding.mutate(bindingId),
    });
  };

  if (groupLoading) {
    return (
      <div className="flex justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!group) {
    return (
      <div className="text-center py-20 text-default-500">权限组不存在</div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="space-y-4"
    >
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button
          isIconOnly
          variant="light"
          onPress={() => navigate("/permissions/groups")}
        >
          <MdArrowBack size={20} />
        </Button>
        <div>
          <h1 className="text-2xl font-bold text-default-900">
            {group.display_name || group.name}
          </h1>
          <p className="text-sm text-default-500">
            {group.description || "暂无描述"}
          </p>
        </div>
      </div>

      {/* Info card */}
      <Card className="bg-white/60 dark:bg-black/40 backdrop-blur-xl border border-white/40 dark:border-white/10 shadow-sm">
        <CardBody>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <span className="text-xs text-default-500">ID</span>
              <p className="font-medium">{group.id}</p>
            </div>
            <div>
              <span className="text-xs text-default-500">标识名</span>
              <p className="font-medium">{group.name}</p>
            </div>
            <div>
              <span className="text-xs text-default-500">成员数</span>
              <p className="font-medium">{members.length}</p>
            </div>
            <div>
              <span className="text-xs text-default-500">权限点数</span>
              <p className="font-medium">{perms.length}</p>
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Tabs */}
      <Tabs aria-label="权限组详情">
        {/* QQ成员 tab */}
        <Tab key="members" title="QQ成员">
          <Card className="bg-white/60 dark:bg-black/40 backdrop-blur-xl border border-white/40 dark:border-white/10 shadow-sm">
            <CardBody className="space-y-4">
              <form onSubmit={handleAddMembers} className="flex gap-2">
                <Input
                  placeholder="输入QQ号（多个用逗号或空格分隔）"
                  value={memberInput}
                  onValueChange={setMemberInput}
                  variant="bordered"
                  radius="lg"
                  className="flex-1"
                />
                <Button
                  type="submit"
                  color="primary"
                  isLoading={addMembers.isPending}
                  startContent={<MdAdd size={18} />}
                >
                  添加
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
                  <TableColumn>添加时间</TableColumn>
                  <TableColumn>操作</TableColumn>
                </TableHeader>
                <TableBody emptyContent="暂无成员">
                  {members.map((m) => (
                    <TableRow key={m.id}>
                      <TableCell>{m.user_id}</TableCell>
                      <TableCell>
                        {m.created_at
                          ? new Date(m.created_at).toLocaleString("zh-CN")
                          : "-"}
                      </TableCell>
                      <TableCell>
                        <Button
                          isIconOnly
                          size="sm"
                          variant="light"
                          onPress={() => handleRemoveMember(m.user_id)}
                        >
                          <MdDelete size={18} className="text-danger" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardBody>
          </Card>
        </Tab>

        {/* QQ群成员 tab */}
        <Tab key="bindings" title="QQ群成员">
          <Card className="bg-white/60 dark:bg-black/40 backdrop-blur-xl border border-white/40 dark:border-white/10 shadow-sm">
            <CardBody className="space-y-4">
              <form onSubmit={handleCreateBinding} className="flex gap-2">
                <Input
                  placeholder="输入QQ群号"
                  value={bindingQQGroup}
                  onValueChange={setBindingQQGroup}
                  variant="bordered"
                  radius="lg"
                  className="flex-1"
                />
                <Button
                  type="submit"
                  color="primary"
                  isLoading={createBinding.isPending}
                  startContent={<MdAdd size={18} />}
                >
                  绑定到当前权限组
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
                  <TableColumn>绑定 ID</TableColumn>
                  <TableColumn>QQ群号</TableColumn>
                  <TableColumn>权限组 ID</TableColumn>
                  <TableColumn>操作</TableColumn>
                </TableHeader>
                <TableBody emptyContent="暂无绑定">
                  {bindings.map((b) => (
                    <TableRow key={b.id}>
                      <TableCell>{b.id}</TableCell>
                      <TableCell>{b.qq_group_id}</TableCell>
                      <TableCell>{b.permission_group_id}</TableCell>
                      <TableCell>
                        <Button
                          isIconOnly
                          size="sm"
                          variant="light"
                          onPress={() => handleDeleteBinding(b.id)}
                        >
                          <MdDelete size={18} className="text-danger" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardBody>
          </Card>
        </Tab>

        {/* 权限点 tab */}
        <Tab key="perms" title="权限点">
          <Card className="bg-white/60 dark:bg-black/40 backdrop-blur-xl border border-white/40 dark:border-white/10 shadow-sm">
            <CardBody className="space-y-4">
              <form onSubmit={handleAddPerms} className="flex gap-2">
                <Input
                  placeholder="输入权限点 key（多个用逗号或空格分隔）"
                  value={permInput}
                  onValueChange={setPermInput}
                  variant="bordered"
                  radius="lg"
                  className="flex-1"
                />
                <Button
                  type="submit"
                  color="primary"
                  isLoading={addPerms.isPending}
                  startContent={<MdAdd size={18} />}
                >
                  添加
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
                  <TableColumn>权限点 Key</TableColumn>
                  <TableColumn>添加时间</TableColumn>
                  <TableColumn>操作</TableColumn>
                </TableHeader>
                <TableBody emptyContent="暂无权限点">
                  {perms.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell>
                        <Chip size="sm" variant="flat" color="primary">
                          {p.perm_key}
                        </Chip>
                      </TableCell>
                      <TableCell>
                        {p.created_at
                          ? new Date(p.created_at).toLocaleString("zh-CN")
                          : "-"}
                      </TableCell>
                      <TableCell>
                        <Button
                          isIconOnly
                          size="sm"
                          variant="light"
                          onPress={() => handleRemovePerm(p.perm_key)}
                        >
                          <MdDelete size={18} className="text-danger" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardBody>
          </Card>
        </Tab>
      </Tabs>

      <ConfirmDialog
        isOpen={isOpen}
        title={options?.title ?? ""}
        message={options?.message ?? ""}
        confirmText={options?.confirmText}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </motion.div>
  );
}
