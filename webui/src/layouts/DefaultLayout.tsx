import { useCallback, useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ErrorBoundary } from "react-error-boundary";
import clsx from "clsx";

import { siteConfig } from "@/config/site";
import { useAuthStore } from "@/store/authStore";
import PageBackground from "@/components/PageBackground";
import Sidebar from "@/components/Sidebar";
import BreadcrumbBar from "@/components/BreadcrumbBar";
import ErrorFallback from "@/components/ErrorFallback";

export default function DefaultLayout() {
  const [openSideBar, setOpenSideBar] = useState(true);
  const [isDark, setIsDark] = useState(
    document.documentElement.classList.contains("dark")
  );
  const navigate = useNavigate();
  const logout = useAuthStore((s) => s.logout);
  const user = useAuthStore((s) => s.user);

  const toggleTheme = useCallback(() => {
    document.documentElement.classList.toggle("dark");
    setIsDark((prev) => !prev);
  }, []);

  const handleLogout = useCallback(() => {
    logout();
    navigate("/login");
  }, [logout, navigate]);

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
    </div>
  );
}
