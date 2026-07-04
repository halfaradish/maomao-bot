import { useState } from "react";
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
import { MdSearch } from "react-icons/md";
import { motion } from "framer-motion";

import { usePermissionPoints } from "@/api/hooks";

export default function PointsPage() {
  const [page, setPage] = useState(1);
  const [pluginFilter, setPluginFilter] = useState("");
  const [activeFilter, setActiveFilter] = useState("");

  const { data, isLoading } = usePermissionPoints(page, 20, activeFilter || undefined);

  const points = data?.data?.items ?? [];
  const total = data?.data?.total ?? 0;
  const totalPages = Math.ceil(total / 20);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setActiveFilter(pluginFilter);
    setPage(1);
  };

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
          <form onSubmit={handleSearch} className="flex gap-2">
            <Input
              placeholder="按插件名筛选"
              value={pluginFilter}
              onValueChange={setPluginFilter}
              variant="bordered"
              radius="lg"
              className="flex-1"
            />
            <Button
              type="submit"
              color="primary"
              startContent={<MdSearch size={18} />}
            >
              筛选
            </Button>
            {activeFilter && (
              <Button
                variant="light"
                onPress={() => {
                  setPluginFilter("");
                  setActiveFilter("");
                  setPage(1);
                }}
              >
                清除
              </Button>
            )}
          </form>

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
