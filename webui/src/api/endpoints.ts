// API endpoint constants and factories

export const API = {
  // Auth
  auth: {
    login: "/auth/login",
  },

  // Permission Groups
  groups: {
    list: (page = 1, size = 20) => `/permissions/groups?page=${page}&size=${size}`,
    create: "/permissions/groups",
    get: (id: number) => `/permissions/groups/${id}`,
    delete: (id: number) => `/permissions/groups/${id}`,
    members: {
      list: (groupId: number) => `/permissions/groups/${groupId}/members`,
      add: (groupId: number) => `/permissions/groups/${groupId}/members`,
      remove: (groupId: number, userId: number) =>
        `/permissions/groups/${groupId}/members/${userId}`,
    },
    perms: {
      list: (groupId: number) => `/permissions/groups/${groupId}/perms`,
      add: (groupId: number) => `/permissions/groups/${groupId}/perms`,
      remove: (groupId: number, permKey: string) =>
        `/permissions/groups/${groupId}/perms/${permKey}`,
    },
    bindings: {
      list: (groupId: number) => `/permissions/groups/${groupId}/bindings`,
    },
  },

  // Bindings
  bindings: {
    list: (groupId?: number) =>
      groupId ? `/permissions/bindings?group_id=${groupId}` : "/permissions/bindings",
    create: "/permissions/bindings",
    delete: (id: number) => `/permissions/bindings/${id}`,
  },

  // Blacklist
  blacklist: {
    users: {
      list: (page = 1, size = 20) =>
        `/permissions/blacklist/users?page=${page}&size=${size}`,
      add: "/permissions/blacklist/users",
      remove: (userId: number) => `/permissions/blacklist/users/${userId}`,
    },
    groups: {
      list: (page = 1, size = 20) =>
        `/permissions/blacklist/groups?page=${page}&size=${size}`,
      add: "/permissions/blacklist/groups",
      remove: (groupId: number) => `/permissions/blacklist/groups/${groupId}`,
    },
  },

  // Whitelist
  whitelist: {
    users: {
      list: (page = 1, size = 20) =>
        `/permissions/whitelist/users?page=${page}&size=${size}`,
      add: "/permissions/whitelist/users",
      remove: (userId: number) => `/permissions/whitelist/users/${userId}`,
    },
    groups: {
      list: (page = 1, size = 20) =>
        `/permissions/whitelist/groups?page=${page}&size=${size}`,
      add: "/permissions/whitelist/groups",
      remove: (groupId: number) => `/permissions/whitelist/groups/${groupId}`,
    },
  },

  // Permission Points
  points: {
    list: (page = 1, size = 20, plugin?: string) => {
      let url = `/permissions/points?page=${page}&size=${size}`;
      if (plugin) url += `&plugin=${plugin}`;
      return url;
    },
    plugins: "/permissions/points/plugins",
  },

  // User Status
  userStatus: {
    get: (userId: number) => `/permissions/users/${userId}/status`,
  },

  // Cache
  cache: {
    clear: "/permissions/cache/clear",
  },
};
