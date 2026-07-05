import { useState } from "react";
import { Card, CardBody, CardHeader } from "@heroui/card";
import { Input } from "@heroui/input";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";
import { Spinner } from "@heroui/spinner";
import { Divider } from "@heroui/divider";
import { MdSearch, MdSecurity, MdGroup } from "react-icons/md";
import { motion } from "framer-motion";

import { useUserStatus } from "@/api/hooks";

export default function UserStatusPage() {
  const [userId, setUserId] = useState("");
  const [searchId, setSearchId] = useState(0);

  const { data, isLoading, isError } = useUserStatus(searchId);

  const status = data?.data;

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const id = parseInt(userId);
    if (!isNaN(id) && id > 0) {
      setSearchId(id);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="space-y-4"
    >
      <h1 className="text-2xl font-bold text-default-900">用户权限状态查询</h1>

      <Card className="bg-white/60 dark:bg-black/40 backdrop-blur-xl border border-white/40 dark:border-white/10 shadow-sm">
        <CardBody>
          <form onSubmit={handleSearch} className="flex gap-2">
            <Input
              placeholder="输入 QQ 号查询"
              value={userId}
              onValueChange={setUserId}
              variant="bordered"
              radius="lg"
              isRequired
              className="flex-1"
            />
            <Button
              type="submit"
              color="primary"
              startContent={<MdSearch size={18} />}
            >
              查询
            </Button>
          </form>
        </CardBody>
      </Card>

      {isLoading && searchId > 0 && (
        <div className="flex justify-center py-10">
          <Spinner size="lg" />
        </div>
      )}

      {isError && (
        <Card className="bg-danger-50 dark:bg-danger-900/20 border border-danger-200 dark:border-danger-800">
          <CardBody className="text-center text-danger">
            查询失败，请检查用户是否存在
          </CardBody>
        </Card>
      )}

      {status && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="space-y-4"
        >
          {/* User info */}
          <Card className="bg-white/60 dark:bg-black/40 backdrop-blur-xl border border-white/40 dark:border-white/10 shadow-sm">
            <CardHeader className="flex gap-2 items-center">
              <MdSecurity size={24} className="text-primary" />
              <h2 className="text-lg font-bold">用户 {status.user_id}</h2>
              {status.is_superuser && (
                <Chip color="warning" size="sm" variant="flat">
                  超级管理员
                </Chip>
              )}
            </CardHeader>
            <CardBody className="space-y-3">
              {/* Blacklist status */}
              <div className="flex items-center gap-2">
                <span className="text-default-500 w-20">黑名单:</span>
                {status.blacklisted ? (
                  <Chip color="danger" size="sm">
                    已拉黑 - {status.blacklisted.reason || "无原因"}
                  </Chip>
                ) : (
                  <Chip variant="flat" size="sm">
                    未拉黑
                  </Chip>
                )}
              </div>

              {/* Whitelist status */}
              <div className="flex items-center gap-2">
                <span className="text-default-500 w-20">白名单:</span>
                {status.whitelisted ? (
                  <Chip color="success" size="sm">
                    已加白 - {status.whitelisted.reason || "无原因"}
                  </Chip>
                ) : (
                  <Chip variant="flat" size="sm">
                    未加白
                  </Chip>
                )}
              </div>
            </CardBody>
          </Card>

          {/* Permission groups */}
          <Card className="bg-white/60 dark:bg-black/40 backdrop-blur-xl border border-white/40 dark:border-white/10 shadow-sm">
            <CardHeader className="flex gap-2 items-center">
              <MdGroup size={24} className="text-primary" />
              <h2 className="text-lg font-bold">所属权限组</h2>
            </CardHeader>
            <CardBody>
              {status.permission_groups.length === 0 ? (
                <p className="text-default-500">该用户不属于任何权限组</p>
              ) : (
                <div className="space-y-4">
                  {status.permission_groups.map((group) => (
                    <div
                      key={group.id}
                      className="p-3 rounded-xl bg-default-100 dark:bg-default-50/10"
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <Chip color="primary" size="sm" variant="flat">
                          ID: {group.id}
                        </Chip>
                        <span className="font-medium">
                          {group.display_name || group.name}
                        </span>
                      </div>
                      {group.description && (
                        <p className="text-sm text-default-500 mb-2">
                          {group.description}
                        </p>
                      )}
                      <Divider className="my-2" />
                      <div className="flex flex-wrap gap-1">
                        <span className="text-xs text-default-400 mr-1">
                          权限点:
                        </span>
                        {group.perms.length === 0 ? (
                          <span className="text-xs text-default-400">无</span>
                        ) : (
                          group.perms.map((perm) => (
                            <Chip
                              key={perm}
                              size="sm"
                              variant="flat"
                              color="secondary"
                            >
                              {perm}
                            </Chip>
                          ))
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>
        </motion.div>
      )}
    </motion.div>
  );
}
