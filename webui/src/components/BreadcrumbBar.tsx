import { BreadcrumbItem, Breadcrumbs } from "@heroui/breadcrumbs";
import { Button } from "@heroui/button";
import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import { useMemo } from "react";
import { MdMenu, MdMenuOpen } from "react-icons/md";
import { useLocation } from "react-router-dom";

import type { MenuItem } from "@/config/site";

interface BreadcrumbBarProps {
  menus: MenuItem[];
  openSideBar: boolean;
  onToggleSideBar: () => void;
}

function findTitle(menus: MenuItem[], pathname: string): string[] {
  const paths: string[] = [];

  if (pathname) {
    for (const item of menus) {
      if (item.href === pathname) {
        paths.push(item.label);
      } else if (item.children) {
        const title = findTitle(item.children, pathname);
        if (title.length > 0) {
          paths.push(item.label);
          paths.push(...title);
        }
      }
    }
  }

  return paths;
}

export default function BreadcrumbBar({
  menus,
  openSideBar,
  onToggleSideBar,
}: BreadcrumbBarProps) {
  const location = useLocation();

  const title = useMemo(
    () => findTitle(menus, location.pathname),
    [menus, location.pathname]
  );

  return (
    <div
      className={clsx(
        "h-10 flex items-center font-bold text-xl backdrop-blur-lg rounded-full",
        "dark:bg-background dark:shadow-primary-100",
        "bg-background !bg-opacity-50",
        "shadow-sm shadow-primary-50",
        "z-30 m-2 mb-0 sticky top-2 left-0"
      )}
    >
      <div
        className={clsx(
          "mr-1 ease-in-out ml-0 md:relative z-50 md:z-auto",
          openSideBar && "pl-2",
          "md:!ml-0 md:pl-0"
        )}
      >
        <Button
          isIconOnly
          radius="full"
          variant="light"
          onPress={onToggleSideBar}
        >
          {openSideBar ? <MdMenuOpen size={24} /> : <MdMenu size={24} />}
        </Button>
      </div>
      <Breadcrumbs isDisabled size="lg">
        {title?.map((item, index) => (
          <BreadcrumbItem key={index}>
            <AnimatePresence mode="wait">
              <motion.div
                key={item}
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                transition={{ duration: 0.3 }}
              >
                {item}
              </motion.div>
            </AnimatePresence>
          </BreadcrumbItem>
        ))}
      </Breadcrumbs>
    </div>
  );
}
