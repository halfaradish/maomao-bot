"""`src/plugins/group_sentinel/auditor.py` 审核判定的离线单测。

不连数据库：用假的 ``get_icpc_db_connection`` 顶替（``asyncmy`` 只安装在 Linux
部署环境）。模块按文件路径加载，避免导入 group_sentinel 包时注册 nonebot 匹配器。
运行：``python -m unittest discover -s src/common/tests -v``
"""
import asyncio
import importlib.util
import sys
import types
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest import mock

_FAKE_DB_MODULE = types.ModuleType("src.common.icpc_database")
_FAKE_DB_MODULE.icpc_async_session_factory = None
_FAKE_DB_MODULE.icpc_engine = None
sys.modules.setdefault("src.common.icpc_database", _FAKE_DB_MODULE)

AUDITOR_PATH = (
    Path(__file__).resolve().parents[2] / "plugins" / "group_sentinel" / "auditor.py"
)


def _load_auditor():
    spec = importlib.util.spec_from_file_location(
        "group_sentinel_auditor_under_test", AUDITOR_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auditor = _load_auditor()

# 线上真实入群申请：学号前 6 位 260714 → 年级 26、专业编码 0714
COMMENT = "问题：请输入学号前六位\n答案：260714"
HANDLER_CLOSED = RuntimeError(
    "unable to perform operation on <TCPTransport closed=True reading=False "
    "0x55eee6e5cf80>; the handler is closed"
)


def _fake_connection(rows=None, error=None):
    """构造替换 get_icpc_db_connection 的假上下文管理器。"""

    class _Session:
        async def execute(self, query, params=None):
            if error is not None:
                raise error
            return rows if rows is not None else []

    @asynccontextmanager
    async def _connection():
        yield _Session()

    return _connection


class MajorCodeExistsTests(unittest.TestCase):
    def test_returns_true_when_code_found(self):
        with mock.patch.object(
            auditor, "get_icpc_db_connection", _fake_connection(rows=[{"code": "0714"}])
        ):
            self.assertTrue(asyncio.run(auditor._major_code_exists("0714")))

    def test_returns_false_when_code_absent(self):
        with mock.patch.object(
            auditor, "get_icpc_db_connection", _fake_connection(rows=[])
        ):
            self.assertFalse(asyncio.run(auditor._major_code_exists("0714")))

    def test_raises_lookup_error_on_query_failure(self):
        """查询失败必须抛错，不能被当成编码不存在。"""
        with mock.patch.object(
            auditor, "get_icpc_db_connection", _fake_connection(error=HANDLER_CLOSED)
        ):
            with self.assertRaises(auditor.MajorCodeLookupError):
                asyncio.run(auditor._major_code_exists("0714"))


class AuditJoinRequestTests(unittest.TestCase):
    def _audit(self, rows=None, error=None):
        with mock.patch.object(
            auditor, "get_icpc_db_connection", _fake_connection(rows=rows, error=error)
        ):
            return asyncio.run(
                auditor.audit_join_request(COMMENT, 2698737146, 101974491)
            )

    def test_approves_existing_major_code(self):
        self.assertEqual(self._audit(rows=[{"code": "0714"}]), (True, ""))

    def test_reports_query_failure_instead_of_missing_code(self):
        """复现线上 bug：查询失败曾被误报为专业编码不存在。"""
        approved, reason = self._audit(error=HANDLER_CLOSED)

        self.assertFalse(approved)
        self.assertNotEqual(reason, "专业编码不存在")
        self.assertIn("查询失败", reason)

    def test_reports_missing_code_when_lookup_succeeds_empty(self):
        self.assertEqual(self._audit(rows=[]), (False, "专业编码不存在"))

    def test_rejects_grade_out_of_range(self):
        with mock.patch.object(auditor, "get_icpc_db_connection", _fake_connection()):
            result = asyncio.run(auditor.audit_join_request("答案：990714", 1, 1))
        self.assertEqual(result, (False, "学号年级不在允许范围"))

    def test_rejects_malformed_student_id(self):
        with mock.patch.object(auditor, "get_icpc_db_connection", _fake_connection()):
            result = asyncio.run(auditor.audit_join_request("答案：26071", 1, 1))
        self.assertEqual(result, (False, "学号格式错误"))


if __name__ == "__main__":
    unittest.main()
