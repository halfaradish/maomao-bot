"""帮助图渲染：缓存读取 → 浏览器池渲染 → 落盘

- get_img / get_detail_img：磁盘缓存命中直接返回；未命中时经单飞锁渲染并落盘，
  并发请求在锁上等待、复用同一份渲染结果。
- BrowserPool：懒启动 Chromium 常驻（参照 llm_scribe 的 HTMLRenderer），
  每次渲染只开关 page/context，空闲超时后关闭整个浏览器进程。
- 失败语义：渲染失败时若有旧缓存图则降级返回并告警，否则返回 None。
"""

import asyncio
from typing import List, Optional

from nonebot import get_plugin_config, logger
from playwright.async_api import async_playwright, Browser, Playwright

from src.common.model.model import PluginUsageInfo

from . import help_cache
from .config import Config

plugin_config = get_plugin_config(Config)


class BrowserPool:
    """懒启动的常驻 Chromium；空闲超时（秒）后自动关闭，<=0 表示常驻不关闭"""

    def __init__(self, idle_timeout: float):
        self._idle_timeout = idle_timeout
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
                logger.info("[cmd_list] 正在启动 Chromium...")
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
                )
        return self._browser

    async def render(self, html_content: str, width: int = 900) -> bytes:
        self._use_epoch += 1
        epoch = self._use_epoch
        try:
            browser = await self._ensure_browser()
            context = await browser.new_context(viewport={"width": width, "height": 800})
            page = await context.new_page()
            try:
                # 模板纯内联样式、无外部资源，等待 domcontentloaded 即可
                await page.set_content(html_content, wait_until="domcontentloaded")
                await page.wait_for_timeout(200)  # 字体/布局渲染缓冲
                return await page.screenshot(type="png", full_page=True)
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
            logger.info("[cmd_list] Chromium 空闲超时，已关闭")
        except Exception as e:
            logger.debug(f"[cmd_list] 关闭 Chromium 失败: {e}")

    async def close(self) -> None:
        await self._close_if_idle(self._use_epoch)


_pool = BrowserPool(idle_timeout=plugin_config.browser_idle_timeout)
# 单飞锁：总览/详情/刷新共用一把，渲染本身低频且共用同一个浏览器
_generate_lock = asyncio.Lock()


def _html_builder(plugins_data: List[PluginUsageInfo], title: str, desc: str) -> Optional[str]:
    try:
        from jinja2 import Environment, FileSystemLoader

        env = Environment(loader=FileSystemLoader(str(help_cache.TEMPLATE_DIR)))
        template = env.get_template(help_cache.HELP_TEMPLATE_FILENAME)
        return template.render(plugins=plugins_data, title=title, desc=desc)
    except Exception as e:
        logger.error(f"渲染帮助HTML失败: {e}")
        return None


def _detail_html_builder(plugin_data: PluginUsageInfo, title: str, desc: str) -> Optional[str]:
    try:
        from jinja2 import Environment, FileSystemLoader

        env = Environment(loader=FileSystemLoader(str(help_cache.TEMPLATE_DIR)))
        template = env.get_template(help_cache.DETAIL_TEMPLATE_FILENAME)
        return template.render(plugin=plugin_data, title=title, desc=desc)
    except Exception as e:
        logger.error(f"渲染详情HTML失败: {e}")
        return None


async def _render_overview(plugins_data: List[PluginUsageInfo]) -> bytes:
    html_content = _html_builder(
        plugins_data=plugins_data,
        title="谛听bot",
        desc="已加载插件列表",
    )
    if not html_content:
        raise RuntimeError("帮助模板渲染失败")
    return await _pool.render(html_content, width=plugin_config.render_width)


async def _render_detail(plugin_data: PluginUsageInfo) -> bytes:
    html_content = _detail_html_builder(
        plugin_data=plugin_data,
        title="插件详情",
        desc=f"{plugin_data.name} 的详细信息",
    )
    if not html_content:
        raise RuntimeError("详情模板渲染失败")
    return await _pool.render(html_content, width=plugin_config.render_width)


async def get_img(plugins_data: List[PluginUsageInfo]) -> Optional[bytes]:
    """总览图：磁盘缓存命中直接返回；未命中时单飞渲染并落盘"""
    expected = help_cache.overview_hash(plugins_data)
    cached = help_cache.get_overview_cache(expected)
    if cached:
        return cached

    async with _generate_lock:
        # 等锁期间可能已被其他请求/预热渲染完成
        cached = help_cache.get_overview_cache(expected)
        if cached:
            return cached

        try:
            png = await _render_overview(plugins_data)
        except Exception as e:
            logger.error(f"[cmd_list] 总览图渲染失败: {e}")
            png = None

        if png:
            help_cache.save_overview_cache(expected, png)
            help_cache.prune_details({p.module_name for p in plugins_data})
            logger.info("[cmd_list] 总览图已重新生成并落盘")
            return png

        # 渲染失败：降级返回旧缓存图（可能是旧内容），完全无缓存则报错
        stale = help_cache.get_overview_stale()
        if stale:
            logger.warning("[cmd_list] 总览图渲染失败，降级返回旧缓存图")
        return stale


async def get_detail_img(plugin_data: PluginUsageInfo) -> Optional[bytes]:
    """详情图：磁盘缓存命中直接返回；未命中时单飞渲染并落盘"""
    module_name = plugin_data.module_name
    expected = help_cache.detail_hash(plugin_data)
    cached = help_cache.get_detail_cache(module_name, expected)
    if cached:
        return cached

    async with _generate_lock:
        cached = help_cache.get_detail_cache(module_name, expected)
        if cached:
            return cached

        try:
            png = await _render_detail(plugin_data)
        except Exception as e:
            logger.error(f"[cmd_list] 插件详情图渲染失败: {module_name}: {e}")
            png = None

        if png:
            help_cache.save_detail_cache(module_name, expected, png)
            logger.info(f"[cmd_list] 插件详情图已生成并落盘: {module_name}")
            return png

        stale = help_cache.get_detail_stale(module_name)
        if stale:
            logger.warning(f"[cmd_list] 插件详情图渲染失败，降级返回旧缓存图: {module_name}")
        return stale


async def refresh_img(plugins_data: List[PluginUsageInfo]) -> Optional[bytes]:
    """手动刷新：清空缓存后强制重建总览图（详情缓存随插件哈希按需重建）"""
    async with _generate_lock:
        help_cache.clear_cache()
        try:
            png = await _render_overview(plugins_data)
        except Exception as e:
            logger.error(f"[cmd_list] 手动刷新总览图失败: {e}")
            return None
        help_cache.save_overview_cache(help_cache.overview_hash(plugins_data), png)
        help_cache.prune_details({p.module_name for p in plugins_data})
        logger.info("[cmd_list] 已手动刷新总览图")
        return png


async def preheat() -> None:
    """启动后台预热：缓存有效则只校验，失效则重建。失败仅记录日志，不影响启动"""
    try:
        from .get_plugin_usage import get_help_usage

        plugins_data = get_help_usage()
        if not plugins_data:
            return

        expected = help_cache.overview_hash(plugins_data)
        if help_cache.get_overview_cache(expected):
            logger.info("[cmd_list] 帮助图缓存有效，跳过预热渲染")
            return

        await get_img(plugins_data)
        logger.info("[cmd_list] 帮助图预热完成")
    except Exception as e:
        logger.warning(f"[cmd_list] 帮助图预热失败（不影响启动）: {e}")


async def shutdown_browser() -> None:
    """进程退出时关闭常驻浏览器"""
    await _pool.close()
