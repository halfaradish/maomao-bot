import { useNavigate } from "react-router-dom";
import { Card, CardBody } from "@heroui/card";
import { motion } from "framer-motion";
import {
  MdGroup,
  MdBlock,
  MdCheckCircle,
  MdSecurity,
  MdPerson,
} from "react-icons/md";

const navCards = [
  {
    title: "权限组",
    description: "管理角色和权限组",
    href: "/permissions/groups",
    icon: MdGroup,
    iconBg: "bg-primary-100 dark:bg-primary-900/30",
    iconColor: "text-primary-500 dark:text-primary-400",
  },
  {
    title: "黑名单",
    description: "管理用户和群黑名单",
    href: "/permissions/blacklist",
    icon: MdBlock,
    iconBg: "bg-danger-100 dark:bg-danger-900/30",
    iconColor: "text-danger-500 dark:text-danger-400",
  },
  {
    title: "白名单",
    description: "管理用户和群白名单",
    href: "/permissions/whitelist",
    icon: MdCheckCircle,
    iconBg: "bg-success-100 dark:bg-success-900/30",
    iconColor: "text-success-500 dark:text-success-400",
  },
  {
    title: "权限点",
    description: "查看已注册的权限点",
    href: "/permissions/points",
    icon: MdSecurity,
    iconBg: "bg-secondary-100 dark:bg-secondary-900/30",
    iconColor: "text-secondary-500 dark:text-secondary-400",
  },
  {
    title: "用户状态",
    description: "查询用户权限状态",
    href: "/permissions/user-status",
    icon: MdPerson,
    iconBg: "bg-warning-100 dark:bg-warning-900/30",
    iconColor: "text-warning-500 dark:text-warning-400",
  },
];

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
    },
  },
};

const item = {
  hidden: { opacity: 0, y: 20, scale: 0.95 },
  show: { opacity: 1, y: 0, scale: 1 },
};

export default function DashboardPage() {
  const navigate = useNavigate();

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="space-y-6"
    >
      <div>
        <h1 className="text-2xl font-bold text-default-900">权限管理</h1>
        <p className="text-default-500 mt-1">选择要管理的功能模块</p>
      </div>

      <motion.div
        variants={container}
        initial="hidden"
        animate="show"
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
      >
        {navCards.map((card) => {
          const Icon = card.icon;
          return (
            <motion.div key={card.href} variants={item}>
              <Card
                isPressable
                onPress={() => navigate(card.href)}
                className="bg-white/60 dark:bg-black/40 backdrop-blur-xl border border-white/40 dark:border-white/10 shadow-sm hover:shadow-lg hover:-translate-y-1 transition-all duration-300"
              >
                <CardBody className="flex flex-row items-center gap-4 p-6">
                  <div className={`p-3 rounded-xl ${card.iconBg}`}>
                    <Icon size={28} className={card.iconColor} />
                  </div>
                  <div>
                    <h2 className="text-lg font-bold text-default-900">
                      {card.title}
                    </h2>
                    <p className="text-sm text-default-500">
                      {card.description}
                    </p>
                  </div>
                </CardBody>
              </Card>
            </motion.div>
          );
        })}
      </motion.div>
    </motion.div>
  );
}
