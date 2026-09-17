"""
Async ICPC DB session provider（SQLAlchemy 2.0 实现）

替代旧的 mysql-connector-python 同步连接池。
通过与 get_icpc_db_connection() 兼容的接口提供异步数据库访问，
并自动将原 MySQL 风格的 %s 占位符转换为 SQLAlchemy text() 所需的 :N 风格。
"""
import contextlib
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from nonebot import logger
from sqlalchemy import text
from sqlalchemy.exc import DisconnectionError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.icpc_database import icpc_async_session_factory, icpc_engine


# uvloop 在已关闭的 transport 上写入时抛出的裸 RuntimeError（uvloop
# UVHandle._ensure_alive）。它不是 DBAPI 异常，而 SQLAlchemy 的 pool_pre_ping
# 只把 DBAPI 异常判定为断连，识别不了它，所以只能按消息内容判定。
_CONNECTION_ERROR_MARKERS = (
    "the handler is closed",
    "unable to perform operation on",
)


def _is_connection_error(exc: BaseException) -> bool:
    """判断异常是否属于连接失效 —— 只有这类异常才可以安全重试。

    SQL 语法错误、参数不匹配等查询本身的错误返回 False，避免无意义的重试。
    OSError 已涵盖 ConnectionError 与 TimeoutError。
    """
    if isinstance(exc, (DisconnectionError, InterfaceError, OperationalError, OSError)):
        return True
    message = str(exc)
    return any(marker in message for marker in _CONNECTION_ERROR_MARKERS)


async def _acquire_healthy_session() -> AsyncSession:
    """获取一个探活通过的会话，必要时重建连接池后重试一次。

    池中连接可能已被服务端或中间网络设备单方面关闭（FIN），此时 uvloop 会在写入
    已关闭的 transport 时抛出 RuntimeError，而 pool_pre_ping 无法把它判定为断连，
    于是坏连接既不会失效也不会被替换，会被反复取出。这里主动执行一次 SELECT 1
    （该语句会触发 checkout 与 pre-ping），失败则丢弃会话、清空连接池后用新连接重试。

    顺序很关键：先 close 把坏连接还给旧池，再 dispose 关闭旧池中所有空闲连接，
    这样重试拿到的必然是全新连接。dispose() 只影响池中的空闲连接，不会打断其它
    协程正在进行的查询。
    """
    for attempt in (1, 2):
        session = icpc_async_session_factory()
        try:
            await session.execute(text("SELECT 1"))
        except Exception as e:
            # 连接已失效时 close() 会再次尝试回滚并抛错，这里只需放弃该会话
            with contextlib.suppress(Exception):
                await session.close()
            if attempt == 2 or not _is_connection_error(e):
                raise
            logger.warning(
                f"ICPC DB 连接失效（{type(e).__name__}: {e}），重建连接池后重试"
            )
            await icpc_engine.dispose()
            continue
        return session

    raise RuntimeError("ICPC DB 会话获取失败：重试次数已用尽")


class IcpcSession:
    """异步 ICPC 数据库会话包装器

    提供与旧 MySQLConnection 兼容的接口：
    - execute(query, params) → list[dict]（替代 fetchall()）
    - execute_many(query, params_list) → None

    自动将 %s 占位符转换为 SQLAlchemy 兼容的 :N 数字占位符。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _adapt_sql(sql: str) -> str:
        """将 MySQL 风格的 %s 占位符转换为 SQLAlchemy :N 数字占位符。

        使用带计数器的替换函数确保顺序递增：
        %s, %s, %s → :1, :2, :3
        """
        counter = [0]

        def _replacer(_match: re.Match[str]) -> str:
            counter[0] += 1
            return f":{counter[0]}"

        return re.sub(r"%s", _replacer, sql)

    async def execute(self, query: str, params: Any = None) -> list[dict]:
        """执行 SQL 查询并返回字典列表（与旧 fetchall() 行为一致）。

        参数：
            query: SQL 查询字符串，可包含 %s 占位符
            params: 参数列表/元组（可选）

        返回：
            list[dict] — 行字典列表
        """
        if params is None:
            params = []
        if isinstance(params, tuple):
            params = list(params)
        if not isinstance(params, list):
            params = [params]

        adapted_sql = self._adapt_sql(query)

        # 构建参数字典：{:1 → params[0], :2 → params[1], ...}
        param_dict: dict[str, Any] = {}
        for i, val in enumerate(params, 1):
            param_dict[str(i)] = val

        try:
            result = await self._session.execute(text(adapted_sql), param_dict)
            rows = result.mappings().all()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(
                f"ICPC DB 查询失败：{query[:200]}... | {type(e).__name__}: {e}"
            )
            raise

    async def execute_many(self, query: str, params_list: list[list]) -> None:
        """执行批量操作（多条 INSERT/UPDATE）。

        参数：
            query: SQL 查询字符串，可包含 %s 占位符
            params_list: 参数行列表
        """
        adapted_sql = self._adapt_sql(query)
        for params in params_list:
            param_dict: dict[str, Any] = {}
            for i, val in enumerate(params, 1):
                param_dict[str(i)] = val
            await self._session.execute(text(adapted_sql), param_dict)
        await self._session.commit()


@asynccontextmanager
async def get_icpc_db_connection() -> AsyncGenerator[IcpcSession, None]:
    """获取 ICPC 数据库异步会话上下文管理器。

    会话在交出前已探活（必要时重建连接池并重试一次），因此调用方的查询不会因为
    池中残留的失效连接而失败。

    用法:
        async with get_icpc_db_connection() as db:
            rows = await db.execute(\"SELECT * FROM user WHERE id = %s\", [42])
    """
    session = await _acquire_healthy_session()
    try:
        yield IcpcSession(session)
    finally:
        # 会话连接已失效时 close() 会尝试回滚并再次抛错，此处无需上报
        with contextlib.suppress(Exception):
            await session.close()


async def close_icpc_engine() -> None:
    """释放 ICPC 引擎（用于优雅关闭）。"""
    await icpc_engine.dispose()
    logger.info("ICPC 数据库引擎已释放。")
