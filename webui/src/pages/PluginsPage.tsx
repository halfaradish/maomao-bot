import { useMemo, useState } from "react";
import { Card, CardBody } from "@heroui/card";
import { Chip } from "@heroui/chip";
import { Divider } from "@heroui/divider";
import {
  Modal,
  ModalContent,
  ModalHeader,
  ModalBody,
} from "@heroui/modal";
import { motion } from "framer-motion";
import { MdExtension, MdSecurity } from "react-icons/md";

import { usePlugins } from "@/api/hooks";
import { GLASS_CARD_CLASS } from "@/constants";
import type { PluginInfo } from "@/types/api";

/** 分组顺序 — 对齐 PluginGroupEnum 的展示习惯，未知分组排最后 */
const GROUP_ORDER = ["基础命令", "群管理", "竞赛相关", "实用工具", "监控提醒"];

/** badge_color → HeroUI Chip 颜色（对齐 /help 菜单 green/blue/yellow） */
const BADGE_CHIP_COLOR: Record<string, "success" | "primary" | "warning" | "default"> = {
  green: "success",
  blue: "primary",
  yellow: "warning",
};

export default function PluginsPage() {
  const { data, isLoading } = usePlugins();
  const [selected, setSelected] = useState<PluginInfo | null>(null);

  const grouped = useMemo(() => {
    const items = data?.data?.items ?? [];
    const map = new Map<string, PluginInfo[]>();
    for (const plugin of items) {
      const group = plugin.group || "其他";
      if (!map.has(group)) map.set(group, []);
      map.get(group)!.push(plugin);
    }
    return Array.from(map.entries()).sort(([a], [b]) => {
      const ia = GROUP_ORDER.indexOf(a);
      const ib = GROUP_ORDER.indexOf(b);
      if (ia === -1 && ib === -1) return a.localeCompare(b);
      if (ia === -1) return 1;
      if (ib === -1) return -1;
      return ia - ib;
    });
  }, [data]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="space-y-6"
    >
      <div>
        <h1 className="text-2xl font-bold text-default-900 dark:text-white">
          插件管理
        </h1>
        <p className="text-default-500 mt-1">
          共 {data?.data?.total ?? 0} 个插件（功能展示，与 QQ 群内 /help 同源）
        </p>
      </div>

      {isLoading ? (
        <Card className={GLASS_CARD_CLASS}>
          <CardBody className="flex items-center justify-center py-12 text-default-400">
            加载中…
          </CardBody>
        </Card>
      ) : (
        grouped.map(([group, plugins], gi) => (
          <div key={group} className="space-y-3">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-default-900 dark:text-white">
                {group}
              </h2>
              <Chip size="sm" variant="flat" color="secondary">
                {plugins.length}
              </Chip>
            </div>
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, delay: gi * 0.05 }}
              className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
            >
              {plugins.map((plugin) => (
                <Card
                  key={plugin.module_name}
                  isPressable
                  onPress={() => setSelected(plugin)}
                  className={`${GLASS_CARD_CLASS} hover:shadow-lg hover:-translate-y-1 duration-300`}
                >
                  <CardBody className="space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="font-semibold text-default-900 dark:text-white">
                        {plugin.name}
                      </h3>
                      {plugin.badge_color && (
                        <Chip
                          size="sm"
                          variant="flat"
                          color={BADGE_CHIP_COLOR[plugin.badge_color] || "default"}
                        >
                          {plugin.group || "未分组"}
                        </Chip>
                      )}
                    </div>
                    <p className="text-sm text-default-500 line-clamp-2 min-h-[2.5rem]">
                      {plugin.description || "暂无描述"}
                    </p>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1 text-xs text-default-400">
                        <MdSecurity size={14} />
                        权限点 {plugin.perm_point_count}
                      </div>
                      <span className="text-xs text-primary-500">查看用法 →</span>
                    </div>
                  </CardBody>
                </Card>
              ))}
            </motion.div>
          </div>
        ))
      )}

      {!isLoading && grouped.length === 0 && (
        <Card className={GLASS_CARD_CLASS}>
          <CardBody className="flex flex-col items-center justify-center py-12 text-default-400 gap-2">
            <MdExtension size={48} />
            <p>暂无插件数据</p>
          </CardBody>
        </Card>
      )}

      {/* 用法弹窗 */}
      <Modal
        isOpen={!!selected}
        onClose={() => setSelected(null)}
        size="2xl"
        backdrop="blur"
        scrollBehavior="inside"
      >
        <ModalContent>
          <ModalHeader className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              {selected?.name}
              {selected?.badge_color && (
                <Chip
                  size="sm"
                  variant="flat"
                  color={BADGE_CHIP_COLOR[selected.badge_color] || "default"}
                >
                  {selected.group || "未分组"}
                </Chip>
              )}
            </div>
            <p className="text-sm font-normal text-default-500">
              {selected?.module_name} · 权限点 {selected?.perm_point_count} 个
            </p>
          </ModalHeader>
          <ModalBody className="pb-6">
            <p className="text-default-600 dark:text-default-300">
              {selected?.description || "暂无描述"}
            </p>
            <Divider />
            <p className="text-sm text-default-500">用法说明</p>
            <div className="whitespace-pre-wrap text-default-700 dark:text-default-200 rounded-xl bg-default-100/50 dark:bg-white/5 p-4">
              {selected?.usage || "无用法说明"}
            </div>
          </ModalBody>
        </ModalContent>
      </Modal>
    </motion.div>
  );
}
