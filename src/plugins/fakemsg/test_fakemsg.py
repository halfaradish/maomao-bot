"""伪消息每日额度逻辑测试（独立脚本式，需在仓库根目录运行）：

    .venv/Scripts/python src/plugins/fakemsg/test_fakemsg.py

插件包在导入期依赖 nonebot driver（siqi_auth_client / get_plugin_config），
因此必须先 nonebot.init() 再导入插件模块 —— 这也是本文件不能用
`python -m unittest` 直接加载的原因（unittest 会先导入父包）。

通过 mock dao 层隔离数据库（遵循 CLAUDE.md：测试不连真实数据库），
覆盖点：当日计数读取、计数递增、历史计数清理。
"""
import datetime
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import nonebot  # noqa: E402

nonebot.init()

from src.plugins.fakemsg import dao, scheduler, utils  # noqa: E402


class TestFakemsgDailyUsage(unittest.IsolatedAsyncioTestCase):
    """每日额度逻辑 — dao 层全部 mock"""

    async def test_get_daily_usage_returns_count(self):
        with patch.object(dao, "get_count", return_value=3) as mocked:
            usage = await utils.get_daily_usage("2091842518")
        self.assertEqual(usage, 3)
        mocked.assert_awaited_once_with(2091842518, datetime.date.today())

    async def test_get_daily_usage_zero_means_no_row(self):
        with patch.object(dao, "get_count", return_value=0) as mocked:
            usage = await utils.get_daily_usage("2091842518")
        self.assertEqual(usage, 0)
        mocked.assert_awaited_once_with(2091842518, datetime.date.today())

    async def test_daily_times_addone(self):
        with patch.object(dao, "incr") as mocked:
            await utils.daily_times_addone("123456789")
        mocked.assert_awaited_once_with(123456789, datetime.date.today())

    async def test_cleanup_expired_usage_deletes_before_today(self):
        with patch.object(dao, "delete_before", return_value=2) as mocked:
            deleted = await scheduler.cleanup_expired_usage()
        self.assertEqual(deleted, 2)
        mocked.assert_awaited_once_with(datetime.date.today())

    async def test_cleanup_expired_usage_swallows_exception(self):
        with patch.object(dao, "delete_before", side_effect=RuntimeError("db down")):
            deleted = await scheduler.cleanup_expired_usage()
        self.assertEqual(deleted, 0)


if __name__ == "__main__":
    unittest.main()
