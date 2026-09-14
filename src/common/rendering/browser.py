"""基于 Playwright 的 HTML→PNG/JPEG 渲染池。

BrowserPool 懒启动常驻 Chromium：每次渲染只开关 page/context，
空闲超时后关闭整个浏览器进程（<=0 表示常驻不关闭）。
各插件自行持有实例（如 cmd_list / prd / llm_scribe），互不共享进程。
"""

import asyncio
from typing import Optional, Union

from nonebot import logger
from playwright.async_api import async_playwright, Browser, Playwright

# 等待策略别名：直接透传给 set_content 的 wait_until
_WAIT_UNTIL = ("domcontentloaded", "load", "networkidle")


class BrowserPool:
    """懒启动的常驻 Chromium；空闲超时（秒）后自动关闭，<=0 表示常驻不关闭"""

    def __init__(
        self,
        idle_timeout: float = 300.0,
        browser_path: Optional[str] = None,
        tag: str = "rendering",
    ):
        self._idle_timeout = idle_timeout
        self._browser_path = browser_path
        self._tag = tag
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._lock = asyncio.Lock()
        self._use_epoch = 0

    async def _ensure_browser(self) -> Browser:
        if self._browser is not None and self._browser.is_connected():
            return self._browser

        async with self._lock:
            # 双重检查：等锁期间可能已被其他协程启动
            if self._browser is None or not self._browser.is_connected():
                logger.info(f"[{self._tag}] 正在启动 Chromium...")
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    executable_path=self._browser_path,
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
                )
        return self._browser

    async def render(
        self,
        html_content: str,
        width: int = 900,
        *,
        wait_until: str = "domcontentloaded",
        wait_ms: int = 200,
        device_scale_factor: int = 1,
        image_type: str = "png",
        quality: Optional[int] = None,
        full_page: bool = True,
    ) -> bytes:
        """渲染 HTML 字符串为图片字节。

        Args:
            html_content: 完整 HTML 文档或片段
            width: 视口宽度（高度由 full_page 决定时仅影响布局）
            wait_until: set_content 等待策略；含外部资源的模板建议 networkidle
            wait_ms: 截图前的渲染缓冲毫秒数（字体/动画）
            device_scale_factor: 缩放倍率，2 即视网膜清晰度
            image_type: png 或 jpeg
            quality: jpeg 质量（1-100），png 时忽略
            full_page: 是否截取整个页面高度
        """
        if wait_until not in _WAIT_UNTIL:
            raise ValueError(f"非法 wait_until: {wait_until!r}，可选 {_WAIT_UNTIL}")

        self._use_epoch += 1
        epoch = self._use_epoch
        try:
            browser = await self._ensure_browser()
            context = await browser.new_context(
                viewport={"width": width, "height": 800},
                device_scale_factor=device_scale_factor,
            )
            page = await context.new_page()
            try:
                await page.set_content(html_content, wait_until=wait_until)
                if wait_ms > 0:
                    await page.wait_for_timeout(wait_ms)  # 字体/布局渲染缓冲
                return await page.screenshot(
                    type=image_type,
                    quality=quality if image_type == "jpeg" else None,
                    full_page=full_page,
                )
            finally:
                await context.close()
        finally:
            self._schedule_idle_close(epoch)

    def _schedule_idle_close(self, epoch: int) -> None:
        if self._idle_timeout <= 0:
            return

        async def _close_when_idle():
            await asyncio.sleep(self._idle_timeout)
            await self._close_if_idle(epoch)

        asyncio.create_task(_close_when_idle())

    async def _close_if_idle(self, epoch: int) -> None:
        async with self._lock:
            # epoch 变化说明期间有新渲染，放弃关闭
            if epoch != self._use_epoch or self._browser is None:
                return
            browser, self._browser = self._browser, None
            playwright, self._playwright = self._playwright, None
        try:
            await browser.close()
            if playwright:
                await playwright.stop()
            logger.info(f"[{self._tag}] Chromium 空闲超时，已关闭")
        except Exception as e:
            logger.debug(f"[{self._tag}] 关闭 Chromium 失败: {e}")

    async def close(self) -> None:
        """立即关闭（无论是否空闲），用于进程退出钩子"""
        await self._close_if_idle(self._use_epoch)
