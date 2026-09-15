import { useState } from "react";
import clsx from "clsx";

/**
 * 谛听品牌图标
 * 优先加载 webui/public/logo.jpg（用户自行提供）；
 * 图片缺失或加载失败时回退为内置盾牌 SVG。
 */
const LOGO_IMAGE_PATH = "/logo.jpg";

export default function BrandIcon({ className }: { className?: string }) {
  const [imgError, setImgError] = useState(false);

  if (imgError) {
    return (
      <svg
        viewBox="0 0 24 24"
        fill="currentColor"
        aria-hidden="true"
        className={clsx("text-primary", className)}
      >
        <path d="M20 9V7c0-1.1-.9-2-2-2h-3c0-1.66-1.34-3-3-3S9 3.34 9 5H6c-1.1 0-2 .9-2 2v2c-1.66 0-3 1.34-3 3s1.34 3 3 3v4c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-4c1.66 0 3-1.34 3-3s-1.34-3-3-3M7.5 11.5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5S9.83 13 9 13s-1.5-.67-1.5-1.5M16 17H8v-2h8zm-1-4c-.83 0-1.5-.67-1.5-1.5S14.17 10 15 10s1.5.67 1.5 1.5S15.83 13 15 13" />
      </svg>
    );
  }

  return (
    <img
      src={LOGO_IMAGE_PATH}
      alt="谛听"
      draggable={false}
      onError={() => setImgError(true)}
      className={clsx(
        "object-contain select-none rounded-xl",
        className
      )}
    />
  );
}
