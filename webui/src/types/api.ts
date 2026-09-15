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

// ---------------------------------------------------------------------------
// Bot 基础信息
// ---------------------------------------------------------------------------

export interface BotConnections {
  bot_db: boolean;
  icpc_db: boolean;
  redis: boolean;
}

export interface BotInfo {
  status: "online" | "offline";
  bot_count: number;
  bot_id: string | null;
  nickname: string | null;
  adapter: string | null;
  group_count: number | null;
  uptime_seconds: number;
  connections: BotConnections;
}

// ---------------------------------------------------------------------------
// 插件管理
// ---------------------------------------------------------------------------

export interface PluginInfo {
  name: string;
  module_name: string;
  description: string;
  usage: string;
  group: string | null;
  badge_color: string | null;
  perm_point_count: number;
}

// ---------------------------------------------------------------------------
// 群管理
// ---------------------------------------------------------------------------

export interface QQGroupInfo {
  group_id: number;
  group_name: string;
  member_count: number | null;
  max_member_count: number | null;
  group_function: string;
  monitored: boolean | null;
  last_crawled_at: string | null;
  message_count: number;
  active_member_count: number;
  last7d_message_count: number;
  last_message_time: number | null;
}

export interface QQGroupStats {
  group_id: number;
  group_name: string;
  member_count: number | null;
  max_member_count: number | null;
  group_function: string;
  monitored: boolean | null;
  last_crawled_at: string | null;
  message_count: number;
  active_member_count: number;
  last7d_message_count: number;
  last_message_time: number | null;
}

export interface GroupFeature {
  name: string;
  perm_key: string;
  enabled: boolean;
}

export interface GroupFeatures {
  group_id: number;
  features: GroupFeature[];
}

// ---------------------------------------------------------------------------
// 消息日志
// ---------------------------------------------------------------------------

export interface MessageLog {
  id: number;
  message_id: number;
  time: number;
  group_id: number | null;
  user_id: number;
  sender_nickname: string;
  sender_card: string | null;
  sender_role: string;
  message_type: string;
  sub_type: string;
  to_me: boolean;
  raw_message: string;
}

export interface MessageLogFilters {
  group_id?: number | null;
  user_id?: number | null;
  keyword?: string;
  message_type?: string | null;
  start_time?: number | null;
  end_time?: number | null;
}
