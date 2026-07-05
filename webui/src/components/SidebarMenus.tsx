import { Button } from "@heroui/button";
import clsx from "clsx";
import React from "react";
import { matchPath, useLocation, useNavigate } from "react-router-dom";

import type { MenuItem } from "@/config/site";

interface SidebarMenusProps {
  items: MenuItem[];
}

function renderItem(item: MenuItem, isChild = false) {
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = React.useState(!!item.children?.length);

  const hasChildren = React.useMemo(
    () => item.children && item.children.length > 0,
    [item.children]
  );

  const isActive = React.useMemo(() => {
    if (item.href) {
      return !!matchPath(item.href, location.pathname);
    }
    return false;
  }, [item.href, location.pathname]);

  // Auto-expand parent if child is active
  React.useEffect(() => {
    if (item.children) {
      const shouldOpen = item.children.some(
        (child) => child.href && !!matchPath(child.href, location.pathname)
      );
      if (shouldOpen) setOpen(true);
    }
  }, [item.children, location.pathname]);

  const panelRef = React.useRef<HTMLDivElement>(null);

  return (
    <div key={item.href + item.label}>
      <Button
        className={clsx(
          "flex items-center w-full text-left justify-start dark:text-white transition-all duration-300",
          isActive
            ? "bg-primary/10 text-primary dark:bg-primary/20 dark:text-primary-400 shadow-none font-semibold translate-x-1"
            : "hover:bg-default-100 hover:translate-x-1"
        )}
        color={isActive ? "primary" : "default"}
        endContent={
          hasChildren ? (
            <div
              className={clsx(
                "ml-auto relative w-3 h-3 transition-transform",
                open && "transform rotate-180",
                isActive ? "text-primary-500" : "text-primary-200 dark:text-white",
                "before:rounded-full",
                'before:content-[""]',
                "before:block",
                "before:absolute",
                "before:w-3",
                "before:h-[4.5px]",
                "before:bg-current",
                "before:top-1/2",
                "before:-left-[3px]",
                "before:transform",
                "before:-translate-y-1/2",
                "before:rotate-45",
                "after:rounded-full",
                'after:content-[""]',
                "after:block",
                "after:absolute",
                "after:w-3",
                "after:h-[4.5px]",
                "after:bg-current",
                "after:top-1/2",
                "after:left-[3px]",
                "after:transform",
                "after:-translate-y-1/2",
                "after:-rotate-45"
              )}
            />
          ) : (
            <div
              className={clsx(
                "w-3 h-1.5 rounded-full ml-auto",
                isActive
                  ? "bg-primary-500"
                  : "bg-primary-200 dark:bg-white shadow-lg"
              )}
              aria-hidden="true"
            />
          )
        }
        variant={isActive ? (isChild ? "solid" : "shadow") : "light"}
        onPress={() => {
          if (item.href) {
            if (!isActive) {
              navigate(item.href);
            }
          } else if (hasChildren) {
            setOpen(!open);
          }
        }}
      >
        {item.label}
      </Button>
      <div
        ref={panelRef}
        className="ml-4 overflow-hidden transition-all duration-300"
        style={{
          height: open ? panelRef.current?.scrollHeight ?? "auto" : 0,
        }}
      >
        {item.children?.map((child) => renderItem(child, true))}
      </div>
    </div>
  );
}

export default function SidebarMenus({ items }: SidebarMenusProps) {
  return (
    <div className="flex flex-col justify-content-center flex-1 gap-2">
      {items.map((item) => renderItem(item))}
    </div>
  );
}
