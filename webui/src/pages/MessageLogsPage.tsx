import { useState } from "react";
import { Card, CardBody } from "@heroui/card";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";
import { DatePicker } from "@heroui/date-picker";
import { Divider } from "@heroui/divider";
import { Input } from "@heroui/input";
import type { ZonedDateTime } from "@internationalized/date";
import {
  Modal,
  ModalContent,
  ModalHeader,
  ModalBody,
} from "@heroui/modal";
import { Pagination } from "@heroui/pagination";
import { Select, SelectItem } from "@heroui/select";
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
import { MdSearch } from "react-icons/md";

import { useMessageLogs } from "@/api/hooks";
import { GLASS_CARD_CLASS, TABLE_CLASS_NAMES, PAGE_SIZE } from "@/constants";
import { formatTimestamp } from "@/utils/format";
import type { MessageLog, MessageLogFilters } from "@/types/api";

const TYPE_CHIP: Record<string, { color: "secondary" | "primary" | "default"; label: string }> = {
  group: { color: "secondary", label: "群聊" },
  private: { color: "primary", label: "私聊" },
};

/** 日历弹层：圆角磨砂玻璃（对齐全局玻璃拟态风格） */
const DATE_PICKER_CLASS_NAMES = {
  popoverContent:
    "rounded-2xl bg-white/70 dark:bg-default-50/60 backdrop-blur-xl backdrop-saturate-150 border border-white/40 dark:border-white/10 shadow-lg",
};

function zdtToUnix(value: ZonedDateTime | null): number | undefined {
  if (!value) return undefined;
  return Math.floor(value.toDate().getTime() / 1000);
}

export default function MessageLogsPage() {
  // 草稿筛选（输入框值）与已应用筛选分离，点击「查询」才触发请求
  const [groupIdStr, setGroupIdStr] = useState("");
  const [userIdStr, setUserIdStr] = useState("");
  const [keyword, setKeyword] = useState("");
  const [messageType, setMessageType] = useState<string | null>(null);
  const [startValue, setStartValue] = useState<ZonedDateTime | null>(null);
  const [endValue, setEndValue] = useState<ZonedDateTime | null>(null);

  const [filters, setFilters] = useState<MessageLogFilters>({});
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<MessageLog | null>(null);

  const { data, isLoading } = useMessageLogs(filters, page, PAGE_SIZE);

  const logs = data?.data?.items ?? [];
  const total = data?.data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  const handleSearch = () => {
    setFilters({
      group_id: groupIdStr ? Number(groupIdStr) : undefined,
      user_id: userIdStr ? Number(userIdStr) : undefined,
      keyword: keyword || undefined,
      message_type: messageType || undefined,
      start_time: zdtToUnix(startValue),
      end_time: zdtToUnix(endValue),
    });
    setPage(1);
  };

  const handleReset = () => {
    setGroupIdStr("");
    setUserIdStr("");
    setKeyword("");
    setMessageType(null);
    setStartValue(null);
    setEndValue(null);
    setFilters({});
    setPage(1);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="space-y-4"
    >
      <h1 className="text-2xl font-bold text-default-900 dark:text-white">
        消息日志
      </h1>

      <Card className={GLASS_CARD_CLASS}>
        <CardBody className="space-y-4">
          {/* 筛选表单 */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Input
              label="群号"
              placeholder="按群号过滤"
              value={groupIdStr}
              onValueChange={setGroupIdStr}
              variant="bordered"
              radius="lg"
            />
            <Input
              label="QQ号"
              placeholder="按发送者过滤"
              value={userIdStr}
              onValueChange={setUserIdStr}
              variant="bordered"
              radius="lg"
            />
            <Input
              label="关键词"
              placeholder="消息内容模糊匹配"
              value={keyword}
              onValueChange={setKeyword}
              variant="bordered"
              radius="lg"
            />
            <Select
              label="消息类型"
              placeholder="全部类型"
              selectedKeys={messageType ? [messageType] : []}
              onSelectionChange={(keys) => {
                const key = Array.from(keys as Set<string>)[0];
                setMessageType(key || null);
              }}
              variant="bordered"
              radius="lg"
            >
              <SelectItem key="group">群聊</SelectItem>
              <SelectItem key="private">私聊</SelectItem>
            </Select>
            <DatePicker
              label="起始时间"
              value={startValue}
              onChange={setStartValue}
              variant="bordered"
              radius="lg"
              granularity="minute"
              hideTimeZone
              classNames={DATE_PICKER_CLASS_NAMES}
            />
            <DatePicker
              label="结束时间"
              value={endValue}
              onChange={setEndValue}
              variant="bordered"
              radius="lg"
              granularity="minute"
              hideTimeZone
              classNames={DATE_PICKER_CLASS_NAMES}
            />
          </div>
          <div className="flex gap-2">
            <Button
              color="primary"
              radius="full"
              variant="shadow"
              startContent={<MdSearch size={18} />}
              onPress={handleSearch}
              isLoading={isLoading}
            >
              查询
            </Button>
            <Button
              variant="flat"
              radius="full"
              className="bg-default-100 dark:bg-default-50/50 text-default-600 font-medium"
              onPress={handleReset}
            >
              重置
            </Button>
            <span className="ml-auto self-center text-sm text-default-500">
              共 {total} 条
            </span>
          </div>

          <Divider />

          {/* 结果表格 */}
          <Table radius="sm" classNames={TABLE_CLASS_NAMES}>
            <TableHeader>
              <TableColumn>时间</TableColumn>
              <TableColumn>群号</TableColumn>
              <TableColumn>发送者</TableColumn>
              <TableColumn>内容</TableColumn>
              <TableColumn>类型</TableColumn>
              <TableColumn>提及</TableColumn>
            </TableHeader>
            <TableBody
              isLoading={isLoading}
              loadingContent={<Spinner />}
              emptyContent="暂无消息记录"
            >
              {logs.map((log) => {
                const typeChip = TYPE_CHIP[log.message_type] || {
                  color: "default" as const,
                  label: log.message_type,
                };
                return (
                  <TableRow
                    key={log.id}
                    className="cursor-pointer"
                    onClick={() => setSelected(log)}
                  >
                    <TableCell className="text-default-500 text-sm whitespace-nowrap">
                      {formatTimestamp(log.time)}
                    </TableCell>
                    <TableCell>
                      {log.group_id !== null ? (
                        <Chip size="sm" variant="flat" color="secondary">
                          {log.group_id}
                        </Chip>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell className="max-w-[140px] truncate">
                      <span className="font-medium">{log.sender_nickname}</span>
                      <span className="text-default-400 text-xs ml-1">
                        {log.user_id}
                      </span>
                    </TableCell>
                    <TableCell className="max-w-[300px] truncate text-default-600 dark:text-default-300">
                      {log.raw_message}
                    </TableCell>
                    <TableCell>
                      <Chip size="sm" variant="flat" color={typeChip.color}>
                        {typeChip.label}
                      </Chip>
                    </TableCell>
                    <TableCell>
                      {log.to_me ? (
                        <Chip size="sm" variant="flat" color="primary">
                          @机器人
                        </Chip>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
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

      {/* 消息详情弹窗 */}
      <Modal
        isOpen={!!selected}
        onClose={() => setSelected(null)}
        size="2xl"
        backdrop="blur"
        scrollBehavior="inside"
      >
        <ModalContent>
          <ModalHeader className="flex flex-col gap-1">
            消息详情
            <p className="text-sm font-normal text-default-500">
              {formatTimestamp(selected?.time)} · {selected?.sender_nickname}（
              {selected?.user_id}）
              {selected?.group_id != null && ` · 群 ${selected.group_id}`}
            </p>
          </ModalHeader>
          <ModalBody className="pb-6 space-y-3">
            {selected?.sender_card && (
              <p className="text-sm text-default-500">
                群名片：{selected.sender_card}
              </p>
            )}
            <Divider />
            <div className="whitespace-pre-wrap break-all text-default-700 dark:text-default-200 rounded-xl bg-default-100/50 dark:bg-white/5 p-4">
              {selected?.raw_message || "（空消息）"}
            </div>
          </ModalBody>
        </ModalContent>
      </Modal>
    </motion.div>
  );
}
