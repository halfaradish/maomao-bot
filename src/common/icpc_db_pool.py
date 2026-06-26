"""
Async ICPC DB session provider（SQLAlchemy 2.0 实现）

替代旧的 mysql-connector-python 同步连接池。
通过与 get_icpc_db_connection() 兼容的接口提供异步数据库访问，
并自动将原 MySQL 风格的 %s 占位符转换为 SQLAlchemy text() 所需的 :N 风格。
"""
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from nonebot import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.icpc_database import icpc_async_session_factory


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
        except Exception:
            logger.error(f"ICPC DB 查询失败：{query[:200]}...")
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

    用法:
        async with get_icpc_db_connection() as db:
            rows = await db.execute(\"SELECT * FROM user WHERE id = %s\", [42])
    """
    async with icpc_async_session_factory() as session:
        yield IcpcSession(session)


async def close_icpc_engine() -> None:
    """释放 ICPC 引擎（用于优雅关闭）。"""
    from src.common.icpc_database import icpc_engine

    await icpc_engine.dispose()
    logger.info("ICPC 数据库引擎已释放。")
