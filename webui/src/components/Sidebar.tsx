import { Button } from "@heroui/button";
import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import { IoMdLogOut } from "react-icons/io";
import { MdDarkMode, MdLightMode } from "react-icons/md";

import type { MenuItem } from "@/config/site";
import SidebarMenus from "./SidebarMenus";

interface SidebarProps {
  open: boolean;
  items: MenuItem[];
  onClose?: () => void;
  isDark: boolean;
  onToggleTheme: () => void;
  onLogout: () => void;
  userName?: string;
}

export default function Sidebar({
  open,
  items,
  onClose,
  isDark,
  onToggleTheme,
  onLogout,
  userName,
}: SidebarProps) {
  return (
    <>
      {/* Mobile overlay */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            className="fixed inset-y-0 left-64 right-0 bg-black/20 backdrop-blur-[1px] z-40 md:hidden"
            aria-hidden="true"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 0.15 } }}
            transition={{ duration: 0.2, delay: 0.15 }}
          />
        )}
      </AnimatePresence>

      {/* Sidebar container */}
      <motion.div
        className={clsx(
          "overflow-hidden fixed top-0 left-0 h-full z-50 md:static",
          "md:shadow-none rounded-r-2xl md:rounded-none",
          "bg-content1/70 backdrop-blur-xl backdrop-saturate-150 shadow-xl",
          "md:bg-transparent md:backdrop-blur-none md:backdrop-saturate-100 md:shadow-none"
        )}
        initial={{ width: 0 }}
        animate={{ width: open ? "16rem" : 0 }}
        transition={{
          type: open ? "spring" : "tween",
          stiffness: 150,
          damping: open ? 15 : 10,
        }}
        style={{ overflow: "hidden" }}
      >
        <motion.div className="w-64 flex flex-col items-stretch h-full transition-transform duration-300 ease-in-out z-30 relative float-right p-4">
          {/* Logo */}
          <div className="flex items-center justify-start gap-3 px-2 my-8 ml-2">
            <div className="h-5 w-1 bg-primary rounded-full shadow-sm" />
            <div className="text-xl font-bold tracking-wide select-none text-default-900 dark:text-white">
              谛听
            </div>
          </div>

          {/* Menu */}
          <div className="overflow-y-auto flex flex-col flex-1 px-2">
            <SidebarMenus items={items} />

            {/* Bottom actions */}
            <div className="mt-auto mb-10 md:mb-0 space-y-3 px-2">
              {userName && (
                <div className="text-sm text-default-500 text-center py-2">
                  QQ: {userName}
                </div>
              )}
              <Button
                className="w-full bg-primary-50/50 hover:bg-primary-100/80 text-primary-600 font-medium shadow-sm hover:shadow-md transition-all duration-300 backdrop-blur-sm"
                radius="full"
                variant="flat"
                onPress={onToggleTheme}
                startContent={
                  !isDark ? <MdLightMode size={18} /> : <MdDarkMode size={18} />
                }
              >
                切换主题
              </Button>
              <Button
                className="w-full mb-2 bg-danger-50/50 hover:bg-danger-100/80 text-danger-500 font-medium shadow-sm hover:shadow-md transition-all duration-300 backdrop-blur-sm"
                radius="full"
                variant="flat"
                onPress={onLogout}
                startContent={<IoMdLogOut size={18} />}
              >
                退出登录
              </Button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </>
  );
}
