"""`src/common/icpc_db_pool.py` 连接失效重试逻辑的离线单测。

不连数据库、不需要 ``nonebot.init()``：``asyncmy`` 只安装在 Linux 部署环境，
这里用一个假的 ``src.common.icpc_database`` 顶替真实引擎模块（它在导入期就会
解析 asyncmy 驱动）。
运行：``python -m unittest discover -s src/common/tests -v``
"""
import asyncio
import contextlib
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

# 必须在导入 icpc_db_pool 之前注入
_FAKE_DB_MODULE = types.ModuleType("src.common.icpc_database")
_FAKE_DB_MODULE.icpc_async_session_factory = None
_FAKE_DB_MODULE.icpc_engine = None
sys.modules.setdefault("src.common.icpc_database", _FAKE_DB_MODULE)

import src.common.icpc_db_pool as icpc_db_pool  # noqa: E402

# uvloop 在已关闭的 transport 上写入时抛出的真实异常形状
HANDLER_CLOSED = RuntimeError(
    "unable to perform operation on <TCPTransport closed=True reading=False "
    "0x55eee6e5cf80>; the handler is closed"
)


class _QueryError(Exception):
    """SQL 本身有问题，重试没有意义。"""


class _FakeResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def mappings(self) -> "_FakeResult":
        return self

    def all(self) -> list[dict]:
        return self._rows


class _FakeSession:
    """探活语句抛 ``error``（None 表示成功），其余语句返回 ``rows``。"""

    def __init__(self, error: Exception | None = None, rows: list[dict] | None = None):
        self.error = error
        self.rows = rows or []
        self.closed = False
        self.statements: list[str] = []

    async def execute(self, statement, params=None) -> _FakeResult:
        self.statements.append(str(statement))
        if self.error is not None:
            raise self.error
        return _FakeResult(self.rows)

    async def close(self) -> None:
        self.closed = True


class _FakeEngine:
    def __init__(self):
        self.dispose_calls = 0

    async def dispose(self) -> None:
        self.dispose_calls += 1


async def _fetch_major_code() -> list[dict]:
    async with icpc_db_pool.get_icpc_db_connection() as db:
        return await db.execute(
            "SELECT code FROM gxu_major WHERE TRIM(code) = %s LIMIT 1",
            ["0714"],
        )


class _Harness:
    """把 icpc_db_pool 的模块级会话工厂/引擎换成可观察的替身。"""

    def __init__(self, sessions: list[_FakeSession]):
        self._queued = list(sessions)
        self.created: list[_FakeSession] = []
        self.engine = _FakeEngine()
        self._stack = contextlib.ExitStack()

    def _factory(self) -> _FakeSession:
        session = self._queued.pop(0)
        self.created.append(session)
        return session

    def __enter__(self) -> "_Harness":
        self._stack.enter_context(
            mock.patch.object(icpc_db_pool, "icpc_async_session_factory", self._factory)
        )
        self._stack.enter_context(mock.patch.object(icpc_db_pool, "icpc_engine", self.engine))
        return self

    def __exit__(self, *exc_info):
        return self._stack.__exit__(*exc_info)


class AcquireHealthySessionTests(unittest.TestCase):
    def test_retries_once_after_stale_connection(self):
        """池中残留的失效连接会被探活发现，重建连接池后重试成功。"""
        stale = _FakeSession(error=HANDLER_CLOSED)
        healthy = _FakeSession(rows=[{"code": "0714"}])

        with _Harness([stale, healthy]) as harness:
            rows = asyncio.run(_fetch_major_code())

        self.assertEqual(rows, [{"code": "0714"}])
        self.assertEqual(len(harness.created), 2)
        self.assertEqual(stale.statements, ["SELECT 1"])  # 坏连接止步于探活
        self.assertTrue(stale.closed)
        self.assertTrue(healthy.closed)
        self.assertEqual(harness.engine.dispose_calls, 1)

    def test_raises_when_connection_failure_persists(self):
        first = _FakeSession(error=HANDLER_CLOSED)
        second = _FakeSession(error=HANDLER_CLOSED)

        with _Harness([first, second]) as harness:
            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(_fetch_major_code())

        self.assertIn("the handler is closed", str(ctx.exception))
        self.assertEqual(len(harness.created), 2)
        self.assertEqual(harness.engine.dispose_calls, 1)  # 只在第一次失败后重建

    def test_does_not_retry_query_errors(self):
        """SQL 语法/参数错误重试是浪费，应当直接抛出。"""
        broken = _FakeSession(error=_QueryError("You have an error in your SQL syntax"))

        with _Harness([broken]) as harness:
            with self.assertRaises(_QueryError):
                asyncio.run(_fetch_major_code())

        self.assertEqual(len(harness.created), 1)
        self.assertEqual(harness.engine.dispose_calls, 0)

    def test_probe_runs_before_handing_session_over(self):
        healthy = _FakeSession(rows=[])

        with _Harness([healthy]):
            asyncio.run(_fetch_major_code())

        self.assertEqual(healthy.statements[0], "SELECT 1")


class IsConnectionErrorTests(unittest.TestCase):
    def test_uvloop_transport_error_is_connection_error(self):
        """裸 RuntimeError 不是 DBAPI 异常，但属于连接失效。"""
        self.assertTrue(icpc_db_pool._is_connection_error(HANDLER_CLOSED))

    def test_os_and_timeout_errors_are_connection_errors(self):
        for exc in (
            OSError("broken pipe"),
            ConnectionResetError("connection reset by peer"),
            TimeoutError("timed out"),
        ):
            with self.subTest(exc=exc):
                self.assertTrue(icpc_db_pool._is_connection_error(exc))

    def test_dbapi_operational_error_is_connection_error(self):
        from sqlalchemy.exc import InterfaceError, OperationalError

        self.assertTrue(
            icpc_db_pool._is_connection_error(
                OperationalError("SELECT 1", {}, Exception("MySQL server has gone away"))
            )
        )
        self.assertTrue(
            icpc_db_pool._is_connection_error(
                InterfaceError("SELECT 1", {}, Exception("Lost connection"))
            )
        )

    def test_sql_error_is_not_connection_error(self):
        self.assertFalse(icpc_db_pool._is_connection_error(_QueryError("syntax error")))


class ApiHealthCheckTests(unittest.TestCase):
    """WebUI 的 ICPC 健康检查必须走探活/重建路径。

    `src/api/bot.py` 依赖 fastapi / jose，本地和 CI 未必装得全，无法导入后断言，
    所以这里退化成源码级检查：健康检查不能再直接使用裸会话工厂。
    """

    def test_icpc_ping_uses_resilient_connection_helper(self):
        source = (
            Path(__file__).resolve().parents[2] / "api" / "bot.py"
        ).read_text(encoding="utf-8")

        self.assertIn("_ping_icpc_mysql()", source)
        self.assertNotIn("_ping_mysql(icpc_async_session_factory)", source)


if __name__ == "__main__":
    unittest.main()
