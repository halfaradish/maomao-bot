import { useState } from "react";
import { Card, CardBody } from "@heroui/card";
import { Chip } from "@heroui/chip";
import { Select, SelectItem } from "@heroui/select";
import { Spinner } from "@heroui/spinner";
import { Switch } from "@heroui/switch";
import { motion } from "framer-motion";
import { MdToggleOn } from "react-icons/md";

import { useGroupFeatures, useQQGroups, useToggleGroupFeature } from "@/api/hooks";
import { GLASS_CARD_CLASS } from "@/constants";
import EmptyState from "@/components/EmptyState";

export default function GroupFeaturesPage() {
  // 群选择器数据源：前 100 个群
  const { data: groupsData, isLoading: groupsLoading } = useQQGroups(1, 100);
  const [groupId, setGroupId] = useState<number | null>(null);

  const { data, isLoading } = useGroupFeatures(groupId);
  const toggleMutation = useToggleGroupFeature(groupId);

  const groups = groupsData?.data?.items ?? [];
  const features = data?.data?.features ?? [];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="space-y-4"
    >
      <div>
        <h1 className="text-2xl font-bold text-default-900 dark:text-white">
          群功能
        </h1>
        <p className="text-default-500 mt-1">
          按群开关功能，与 QQ 命令「群管理 监控/取消监控」效果一致
        </p>
      </div>

      {/* 群选择器 */}
      <Card className={GLASS_CARD_CLASS}>
        <CardBody>
          <Select
            label="选择群"
            placeholder={groupsLoading ? "加载群列表中…" : "选择一个群"}
            items={groups}
            selectionMode="single"
            selectedKeys={groupId ? [String(groupId)] : []}
            onSelectionChange={(keys) => {
              const key = Array.from(keys as Set<string>)[0];
              setGroupId(key ? Number(key) : null);
            }}
            isLoading={groupsLoading}
            className="max-w-md"
            variant="bordered"
          >
            {(g) => (
              <SelectItem key={g.group_id} textValue={g.group_name}>
                {g.group_name || "未命名群"}（{g.group_id}）
              </SelectItem>
            )}
          </Select>
        </CardBody>
      </Card>

      {/* 功能开关列表 */}
      {!groupId ? (
        <Card className={GLASS_CARD_CLASS}>
          <CardBody className="py-10">
            <EmptyState
              icon={<MdToggleOn size={48} />}
              title="请先选择一个群"
              description="选择群后展示该群的功能开关状态"
            />
          </CardBody>
        </Card>
      ) : isLoading ? (
        <Card className={GLASS_CARD_CLASS}>
          <CardBody className="flex items-center justify-center py-12">
            <Spinner />
          </CardBody>
        </Card>
      ) : (
        <div className="space-y-3">
          {features.map((feature, i) => (
            <motion.div
              key={feature.perm_key}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, delay: i * 0.05 }}
            >
              <Card className={GLASS_CARD_CLASS}>
                <CardBody className="flex flex-row items-center justify-between gap-3 py-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-default-900 dark:text-white">
                        {feature.name}
                      </span>
                      <Chip size="sm" variant="flat" color="secondary">
                        {feature.perm_key}
                      </Chip>
                    </div>
                    {feature.perm_key === "auto_manage_group:ban_word_log_target" && (
                      <p className="text-xs text-default-400">
                        该群接收违禁词检测告警日志
                      </p>
                    )}
                  </div>
                  <Switch
                    isSelected={feature.enabled}
                    isDisabled={toggleMutation.isPending}
                    onValueChange={(enabled) =>
                      toggleMutation.mutate({
                        perm_key: feature.perm_key,
                        enabled,
                      })
                    }
                  />
                </CardBody>
              </Card>
            </motion.div>
          ))}
        </div>
      )}
    </motion.div>
  );
}
