"""prd 插件 — 数据访问层

需求条目存取（原 prd.json 的 to_do → prd_todos 表）。
所有结果经 to_legacy_dict() 转换为原 JSON 字段形状（含 "%Y-%m-%d"
日期字符串），保证 html_gen 与消息构建逻辑零改动。

注意：prd_todos 的自增主键跨环境共享，所有按 id 的读写必须校验
env_tag，避免 dev 环境误改 prod 数据。
"""
from datetime import date

from sqlalchemy import select

from src.common.database import async_session_factory, current_env_tag
from src.common.models.prd_models import PrdTodo

_DATE_FMT = "%Y-%m-%d"


def to_legacy_dict(row: PrdTodo) -> dict:
    """转换为原 JSON 的字段形状"""
    return {
        "id": row.id,
        "finish": row.finish,
        "group": row.group_name,
        "content": row.content,
        "priority": row.priority,
        "create_by": row.create_by or "",
        "create_at": row.create_at.strftime(_DATE_FMT) if row.create_at else "",
        "last_modify_by": row.last_modify_by or "",
        "last_modify_at": row.last_modify_at.strftime(_DATE_FMT) if row.last_modify_at else "",
        "finish_by": row.finish_by or "",
        "finish_at": row.finish_at.strftime(_DATE_FMT) if row.finish_at else "",
        "assign_to": row.assign_to or "",
        "assign_at": row.assign_at.strftime(_DATE_FMT) if row.assign_at else "",
        "assign_by": row.assign_by or "",
    }


async def list_todos() -> list[dict]:
    """返回当前环境全部需求（按编号升序），形状与原 to_do 列表一致"""
    stmt = (
        select(PrdTodo)
        .where(PrdTodo.env_tag == current_env_tag())
        .order_by(PrdTodo.id)
    )
    async with async_session_factory() as session:
        rows = (await session.scalars(stmt)).all()
    return [to_legacy_dict(row) for row in rows]


async def add_todo(content: str, create_by: str) -> dict:
    """新增需求，返回带自增编号的 legacy dict"""
    async with async_session_factory() as session:
        row = PrdTodo(
            env_tag=current_env_tag(),
            content=content,
            finish=False,
            group_name="其他",
            create_by=create_by,
            create_at=date.today(),
        )
        session.add(row)
        await session.flush()
        result = to_legacy_dict(row)
        await session.commit()
        return result


async def remove_todo(todo_id: int) -> dict | None:
    """删除需求，返回被删条目；不存在返回 None"""
    async with async_session_factory() as session:
        row = await session.get(PrdTodo, todo_id)
        if row is None or row.env_tag != current_env_tag():
            return None
        result = to_legacy_dict(row)
        await session.delete(row)
        await session.commit()
        return result


async def update_content(todo_id: int, content: str, last_modify_by: str) -> dict | None:
    """修改需求内容并记录修改人"""
    async with async_session_factory() as session:
        row = await session.get(PrdTodo, todo_id)
        if row is None or row.env_tag != current_env_tag():
            return None
        row.content = content
        row.last_modify_by = last_modify_by or ""
        row.last_modify_at = date.today()
        result = to_legacy_dict(row)
        await session.commit()
        return result


async def toggle_finish(todo_id: int, finish_by: str) -> dict | None:
    """翻转需求完成状态（与原实现一致：取消完成时同样刷新 finish_at/by）"""
    async with async_session_factory() as session:
        row = await session.get(PrdTodo, todo_id)
        if row is None or row.env_tag != current_env_tag():
            return None
        row.finish = not row.finish
        row.finish_at = date.today()
        row.finish_by = finish_by or ""
        result = to_legacy_dict(row)
        await session.commit()
        return result


async def set_group(todo_id: int, group_name: str) -> dict | None:
    """设置需求分组"""
    async with async_session_factory() as session:
        row = await session.get(PrdTodo, todo_id)
        if row is None or row.env_tag != current_env_tag():
            return None
        row.group_name = group_name
        result = to_legacy_dict(row)
        await session.commit()
        return result


async def assign(todo_id: int, assign_to: str, assign_by: str) -> dict | None:
    """为需求分配执行人"""
    async with async_session_factory() as session:
        row = await session.get(PrdTodo, todo_id)
        if row is None or row.env_tag != current_env_tag():
            return None
        row.assign_to = assign_to
        row.assign_at = date.today()
        row.assign_by = assign_by or ""
        result = to_legacy_dict(row)
        await session.commit()
        return result
