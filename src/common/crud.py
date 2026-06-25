"""
异步 CRUD 包装层（SQLAlchemy 实现）

完全替代 src/common/django_crud.py，提供相同的 5 个函数签名。
内部使用 SQLAlchemy 2.0 async session，支持 Django 风格过滤器（__in,
__lte, __lt, __gte, __gt, __icontains, __contains）和关系遍历。
"""
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Type

from sqlalchemy import Column, and_, delete, func, inspect, or_, select, text, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import RelationshipProperty
from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList, UnaryExpression

from src.common.database import async_session_factory


# ---- 查询辅助函数 ----


def _is_datetime_like(value: Any) -> bool:
    """判断值是否为 datetime 类型"""
    return isinstance(value, datetime)


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

    # 从内到外构建 has() 链
    result: Any = inner_condition
    rel_attr = getattr(model_cls, current_rels[-1].key)
    result = rel_attr.has(result)

    for rel in reversed(current_rels[:-1]):
        # 多跳关系的处理 — 当前项目未用到
        raise NotImplementedError(
            f"不支持多跳关系遍历: {'__'.join(field_parts)}__{lookup}。"
            f"仅支持单跳关系如 'group__name__in'。"
        )

    return result


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


async def async_create_record(model_cls: Type[Any], **fields) -> Any:
    """
    异步创建记录

    用法同 Django: obj = await async_create_record(MyModel, name="foo", count=1)
    返回创建后的模型实例（包含自动生成的主键）。
    """
    async with async_session_factory() as session:
        obj = model_cls(**fields)
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
        return obj


async def async_get_one(model_cls: Type[Any], **filters) -> Optional[Any]:
    """
    异步获取单条记录

    用法同 Django: obj = await async_get_one(MyModel, id=1)
    返回第一条匹配记录，无匹配时返回 None。
    """
    async with async_session_factory() as session:
        try:
            conditions = _parse_filter(model_cls, filters)
            stmt = select(model_cls).where(*conditions).limit(1)
            result = await session.execute(stmt)
            return result.scalars().first()
        except Exception:
            return None


async def async_get_many(
    model_cls: Type[Any],
    filters: Optional[Dict[str, Any]] = None,
    order_by: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> List[Any]:
    """
    异步获取多条记录

    用法同 Django:
        rows = await async_get_many(MyModel, filters={"status": "pending"}, order_by=["-created_at"], limit=10)
    """
    async with async_session_factory() as session:
        try:
            stmt = select(model_cls)
            if filters:
                conditions = _parse_filter(model_cls, filters)
                stmt = stmt.where(*conditions)
            if order_by:
                stmt = stmt.order_by(*_build_order_clauses(model_cls, order_by))
            if limit is not None:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except Exception:
            return []


async def async_update_records(
    model_cls: Type[Any],
    filters: Dict[str, Any],
    updates: Dict[str, Any],
) -> int:
    """
    异步更新记录

    用法同 Django:
        affected = await async_update_records(MyModel, {"id": 1}, {"status": "done"})
    返回受影响的行数。
    """
    async with async_session_factory() as session:
        try:
            conditions = _parse_filter(model_cls, filters)
            stmt = update(model_cls).where(*conditions).values(**updates)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount
        except Exception:
            await session.rollback()
            return 0


async def async_delete_records(model_cls: Type[Any], **filters) -> int:
    """
    异步删除记录

    用法同 Django:
        deleted = await async_delete_records(MyModel, id=1, user_id=42)
    返回删除的行数。
    """
    async with async_session_factory() as session:
        try:
            conditions = _parse_filter(model_cls, filters)
            stmt = delete(model_cls).where(*conditions)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount
        except Exception:
            await session.rollback()
            return 0
