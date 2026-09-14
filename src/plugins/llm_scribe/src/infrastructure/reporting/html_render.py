"""HTML 转图片渲染器（基础设施适配器）。

Chromium 进程管理委托给 src.common.rendering.BrowserPool，
本类仅保留 llm_scribe 渲染端口所需的接口与默认渲染参数
（networkidle 等待、device_scale_factor=2、异常时返回 None）。
"""

from loguru import logger
from typing import Optional, Dict, Any

from src.common.rendering import BrowserPool


class HTMLRenderer:
    """HTML 转图片渲染器"""

    def __init__(self, browser_path: Optional[str] = None):
        # idle_timeout<=0：与旧实现一致，浏览器常驻直到显式 close
        self._pool = BrowserPool(idle_timeout=0, browser_path=browser_path, tag="llm_scribe")

    async def html_render_to_img(
            self,
            html_content: str,
            img_opt: Optional[Dict[str, Any]] = None,
    ) -> Optional[bytes]:
        """渲染 HTML 字符串为图片"""
        image_options = img_opt or {}

        try:
            return await self._pool.render(
                html_content,
                width=image_options.get("width", 750),  # 建议固定宽度，长图更美观
                wait_until="networkidle",
                wait_ms=200,  # 如果模板有渐变或动画，给一点点渲染缓冲时间
                device_scale_factor=2,  # 视网膜屏级别的高清效果
                image_type=image_options.get("type", "jpeg"),
                quality=image_options.get("quality", 95),
                full_page=image_options.get("full_page", True),
            )
        except Exception as e:
            logger.error(f"HTML 渲染异常: {e}", exc_info=True)
            return None

    async def close(self):
        """服务关闭时调用，退出浏览器"""
        await self._pool.close()
