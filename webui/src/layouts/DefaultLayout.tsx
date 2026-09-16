import { useCallback, useEffect, useRef } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ErrorBoundary } from "react-error-boundary";
import { useIsFetching } from "@tanstack/react-query";
import clsx from "clsx";

import { siteConfig } from "@/config/site";
import { useAuthStore } from "@/store/authStore";
import { useTheme, useLocalStorageState } from "@/hooks/useTheme";
import { useConfirm } from "@/hooks/useConfirm";
import PageBackground from "@/components/PageBackground";
import Sidebar from "@/components/Sidebar";
import BreadcrumbBar from "@/components/BreadcrumbBar";
import ErrorFallback from "@/components/ErrorFallback";
import ConfirmDialog from "@/components/ConfirmDialog";
import PageLoading from "@/components/PageLoading";

export default function DefaultLayout() {
  const [openSideBar, setOpenSideBar] = useLocalStorageState<boolean>(
    "diting_sidebar_open",
    true
  );
  const { isDark, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const logout = useAuthStore((s) => s.logout);
  const user = useAuthStore((s) => s.user);

  const contentRef = useRef<HTMLDivElement>(null);

  // 路由切换平滑回顶
  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, [pathname]);

  // 仅首次加载数据时显示全局遮罩(后台 refetch 不闪烁)
  const pending = useIsFetching({
    predicate: (q) => q.state.status === "pending",
  });

  const {
    isOpen: confirmOpen,
    options,
    confirm,
    handleConfirm,
    handleCancel,
  } = useConfirm();

  const handleLogout = useCallback(() => {
    confirm({
      title: "退出登录",
      message: "确定要退出登录吗？",
      confirmText: "退出",
      color: "danger",
      onConfirm: () => {
        logout();
        navigate("/login");
      },
    });
  }, [confirm, logout, navigate]);

  return (
    <div className="h-screen relative flex items-stretch overflow-hidden">
      <PageBackground />

      <Sidebar
        items={siteConfig.navItems}
        open={openSideBar}
        onClose={() => setOpenSideBar(false)}
        isDark={isDark}
        onToggleTheme={toggleTheme}
        onLogout={handleLogout}
        userName={user?.qq}
      />

      <motion.div
        ref={contentRef}
        layout
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4 }}
        className={clsx(
          "flex-1 overflow-y-auto",
          "transition-all duration-300 ease-in-out",
          "pb-10 md:pb-0"
        )}
      >
        <BreadcrumbBar
          menus={siteConfig.navItems}
          openSideBar={openSideBar}
          onToggleSideBar={() => setOpenSideBar(!openSideBar)}
        />

        <ErrorBoundary FallbackComponent={ErrorFallback}>
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.1 }}
            className="p-4"
          >
            <Outlet />
          </motion.div>
        </ErrorBoundary>
      </motion.div>

      <PageLoading loading={pending > 0} />

      <ConfirmDialog
        isOpen={confirmOpen}
        title={options?.title ?? ""}
        message={options?.message ?? ""}
        confirmText={options?.confirmText}
        cancelText={options?.cancelText}
        color={options?.color}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </div>
  );
}
