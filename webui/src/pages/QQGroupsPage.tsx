import { useState } from "react";
import { Card, CardBody } from "@heroui/card";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";
import { Divider } from "@heroui/divider";
import {
  Modal,
  ModalContent,
  ModalHeader,
  ModalBody,
} from "@heroui/modal";
import { Pagination } from "@heroui/pagination";
import { Spinner } from "@heroui/spinner";
import {
  Table,
  TableHeader,
  TableColumn,
  TableBody,
  TableRow,
  TableCell,
} from "@heroui/table";
import { motion } from "framer-motion";
import { MdGroups, MdInsertChart } from "react-icons/md";

import { useQQGroups, useQQGroupStats } from "@/api/hooks";
import { GLASS_CARD_CLASS, TABLE_CLASS_NAMES, PAGE_SIZE } from "@/constants";
import { formatTimestamp } from "@/utils/format";
import type { QQGroupInfo } from "@/types/api";

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-default-100/50 dark:bg-white/5 p-3">
      <p className="text-xs text-default-500">{label}</p>
      <p className="text-base font-semibold text-default-900 dark:text-white mt-0.5">
        {value}
      </p>
    </div>
  );
}

export default function QQGroupsPage() {
  const [page, setPage] = useState(1);
  const [statsGroup, setStatsGroup] = useState<QQGroupInfo | null>(null);

  const { data, isLoading } = useQQGroups(page, PAGE_SIZE);
  const { data: statsData, isLoading: statsLoading } = useQQGroupStats(
    statsGroup?.group_id ?? null
  );

  const groups = data?.data?.items ?? [];
  const total = data?.data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const stats = statsData?.data;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="space-y-4"
    >
      <h1 className="text-2xl font-bold text-default-900 dark:text-white">
        群列表
      </h1>

      <Card className={GLASS_CARD_CLASS}>
        <CardBody className="space-y-4">
          <Table radius="sm" classNames={TABLE_CLASS_NAMES}>
            <TableHeader>
              <TableColumn>群号</TableColumn>
              <TableColumn>群名</TableColumn>
              <TableColumn>成员数</TableColumn>
              <TableColumn>消息总量</TableColumn>
              <TableColumn>7天消息</TableColumn>
              <TableColumn>活跃成员</TableColumn>
              <TableColumn>爬取</TableColumn>
              <TableColumn>最近活跃</TableColumn>
              <TableColumn>操作</TableColumn>
            </TableHeader>
            <TableBody
              isLoading={isLoading}
              loadingContent={<Spinner />}
              emptyContent="暂无群数据"
            >
              {groups.map((g) => (
                <TableRow key={g.group_id}>
                  <TableCell>
                    <Chip size="sm" variant="flat" color="secondary">
                      {g.group_id}
                    </Chip>
                  </TableCell>
                  <TableCell className="font-medium max-w-[160px] truncate">
                    {g.group_name || "—"}
                  </TableCell>
                  <TableCell>{g.member_count ?? "—"}</TableCell>
                  <TableCell>{g.message_count}</TableCell>
                  <TableCell>{g.last7d_message_count}</TableCell>
                  <TableCell>{g.active_member_count}</TableCell>
                  <TableCell>
                    {g.monitored === null ? (
                      "—"
                    ) : (
                      <Chip
                        size="sm"
                        variant="flat"
                        color={g.monitored ? "success" : "warning"}
                      >
                        {g.monitored ? "监控中" : "已停用"}
                      </Chip>
                    )}
                  </TableCell>
                  <TableCell className="text-default-500 text-sm">
                    {formatTimestamp(g.last_message_time)}
                  </TableCell>
                  <TableCell>
                    <Button
                      isIconOnly
                      size="sm"
                      variant="light"
                      onPress={() => setStatsGroup(g)}
                      aria-label="查看统计"
                    >
                      <MdInsertChart size={18} />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {totalPages > 1 && (
            <div className="flex justify-center">
              <Pagination
                total={totalPages}
                page={page}
                onChange={setPage}
                showControls
              />
            </div>
          )}
        </CardBody>
      </Card>

      {/* 单群统计弹窗 */}
      <Modal
        isOpen={!!statsGroup}
        onClose={() => setStatsGroup(null)}
        size="lg"
        backdrop="blur"
      >
        <ModalContent>
          <ModalHeader className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <MdGroups size={20} className="text-primary-500" />
              {statsGroup?.group_name || "群"}（{statsGroup?.group_id}）
            </div>
          </ModalHeader>
          <ModalBody className="pb-6">
            {statsLoading || !stats ? (
              <div className="flex items-center justify-center py-8">
                <Spinner />
              </div>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-3">
                  <StatItem
                    label="成员数"
                    value={stats.member_count !== null ? String(stats.member_count) : "—"}
                  />
                  <StatItem
                    label="最大成员"
                    value={
                      stats.max_member_count !== null
                        ? String(stats.max_member_count)
                        : "—"
                    }
                  />
                  <StatItem
                    label="消息总量"
                    value={String(stats.message_count)}
                  />
                  <StatItem
                    label="近7天消息"
                    value={String(stats.last7d_message_count)}
                  />
                  <StatItem
                    label="活跃成员"
                    value={String(stats.active_member_count)}
                  />
                  <StatItem
                    label="最近消息"
                    value={formatTimestamp(stats.last_message_time)}
                  />
                </div>
                <Divider />
                <div className="space-y-2 text-sm">
                  <p className="text-default-600 dark:text-default-300">
                    群功能标记：
                    <span className="text-default-900 dark:text-white">
                      {stats.group_function || "—"}
                    </span>
                  </p>
                  <p className="text-default-600 dark:text-default-300">
                    群文件爬取：
                    {stats.monitored === null ? (
                      <span className="text-default-900 dark:text-white">
                        {" "}
                        未监控
                      </span>
                    ) : (
                      <Chip
                        size="sm"
                        variant="flat"
                        color={stats.monitored ? "success" : "warning"}
                        className="ml-1"
                      >
                        {stats.monitored ? "监控中" : "已停用"}
                      </Chip>
                    )}
                  </p>
                  <p className="text-default-600 dark:text-default-300">
                    最近爬取时间：
                    <span className="text-default-900 dark:text-white">
                      {stats.last_crawled_at
                        ? new Date(stats.last_crawled_at).toLocaleString("zh-CN", {
                            hour12: false,
                          })
                        : "—"}
                    </span>
                  </p>
                </div>
              </div>
            )}
          </ModalBody>
        </ModalContent>
      </Modal>
    </motion.div>
  );
}
