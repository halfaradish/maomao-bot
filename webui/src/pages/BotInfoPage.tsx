import { useState } from "react";
import { Card, CardBody } from "@heroui/card";
import { Avatar } from "@heroui/avatar";
import { Chip } from "@heroui/chip";
import { Divider } from "@heroui/divider";
import { Skeleton } from "@heroui/skeleton";
import { motion } from "framer-motion";
import {
  MdCircle,
  MdGroups,
  MdLink,
  MdTag,
  MdTimer,
  MdSmartToy,
} from "react-icons/md";

import { useBotInfo } from "@/api/hooks";
import { siteConfig } from "@/config/site";
import { GLASS_CARD_CLASS } from "@/constants";
import { formatUptime } from "@/utils/format";

function ConnectionDot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <MdCircle
        size={14}
        className={ok ? "text-success-500" : "text-danger-500"}
      />
      <span className="text-default-600 dark:text-default-400">{label}</span>
      <Chip
        size="sm"
        variant="flat"
        color={ok ? "success" : "danger"}
        className="ml-auto"
      >
        {ok ? "正常" : "异常"}
      </Chip>
    </div>
  );
}

export default function BotInfoPage() {
  const { data, isLoading } = useBotInfo();
  const info = data?.data;
  const [avatarError, setAvatarError] = useState(false);

  const online = info?.status === "online";

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="space-y-4"
    >
      <h1 className="text-2xl font-bold text-default-900 dark:text-white">
        基础信息
      </h1>

      {/* 头像 + 名称 + 状态 */}
      <Card className={GLASS_CARD_CLASS}>
        <CardBody className="flex flex-row items-center gap-5 p-6">
          <Avatar
            src={avatarError ? undefined : "/logo.jpg"}
            fallback={
              <MdSmartToy size={48} className="text-primary-400 dark:text-primary-300" />
            }
            showFallback
            onError={() => setAvatarError(true)}
            className="w-24 h-24"
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3">
              <h2 className="text-2xl font-bold text-default-900 dark:text-white">
                谛听
              </h2>
              {isLoading ? (
                <Skeleton className="h-6 w-14 rounded-full" />
              ) : (
                <Chip
                  variant="flat"
                  color={online ? "success" : "default"}
                  size="sm"
                >
                  {online ? "在线" : "离线"}
                </Chip>
              )}
            </div>
            <p className="text-default-500 mt-1 break-words">
              {siteConfig.description}
            </p>
          </div>
        </CardBody>
      </Card>

      {/* 关键信息格子 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Bot 账号 */}
        <Card className={GLASS_CARD_CLASS}>
          <CardBody className="space-y-2">
            <div className="flex items-center gap-2 text-default-500">
              <MdTag size={18} className="text-primary-500" />
              <span className="text-sm font-medium">Bot 账号</span>
            </div>
            {isLoading ? (
              <Skeleton className="h-5 w-40" />
            ) : (
              <p className="text-lg font-semibold text-default-900 dark:text-white">
                {info?.bot_id || "—"}
              </p>
            )}
            {isLoading ? (
              <Skeleton className="h-4 w-32" />
            ) : (
              <p className="text-sm text-default-500">
                适配器：{info?.adapter || "—"}
              </p>
            )}
          </CardBody>
        </Card>

        {/* 所在群数量 */}
        <Card className={GLASS_CARD_CLASS}>
          <CardBody className="space-y-2">
            <div className="flex items-center gap-2 text-default-500">
              <MdGroups size={18} className="text-secondary-500" />
              <span className="text-sm font-medium">所在群数量</span>
            </div>
            {isLoading ? (
              <Skeleton className="h-5 w-16" />
            ) : (
              <p className="text-lg font-semibold text-default-900 dark:text-white">
                {info?.group_count !== null && info?.group_count !== undefined
                  ? `${info.group_count} 个群`
                  : "网关离线"}
              </p>
            )}
            {isLoading ? (
              <Skeleton className="h-4 w-40" />
            ) : (
              <p className="text-sm text-default-500">
                数据来自 QQ 网关实时查询
              </p>
            )}
          </CardBody>
        </Card>

        {/* 运行时长 */}
        <Card className={GLASS_CARD_CLASS}>
          <CardBody className="space-y-2">
            <div className="flex items-center gap-2 text-default-500">
              <MdTimer size={18} className="text-warning-500" />
              <span className="text-sm font-medium">运行时长</span>
            </div>
            {isLoading ? (
              <Skeleton className="h-5 w-32" />
            ) : (
              <p className="text-lg font-semibold text-default-900 dark:text-white">
                {info ? formatUptime(info.uptime_seconds) : "—"}
              </p>
            )}
            {isLoading ? (
              <Skeleton className="h-4 w-32" />
            ) : (
              <p className="text-sm text-default-500">后端进程启动至今</p>
            )}
          </CardBody>
        </Card>

        {/* 连接状态 */}
        <Card className={GLASS_CARD_CLASS}>
          <CardBody className="space-y-2">
            <div className="flex items-center gap-2 text-default-500">
              <MdLink size={18} className="text-danger-500" />
              <span className="text-sm font-medium">连接状态</span>
            </div>
            {isLoading || !info ? (
              <>
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-full" />
              </>
            ) : (
              <div className="space-y-1.5">
                <ConnectionDot ok={info.connections.bot_db} label="Bot DB" />
                <ConnectionDot ok={info.connections.icpc_db} label="ICPC DB" />
                <ConnectionDot ok={info.connections.redis} label="Redis" />
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      <Divider className="mt-2" />
    </motion.div>
  );
}
