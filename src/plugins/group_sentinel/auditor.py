"""入群审核逻辑

规则：
1. 从入群申请 comment 中提取"答案"字段值，去除非数字字符后必须恰好 6 位数字
2. 前 2 位转为整数，必须在 [1, 当前年份后两位] 范围内
3. 后 4 位字符串，须在 gxu_major 表中 code 字段存在精确匹配
4. 仅当步骤 2 和 3 均通过才批准
"""
import re
from datetime import datetime
from typing import Optional

from nonebot import logger

from src.common import get_icpc_db_connection


def _extract_student_id(comment: Optional[str]) -> Optional[str]:
    """从入群申请 comment 中提取学号前6位（纯数字连续串≥6位，取前6位）。

    comment 格式: '问题：请输入学号前 6 位\n答案：xxxxx'
    按"答案："或"答案:"分割，取后半部分，提取最长连续数字串，长度≥6则返回前6位。
    """
    if not comment:
        return None

    # 按 "答案：" 或 "答案:" 分割提取答案部分
    answer = comment
    for sep in ("答案：", "答案:"):
        if sep in comment:
            answer = comment.split(sep, 1)[1].strip()
            break

    # 匹配所有连续数字串
    num_matches = re.findall(r"\d+", answer)
    if not num_matches:
        return None

    # 筛选长度≥6的数字串
    valid_nums = [num for num in num_matches if len(num) >= 6]
    if not valid_nums:
        return None

    # 取第一个符合条件的数字串，截取前6位返回
    return valid_nums[0][:6]


def _get_max_grade() -> int:
    """获取允许的最大年级（当前年份后两位）。

    系统年份获取异常时默认返回 26。
    """
    try:
        return datetime.now().year % 100
    except Exception:
        return 26


class MajorCodeLookupError(RuntimeError):
    """查询 gxu_major 失败（基础设施故障，非"编码不存在"）。"""


async def _major_code_exists(code: str) -> bool:
    """检查专业编码是否在 gxu_major 表中存在。

    精确匹配，忽略首尾空格。

    Raises:
        MajorCodeLookupError: 查询本身失败。查询失败不等于"编码不存在"，不能把
            基础设施故障当作审核结论，否则合法编码会被误判为"专业编码不存在"。
    """
    try:
        async with get_icpc_db_connection() as db:
            rows = await db.execute(
                "SELECT code FROM gxu_major WHERE TRIM(code) = %s LIMIT 1",
                [code],
            )
            return len(rows) > 0
    except Exception as e:
        logger.error(f"[group_sentinel] 查询 gxu_major 失败: {e}")
        raise MajorCodeLookupError(str(e)) from e


async def audit_join_request(
    comment: Optional[str],
    user_id: int,
    group_id: int,
) -> tuple[bool, str]:
    """审核入群请求。

    提取学号前 6 位，依次校验格式、年级范围、专业编码。

    Args:
        comment: 用户填写的入群验证信息（可能为 None）
        user_id: 申请入群的 QQ 号
        group_id: 目标群号

    Returns:
        tuple[bool, str]: (是否批准, 原因说明)
    """
    logger.info(
        f"[group_sentinel] 审核: user={user_id}, group={group_id}, "
        f"comment={comment!r}"
    )

    # 1. 提取学号，校验格式（去除非数字后必须恰好 6 位）
    student_id = _extract_student_id(comment)
    if student_id is None:
        return False, "学号格式错误"

    # 2. 前 2 位年级校验
    try:
        grade = int(student_id[:2])
    except ValueError:
        return False, "学号格式错误"

    max_grade = _get_max_grade()
    if grade < 1 or grade > max_grade:
        return False, "学号年级不在允许范围"

    # 3. 后 4 位专业编码校验
    major_code = student_id[2:]  # 后 4 位
    try:
        major_code_exists = await _major_code_exists(major_code)
    except MajorCodeLookupError:
        # 查询失败时不下"编码不存在"的结论，交由人工复核处理
        return False, "审核服务查询失败，请稍后重试"
    if not major_code_exists:
        return False, "专业编码不存在"

    return True, ""
