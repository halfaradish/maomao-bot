// API response types matching the backend

export interface BlacklistUser {
  id: string;
  user_id: number;
  reason: string;
  created_by: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface BlacklistGroup {
  id: string;
  group_id: number;
  reason: string;
  created_by: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface WhitelistUser {
  id: string;
  user_id: number;
  reason: string;
  created_by: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface WhitelistGroup {
  id: string;
  group_id: number;
  reason: string;
  created_by: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface PermissionGroup {
  id: number;
  name: string;
  display_name: string;
  description: string;
  created_by: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface PermissionGroupDetail extends PermissionGroup {
  members: GroupMember[];
  permissions: GroupPerm[];
}

export interface GroupMember {
  id: string;
  user_id: number;
  created_at: string | null;
}

export interface GroupPerm {
  id: string;
  perm_key: string;
  created_at: string | null;
}

export interface GroupPermBinding {
  id: number;
  qq_group_id: number;
  permission_group_id: number;
  permission_group_name?: string;
  created_at: string | null;
}

export interface PermissionPoint {
  id: string;
  plugin_name: string;
  perm_key: string;
  name: string;
  description: string;
}

export interface UserStatus {
  user_id: number;
  is_superuser: boolean;
  blacklisted: {
    reason: string;
    created_by: number;
    created_at: string | null;
  } | null;
  whitelisted: {
    reason: string;
    created_by: number;
    created_at: string | null;
  } | null;
  permission_groups: {
    id: number;
    name: string;
    display_name: string;
    description: string;
    perms: string[];
  }[];
}

// Paginated response
export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
