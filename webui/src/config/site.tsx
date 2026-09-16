import type { ReactNode } from "react";
import {
  MdAdminPanelSettings,
  MdGroup,
  MdBlock,
  MdCheckCircle,
  MdSecurity,
  MdPersonSearch,
  MdInfo,
  MdExtension,
  MdGroups,
  MdList,
  MdToggleOn,
  MdArticle,
} from "react-icons/md";

export type MenuItem = {
  key: string;
  label: string;
  icon?: ReactNode;
  href?: string;
  children?: MenuItem[];
};

export const siteConfig = {
  name: "谛听 · 权限管理",
  description: "DiTing NoneBot 权限管理面板",
  navItems: [
    {
      key: "bot-info",
      label: "基础信息",
      href: "/info",
      icon: <MdInfo className="w-5 h-5" />,
    },
    {
      key: "permissions",
      label: "权限管理",
      icon: <MdAdminPanelSettings className="w-5 h-5" />,
      children: [
        {
          key: "groups",
          label: "权限组",
          href: "/permissions/groups",
          icon: <MdGroup className="w-5 h-5" />,
        },
        {
          key: "blacklist",
          label: "黑名单",
          href: "/permissions/blacklist",
          icon: <MdBlock className="w-5 h-5" />,
        },
        {
          key: "whitelist",
          label: "白名单",
          href: "/permissions/whitelist",
          icon: <MdCheckCircle className="w-5 h-5" />,
        },
        {
          key: "points",
          label: "权限点",
          href: "/permissions/points",
          icon: <MdSecurity className="w-5 h-5" />,
        },
        {
          key: "user-status",
          label: "用户状态",
          href: "/permissions/user-status",
          icon: <MdPersonSearch className="w-5 h-5" />,
        },
      ],
    },
    {
      key: "plugins",
      label: "插件管理",
      href: "/plugins",
      icon: <MdExtension className="w-5 h-5" />,
    },
    {
      key: "qq-groups",
      label: "群管理",
      icon: <MdGroups className="w-5 h-5" />,
      children: [
        {
          key: "qq-group-list",
          label: "群列表",
          href: "/groups/list",
          icon: <MdList className="w-5 h-5" />,
        },
        {
          key: "qq-group-features",
          label: "群功能",
          href: "/groups/features",
          icon: <MdToggleOn className="w-5 h-5" />,
        },
      ],
    },
    {
      key: "logs",
      label: "消息日志",
      href: "/logs",
      icon: <MdArticle className="w-5 h-5" />,
    },
  ] as MenuItem[],
  links: {
    github: "https://github.com/Ustinian-0328/DiTing",
  },
};
