from nonebot import logger, get_plugin_config
from datetime import datetime, timedelta
from typing import Tuple
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.params import CommandArg
from nonebot.adapters import Message
from .config import Config
from .table_generator import generate_table_png_bytes
from ...common import get_icpc_db_connection, utils
from ...common.timer import timer

import time

config = get_plugin_config(Config)

t0 = time.perf_counter()
t1 = time.perf_counter()
logger.info(f"① 获取数据耗时：{(t1 - t0) * 1000:.2f} ms")
class Submission(object):

    """
    获取过题数据
    """

    # @staticmethod
    # def _get_range_sub_records(start_time, end_time):
    #     """获取范围内过题数据"""
    #
    #     try:
    #         with get_icpc_db_connection() as db:
    #             query = utils.GetSQL.read_sql_file(config.GET_RANGE_SUB_RECORDS)
    #             records = db.execute(query, (start_time, end_time, start_time, end_time)).fetchall()
    #             return records
    #     except Exception as e:
    #         logger.error(f"查询过题记录时出错：{e}")
    #         return []

    @staticmethod
    def _get_range_sub_records(start_time, end_time):
        # --------------- 临时假数据 ---------------
        return [
            {
                "real_name": "test1",
                "cf_count": 5,
                "luogu_count": 3,
                "all_count": 8,
                "role_id": 1,
                "school": "GXU"
            },
            {
                "real_name": "test2",
                "cf_count": 2,
                "luogu_count": 4,
                "all_count": 6,
                "role_id": 2,
                "school": "GXU"
            }
        ]
    #     # --------------- 临时假数据 ---------------
    @classmethod
    def get_records_msg(cls, upstream_days: int = 7):
        """获取cf过题消息"""
        end_time: datetime = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start_time: datetime = end_time - timedelta(days=upstream_days)

        records = cls._get_range_sub_records(start_time=start_time, end_time=end_time)
        if not records:
            return f"从上一日开始上溯 {upstream_days} 天没有cf过题记录"
        
        result_msg = f"从上一日开始上溯 {upstream_days} 天cf过题记录如下"
        for record in records:
            result_msg += f"{record['real_name']}: {record['cf_count']} - school: {record['school']}\n"
        result_msg += f"\n从上一日开始上溯 {upstream_days} 天luogu过题记录如下:"
        for record in records:
            result_msg += f"{record['real_name']}: {record['luogu_count']} - school: {record['school']}\n"
        # 去掉最后一个换行符
        result_msg = result_msg.rstrip('\n')
        return result_msg

    @classmethod
    async def create_ranking_table(
            cls,
            upstream_days: int = 7,
            needed_roles: list = [],
            needed_schools: list = [],
            needed_users: list = []
    ) -> Tuple[bool, str, bytes]:

        # 查询范围
        end_time: datetime = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start_time: datetime = end_time - timedelta(days=upstream_days)

        with timer("数据读取"):
            data = cls._get_range_sub_records(start_time=start_time, end_time=end_time)

        if not data:
            return (False, f"前 {upstream_days} 日没有数据", None)

        with timer("数据过滤"):
            # 过滤数据
            # 过滤用户名
            if needed_users:
                new_data = [item for item in data if item.get('real_name', '') in needed_users]
                data = new_data
            # 过滤学校
            if needed_schools:
                new_data = [item for item in data if item.get('school', '') in needed_schools]
                data = new_data
            # 过滤身份
            if needed_roles:
                needed_role_ids: list = []
                for role_name, role_id in config.sub_record_roles_dict.items():
                    if role_name in needed_roles:
                        needed_role_ids.append(role_id)
                new_data = [item for item in data if item.get('role_id', -1) in needed_role_ids]
                data = new_data

        # logger.info(data)

        # 创建存放路径
        # output_dir = os.path.abspath(DiTingData.SUB_RANKING_DIR)
        # output_filename = f"sub_ranking_table-{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        # if not os.path.exists(output_dir):
        #     os.makedirs(output_dir)
        #     logger.debug(f"表格图片存放目录已创建：{output_dir}")
        # output_path = os.path.join(output_dir, output_filename)

        # 3. 组装表头与行数据
        headers = ["排名", "用户名", "CF题数", "洛谷题数", "总题数", "身份", "学校"]
        rows = []
        for i, item in enumerate(data, 1):
            item["rank"] = i
            role_map = {0: "管理员", 1: "现役", 2: "退役", 3: "预备役"}
            item["role_name"] = role_map.get(item.get("role_id", 0), "未知")
            rows.append([
                str(item['rank']),
                item['real_name'],
                str(item['cf_count']),
                str(item['luogu_count']),
                str(item['all_count']),
                item['role_name'],
                item['school'].strip()
            ])
        t1=time.perf_counter()

        # 4. 用 C++ 生成 PNG
        try:
            with timer("cpp图片生成"):
                png_bytes = await generate_table_png_bytes(headers, rows)
            logger.success("过题表格图片已生成")
            return (True, "过题表格生成成功", png_bytes)
        except Exception as e:
            logger.error(f"表格图片生成失败：{str(e)}", exc_info=True)
            return (False, "表格图片生成失败", None)



test_table = on_command("测表格", priority=5, block=True)

@test_table.handle()
async def _(arg: Message = CommandArg()):
    logger.debug("=== 测表格命令已触发 ===")
    days = int(arg.extract_plain_text()) if arg else 7
    ok, msg, png_bytes = await Submission.create_ranking_table(upstream_days=days)
    if not ok:
        await test_table.finish(msg)
    await test_table.finish(MessageSegment.image(png_bytes))