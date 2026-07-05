import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";

import { apiGet, apiPost, apiDelete } from "./client";
import { API } from "./endpoints";
import type {
  PermissionGroup,
  PermissionGroupDetail,
  GroupMember,
  GroupPerm,
  GroupPermBinding,
  BlacklistUser,
  BlacklistGroup,
  WhitelistUser,
  WhitelistGroup,
  PermissionPoint,
  UserStatus,
  PaginatedData,
} from "@/types/api";

// ---------------------------------------------------------------------------
// Permission Groups
// ---------------------------------------------------------------------------

export function useGroups(page = 1, size = 20) {
  return useQuery({
    queryKey: ["groups", page, size],
    queryFn: () => apiGet<PaginatedData<PermissionGroup>>(API.groups.list(page, size)),
  });
}

export function useGroup(id: number) {
  return useQuery({
    queryKey: ["group", id],
    queryFn: () => apiGet<PermissionGroupDetail>(API.groups.get(id)),
    enabled: !!id,
  });
}

export function useCreateGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string; display_name?: string; description?: string }) =>
      apiPost(API.groups.create, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["groups"] });
      toast.success("权限组创建成功");
    },
  });
}

export function useDeleteGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiDelete(API.groups.delete(id)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["groups"] });
      toast.success("权限组已删除");
    },
  });
}

// ---------------------------------------------------------------------------
// Group Members
// ---------------------------------------------------------------------------

export function useGroupMembers(groupId: number) {
  return useQuery({
    queryKey: ["group-members", groupId],
    queryFn: () =>
      apiGet<{ members: GroupMember[]; total: number }>(
        API.groups.members.list(groupId)
      ),
    enabled: !!groupId,
  });
}

export function useAddGroupMembers(groupId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userIds: number[]) =>
      apiPost(API.groups.members.add(groupId), { user_ids: userIds }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["group-members", groupId] });
      qc.invalidateQueries({ queryKey: ["group", groupId] });
      toast.success("成员添加成功");
    },
  });
}

export function useRemoveGroupMember(groupId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: number) =>
      apiDelete(API.groups.members.remove(groupId, userId)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["group-members", groupId] });
      qc.invalidateQueries({ queryKey: ["group", groupId] });
      toast.success("成员已移除");
    },
  });
}

// ---------------------------------------------------------------------------
// Group Permissions
// ---------------------------------------------------------------------------

export function useGroupPerms(groupId: number) {
  return useQuery({
    queryKey: ["group-perms", groupId],
    queryFn: () =>
      apiGet<{ permissions: GroupPerm[]; total: number }>(
        API.groups.perms.list(groupId)
      ),
    enabled: !!groupId,
  });
}

export function useAddGroupPerms(groupId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (permKeys: string[]) =>
      apiPost(API.groups.perms.add(groupId), { perm_keys: permKeys }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["group-perms", groupId] });
      qc.invalidateQueries({ queryKey: ["group", groupId] });
      toast.success("权限点添加成功");
    },
  });
}

export function useRemoveGroupPerm(groupId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (permKey: string) =>
      apiDelete(API.groups.perms.remove(groupId, permKey)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["group-perms", groupId] });
      qc.invalidateQueries({ queryKey: ["group", groupId] });
      toast.success("权限点已移除");
    },
  });
}

// ---------------------------------------------------------------------------
// Group Bindings
// ---------------------------------------------------------------------------

export function useGroupBindings(groupId: number) {
  return useQuery({
    queryKey: ["group-bindings", groupId],
    queryFn: () =>
      apiGet<{ bindings: GroupPermBinding[]; total: number }>(
        API.groups.bindings.list(groupId)
      ),
    enabled: !!groupId,
  });
}

export function useBindings(groupId?: number) {
  return useQuery({
    queryKey: ["bindings", groupId],
    queryFn: () =>
      apiGet<{ items: GroupPermBinding[]; total: number }>(
        API.bindings.list(groupId)
      ),
  });
}

export function useCreateBinding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { qq_group_id: number; permission_group_id: number }) =>
      apiPost(API.bindings.create, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bindings"] });
      qc.invalidateQueries({ queryKey: ["group-bindings"] });
      toast.success("绑定创建成功");
    },
  });
}

export function useDeleteBinding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiDelete(API.bindings.delete(id)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bindings"] });
      qc.invalidateQueries({ queryKey: ["group-bindings"] });
      toast.success("绑定已删除");
    },
  });
}

// ---------------------------------------------------------------------------
// Blacklist
// ---------------------------------------------------------------------------

export function useBlacklistUsers(page = 1, size = 20) {
  return useQuery({
    queryKey: ["blacklist-users", page, size],
    queryFn: () =>
      apiGet<PaginatedData<BlacklistUser>>(API.blacklist.users.list(page, size)),
  });
}

export function useAddBlacklistUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { user_id: number; reason?: string }) =>
      apiPost(API.blacklist.users.add, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["blacklist-users"] });
      toast.success("用户已加入黑名单");
    },
  });
}

export function useRemoveBlacklistUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: number) =>
      apiDelete(API.blacklist.users.remove(userId)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["blacklist-users"] });
      toast.success("用户已从黑名单移除");
    },
  });
}

export function useBlacklistGroups(page = 1, size = 20) {
  return useQuery({
    queryKey: ["blacklist-groups", page, size],
    queryFn: () =>
      apiGet<PaginatedData<BlacklistGroup>>(API.blacklist.groups.list(page, size)),
  });
}

export function useAddBlacklistGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { group_id: number; reason?: string }) =>
      apiPost(API.blacklist.groups.add, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["blacklist-groups"] });
      toast.success("群已加入黑名单");
    },
  });
}

export function useRemoveBlacklistGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (groupId: number) =>
      apiDelete(API.blacklist.groups.remove(groupId)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["blacklist-groups"] });
      toast.success("群已从黑名单移除");
    },
  });
}

// ---------------------------------------------------------------------------
// Whitelist
// ---------------------------------------------------------------------------

export function useWhitelistUsers(page = 1, size = 20) {
  return useQuery({
    queryKey: ["whitelist-users", page, size],
    queryFn: () =>
      apiGet<PaginatedData<WhitelistUser>>(API.whitelist.users.list(page, size)),
  });
}

export function useAddWhitelistUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { user_id: number; reason?: string }) =>
      apiPost(API.whitelist.users.add, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["whitelist-users"] });
      toast.success("用户已加入白名单");
    },
  });
}

export function useRemoveWhitelistUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: number) =>
      apiDelete(API.whitelist.users.remove(userId)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["whitelist-users"] });
      toast.success("用户已从白名单移除");
    },
  });
}

export function useWhitelistGroups(page = 1, size = 20) {
  return useQuery({
    queryKey: ["whitelist-groups", page, size],
    queryFn: () =>
      apiGet<PaginatedData<WhitelistGroup>>(API.whitelist.groups.list(page, size)),
  });
}

export function useAddWhitelistGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { group_id: number; reason?: string }) =>
      apiPost(API.whitelist.groups.add, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["whitelist-groups"] });
      toast.success("群已加入白名单");
    },
  });
}

export function useRemoveWhitelistGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (groupId: number) =>
      apiDelete(API.whitelist.groups.remove(groupId)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["whitelist-groups"] });
      toast.success("群已从白名单移除");
    },
  });
}

// ---------------------------------------------------------------------------
// Permission Points
// ---------------------------------------------------------------------------

export function usePermissionPoints(page = 1, size = 20, plugin?: string) {
  return useQuery({
    queryKey: ["permission-points", page, size, plugin],
    queryFn: () =>
      apiGet<PaginatedData<PermissionPoint>>(API.points.list(page, size, plugin)),
  });
}

export function usePermissionPlugins() {
  return useQuery({
    queryKey: ["permission-plugins"],
    queryFn: () => apiGet<{ plugins: string[] }>(API.points.plugins),
  });
}

// ---------------------------------------------------------------------------
// User Status
// ---------------------------------------------------------------------------

export function useUserStatus(userId: number) {
  return useQuery({
    queryKey: ["user-status", userId],
    queryFn: () => apiGet<UserStatus>(API.userStatus.get(userId)),
    enabled: !!userId,
  });
}
