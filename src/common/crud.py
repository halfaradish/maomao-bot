"""
异步 CRUD 包装层（SQLAlchemy 实现）

提供 5 个函数：async_create_record / async_get_one / async_get_many /
async_update_records / async_delete_records，支持 Django 风格过滤器
（__in, __lte, __lt, __gte, __gt, __icontains, __contains, __startswith）
和单跳关系遍历（如 group__name__in）。

错误语义：数据库错误原样向上抛出，不转换为 None/[]/0，由调用方决定降级策略。
事务语义：默认每个函数独立提交；传入 session= 时不提交，多个调用可组成同一事务。
"""
from typing import Any, Dict, Iterable, List, Optional, Type

from sqlalchemy import Column, delete, func, inspect, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import RelationshipProperty
from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList

from src.common.database import get_session


# ---- 查询辅助函数 ----


def _apply_lookup(column: Column, lookup: str, value: Any) -> BinaryExpression | BooleanClauseList:
    """
    根据 Django 风格的查找类型生成 SQLAlchemy 条件

    支持的查找类型：
    - exact (默认)  → column == value
    - in            → column.in_(value)
    - lte           → column <= value
    - lt            → column < value
    - gte           → column >= value
    - gt            → column > value
    - icontains     → column.ilike(f"%{value}%")
    - contains      → column.like(f"%{value}%")
    - startswith    → column.startswith(value)
    """
    match lookup:
        case "exact":
            return column == value
        case "in":
            if not isinstance(value, (list, tuple, set)):
                value = [value]
            return column.in_(list(value))
        case "lte":
            return column <= value
        case "lt":
            return column < value
        case "gte":
            return column >= value
        case "gt":
            return column > value
        case "icontains":
            return column.ilike(f"%{value}%")
        case "contains":
            return column.like(f"%{value}%")
        case "startswith":
            return column.like(f"{value}%")
        case _:
            raise ValueError(f"不支持的查找类型: {lookup}")


# 支持的 Django 查找后缀
_LOOKUP_SUFFIXES = frozenset(["in", "lte", "lt", "gte", "gt", "icontains", "contains", "startswith"])


def _parse_filter(model_cls: Type[Any], filters: Dict[str, Any]) -> list[BinaryExpression | BooleanClauseList]:
    """
    将 Django 风格过滤字典转换为 SQLAlchemy where 条件列表

    格式：key__lookup=value
    支持通过关系遍历（如 group__name__in 映射为 relation.has(…)）

    返回可以在 select().where(*conditions) 中使用的条件列表
    """
    conditions: list[BinaryExpression | BooleanClauseList] = []

    for key, value in filters.items():
        parts = key.split("__")

        # 判断最后一部分是否为已知的查找类型
        if parts[-1] in _LOOKUP_SUFFIXES:
            lookup = parts[-1]
            field_parts = parts[:-1]
        else:
            lookup = "exact"
            field_parts = parts

        if len(field_parts) == 1:
            # 直接字段
            column = getattr(model_cls, field_parts[0])
            conditions.append(_apply_lookup(column, lookup, value))
        else:
            # 关系遍历 — 使用 has() / any() 链式调用
            # 当前项目仅用到单跳关系（如 group__name__in），
            # 通用实现支持多层嵌套
            cond = _build_relation_filter(model_cls, field_parts, lookup, value)
            conditions.append(cond)

    return conditions


def _build_relation_filter(
    model_cls: Type[Any],
    field_parts: List[str],
    lookup: str,
    value: Any,
) -> BinaryExpression | BooleanClauseList:
    """
    为关系遍历构建过滤条件

    例如：field_parts=["group", "name"], lookup="in", value=[...]
    → GroupMember.group.has(Group.name.in_(values))
    """
    mapper = inspect(model_cls)

    current_rels: list[RelationshipProperty] = []
    current_model = model_cls

    for i, part in enumerate(field_parts[:-1]):
        rel = mapper.relationships.get(part)
        if rel is None:
            raise ValueError(
                f"模型 '{model_cls.__name__}' 没有名为 '{part}' 的关系，"
                f"无法解析过滤器 '{'__'.join(field_parts)}__{lookup}'"
            )
        current_rels.append(rel)
        current_model = rel.mapper.class_
        mapper = inspect(current_model)

    # 最后一个 field_part 是目标模型上的列
    target_column = getattr(current_model, field_parts[-1])
    inner_condition = _apply_lookup(target_column, lookup, value)

    # 从内到外构建 has() 链（仅支持单跳关系）
    if len(current_rels) > 1:
        raise NotImplementedError(
            f"不支持多跳关系遍历: {'__'.join(field_parts)}__{lookup}。"
            f"仅支持单跳关系如 'group__name__in'。"
        )
    rel_attr = getattr(model_cls, current_rels[-1].key)
    return rel_attr.has(inner_condition)


def _build_order_clauses(model_cls: Type[Any], order_by: Optional[Iterable[str]]):
    """将 Django 风格排序转换为 SQLAlchemy order_by 子句"""
    if not order_by:
        return []
    clauses = []
    for field_expr in order_by:
        if field_expr.startswith("-"):
            col = getattr(model_cls, field_expr[1:])
            clauses.append(col.desc())
        else:
            col = getattr(model_cls, field_expr)
            clauses.append(col.asc())
    return clauses


# ---- 公开 API ----


async def async_create_record(
    model_cls: Type[Any], *, session: Optional[AsyncSession] = None, **fields
) -> Any:
    """
    异步创建记录

    用法同 Django: obj = await async_create_record(MyModel, name="foo", count=1)
    返回创建后的模型实例（flush 后即含自动生成的主键）。

    传入 session 时不提交，由调用方统一 commit；数据库错误向上抛出。
    """
    obj = model_cls(**fields)
    if session is not None:
        session.add(obj)
        await session.flush()
        return obj
    async with get_session() as s:
        s.add(obj)
        await s.flush()
        return obj


async def async_get_one(
    model_cls: Type[Any], *, session: Optional[AsyncSession] = None, **filters
) -> Optional[Any]:
    """
    异步获取单条记录

    用法同 Django: obj = await async_get_one(MyModel, id=1)
    返回第一条匹配记录，无匹配时返回 None。数据库错误向上抛出。
    """
    stmt = select(model_cls).where(*_parse_filter(model_cls, filters)).limit(1)
    if session is not None:
        return (await session.execute(stmt)).scalars().first()
    async with get_session(commit=False) as s:
        return (await s.execute(stmt)).scalars().first()


async def async_get_many(
    model_cls: Type[Any],
    filters: Optional[Dict[str, Any]] = None,
    order_by: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
    *,
    session: Optional[AsyncSession] = None,
) -> List[Any]:
    """
    异步获取多条记录

    用法同 Django:
        rows = await async_get_many(MyModel, filters={"status": "pending"}, order_by=["-created_at"], limit=10)
    数据库错误向上抛出。
    """
    stmt = select(model_cls)
    if filters:
        stmt = stmt.where(*_parse_filter(model_cls, filters))
    if order_by:
        stmt = stmt.order_by(*_build_order_clauses(model_cls, order_by))
    if limit is not None:
        stmt = stmt.limit(limit)
    if session is not None:
        return list((await session.execute(stmt)).scalars().all())
    async with get_session(commit=False) as s:
        return list((await s.execute(stmt)).scalars().all())


async def async_update_records(
    model_cls: Type[Any],
    filters: Dict[str, Any],
    updates: Dict[str, Any],
    *,
    session: Optional[AsyncSession] = None,
) -> int:
    """
    异步更新记录

    用法同 Django:
        affected = await async_update_records(MyModel, {"id": 1}, {"status": "done"})
    返回受影响的行数。数据库错误向上抛出。
    """
    stmt = update(model_cls).where(*_parse_filter(model_cls, filters)).values(**updates)
    if session is not None:
        result = await session.execute(stmt)
        return result.rowcount
    async with get_session() as s:
        result = await s.execute(stmt)
        return result.rowcount


async def async_delete_records(
    model_cls: Type[Any], *, session: Optional[AsyncSession] = None, **filters
) -> int:
    """
    异步删除记录

    用法同 Django:
        deleted = await async_delete_records(MyModel, id=1, user_id=42)
    返回删除的行数。数据库错误向上抛出。
    """
    stmt = delete(model_cls).where(*_parse_filter(model_cls, filters))
    if session is not None:
        result = await session.execute(stmt)
        return result.rowcount
    async with get_session() as s:
        result = await s.execute(stmt)
        return result.rowcount
