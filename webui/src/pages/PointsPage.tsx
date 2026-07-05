import { useState, useMemo, useRef, useEffect, useCallback } from "react";
import { Card, CardBody } from "@heroui/card";
import { Input } from "@heroui/input";
import { Button } from "@heroui/button";
import {
  Table,
  TableHeader,
  TableColumn,
  TableBody,
  TableRow,
  TableCell,
} from "@heroui/table";
import { Pagination } from "@heroui/pagination";
import { Spinner } from "@heroui/spinner";
import { Chip } from "@heroui/chip";
import { motion, AnimatePresence } from "framer-motion";

import { usePermissionPoints, usePermissionPlugins } from "@/api/hooks";

export default function PointsPage() {
  const [page, setPage] = useState(1);
  const [inputValue, setInputValue] = useState("");
  const [activeFilter, setActiveFilter] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const { data, isLoading } = usePermissionPoints(page, 20, activeFilter || undefined);
  const { data: pluginsData } = usePermissionPlugins();

  const points = data?.data?.items ?? [];
  const total = data?.data?.total ?? 0;
  const totalPages = Math.ceil(total / 20);

  const pluginNames = useMemo(() => {
    return pluginsData?.data?.plugins ?? [];
  }, [pluginsData]);

  const filteredPlugins = useMemo(() => {
    if (!inputValue.trim()) return pluginNames;
    const lower = inputValue.toLowerCase();
    return pluginNames.filter((name) => name.toLowerCase().includes(lower));
  }, [pluginNames, inputValue]);

  // 点击外部关闭下拉
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelect = useCallback((name: string) => {
    setInputValue(name);
    setActiveFilter(name);
    setShowDropdown(false);
    setPage(1);
  }, []);

  const handleClear = useCallback(() => {
    setInputValue("");
    setActiveFilter("");
    setShowDropdown(false);
    setPage(1);
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") {
        e.preventDefault();
        // 回车时如果有输入值则按输入值筛选（模糊匹配取第一个，或直接用输入值）
        if (inputValue.trim()) {
          const match = pluginNames.find((n) =>
            n.toLowerCase().includes(inputValue.toLowerCase())
          );
          if (match) {
            setActiveFilter(match);
            setInputValue(match);
          } else {
            setActiveFilter(inputValue);
          }
        }
        setShowDropdown(false);
        setPage(1);
      } else if (e.key === "Escape") {
        setShowDropdown(false);
      }
    },
    [inputValue, pluginNames]
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="space-y-4"
    >
      <h1 className="text-2xl font-bold text-default-900">权限点目录</h1>

      <Card className="bg-white/60 dark:bg-black/40 backdrop-blur-xl border border-white/40 dark:border-white/10 shadow-sm">
        <CardBody className="space-y-4">
          {/* Filter */}
          <div className="flex gap-2 items-end">
            <div ref={wrapperRef} className="relative flex-1">
              <Input
                placeholder="按插件名筛选（支持模糊搜索）"
                value={inputValue}
                onValueChange={(v) => {
                  setInputValue(v);
                  setShowDropdown(true);
                }}
                onFocus={() => setShowDropdown(true)}
                onKeyDown={handleKeyDown}
                variant="bordered"
                radius="lg"
                isClearable
                onClear={handleClear}
              />
              {/* 下拉建议列表 */}
              <AnimatePresence>
                {showDropdown && filteredPlugins.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: -8, scaleY: 0.95 }}
                    animate={{ opacity: 1, y: 0, scaleY: 1 }}
                    exit={{ opacity: 0, y: -8, scaleY: 0.95 }}
                    transition={{ duration: 0.15, ease: "easeOut" }}
                    className="absolute z-50 top-full mt-1 w-full origin-top bg-white dark:bg-default-50 border border-default-200 rounded-lg shadow-lg max-h-[300px] overflow-y-auto"
                  >
                    {filteredPlugins.map((name, i) => (
                      <motion.div
                        key={name}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.12, delay: Math.min(i * 0.02, 0.2) }}
                        className="px-3 py-2 cursor-pointer hover:bg-default-100 active:bg-default-200 transition-colors"
                        onMouseDown={(e) => {
                          // 用 onMouseDown 而非 onClick，保证在 input blur 之前触发
                          e.preventDefault();
                          handleSelect(name);
                        }}
                      >
                        <Chip size="sm" variant="flat" color="secondary">
                          {name}
                        </Chip>
                      </motion.div>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            {activeFilter && (
              <Button variant="light" onPress={handleClear}>
                清除
              </Button>
            )}
          </div>

          {/* Table */}
          <Table
            radius="sm"
            classNames={{
              wrapper: "bg-transparent shadow-none",
              th: "bg-white/40 dark:bg-white/5 backdrop-blur-md text-default-600",
            }}
          >
            <TableHeader>
              <TableColumn>插件</TableColumn>
              <TableColumn>权限点 Key</TableColumn>
              <TableColumn>名称</TableColumn>
              <TableColumn>描述</TableColumn>
            </TableHeader>
            <TableBody
              isLoading={isLoading}
              loadingContent={<Spinner />}
              emptyContent="暂无权限点"
            >
              {points.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <Chip size="sm" variant="flat" color="secondary">
                      {p.plugin_name}
                    </Chip>
                  </TableCell>
                  <TableCell>
                    <Chip size="sm" variant="flat" color="primary">
                      {p.perm_key}
                    </Chip>
                  </TableCell>
                  <TableCell className="font-medium">{p.name}</TableCell>
                  <TableCell className="text-default-500">
                    {p.description || "-"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {/* Pagination */}
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
    </motion.div>
  );
}
