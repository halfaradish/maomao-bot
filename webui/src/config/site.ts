export type MenuItem = {
  key: string;
  label: string;
  icon?: string;
  href?: string;
  children?: MenuItem[];
};

export const siteConfig = {
  name: "谛听 · 权限管理",
  description: "DiTing NoneBot 权限管理面板",
  navItems: [
    {
      key: "permissions",
      label: "权限管理",
      children: [
        { key: "groups", label: "权限组", href: "/permissions/groups" },
        { key: "blacklist", label: "黑名单", href: "/permissions/blacklist" },
        { key: "whitelist", label: "白名单", href: "/permissions/whitelist" },
        { key: "points", label: "权限点", href: "/permissions/points" },
        { key: "user-status", label: "用户状态", href: "/permissions/user-status" },
      ],
    },
  ] as MenuItem[],
  links: {
    github: "https://github.com/Ustinian-0328/DiTing",
  },
};
