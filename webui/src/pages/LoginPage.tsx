import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardBody, CardHeader } from "@heroui/card";
import { Input } from "@heroui/input";
import { Button } from "@heroui/button";
import { motion } from "framer-motion";
import toast from "react-hot-toast";
import { MdPerson, MdLock } from "react-icons/md";

import { apiPost } from "@/api/client";
import { useAuthStore } from "@/store/authStore";

interface LoginResponse {
  token: string;
  expires_in: number;
}

export default function LoginPage() {
  const [qqNumber, setQqNumber] = useState("");
  const [tempPassword, setTempPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!qqNumber.trim() || !tempPassword.trim()) {
      toast.error("请输入QQ号和临时密码");
      return;
    }

    setLoading(true);
    try {
      const res = await apiPost<LoginResponse>("/auth/login", {
        qq_number: qqNumber.trim(),
        temp_password: tempPassword.trim(),
      });

      if (res.data) {
        login(res.data.token, qqNumber.trim());
        toast.success("登录成功");
        navigate("/permissions", { replace: true });
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "登录失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative">
      {/* Background */}
      <div className="fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-gradient-to-br from-background via-background to-background" />
        <div className="absolute -top-1/4 -left-1/4 w-[600px] h-[600px] rounded-full opacity-30 blur-[120px] bg-primary/40" />
        <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] rounded-full opacity-25 blur-[80px] bg-secondary/30" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 30, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, type: "spring", stiffness: 100 }}
      >
        <Card className="w-full max-w-md bg-white/60 dark:bg-black/40 backdrop-blur-xl border border-white/40 dark:border-white/10 shadow-xl">
          <CardHeader className="flex flex-col items-center gap-2 pt-8 pb-4">
            <div className="h-8 w-1.5 bg-primary rounded-full shadow-sm" />
            <h1 className="text-2xl font-bold text-default-900 dark:text-white">
              谛听 · 权限管理
            </h1>
            <p className="text-sm text-default-500">
              请使用QQ号和临时密码登录
            </p>
          </CardHeader>
          <CardBody className="px-8 pb-8">
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <Input
                label="QQ号"
                placeholder="请输入QQ号"
                value={qqNumber}
                onValueChange={setQqNumber}
                startContent={<MdPerson className="text-default-400" size={20} />}
                variant="bordered"
                radius="lg"
                isRequired
                classNames={{
                  input: "text-sm",
                  inputWrapper: "bg-white/50 dark:bg-black/30 backdrop-blur-sm",
                }}
              />
              <Input
                label="临时密码"
                placeholder="请输入临时密码"
                type="password"
                value={tempPassword}
                onValueChange={setTempPassword}
                startContent={<MdLock className="text-default-400" size={20} />}
                variant="bordered"
                radius="lg"
                isRequired
                classNames={{
                  input: "text-sm",
                  inputWrapper: "bg-white/50 dark:bg-black/30 backdrop-blur-sm",
                }}
              />
              <Button
                type="submit"
                color="primary"
                size="lg"
                radius="full"
                isLoading={loading}
                className="mt-2 font-semibold shadow-lg hover:shadow-xl transition-all duration-300"
              >
                登录
              </Button>
            </form>
            <p className="text-xs text-default-400 text-center mt-4">
              在QQ群中发送「权限 登录」获取临时密码
            </p>
          </CardBody>
        </Card>
      </motion.div>
    </div>
  );
}
