from datetime import datetime, timedelta
from html2image import Html2Image
from decimal import Decimal
from playwright.async_api import async_playwright
import os

from nonebot import logger

from ...config import DiTingData
from ...common import get_icpc_db_connection

class Submission(object):
    """
    获取过题数据
    """

    @staticmethod
    def _get_range_sub_records(start_time, end_time):
        """获取范围内过题数据"""
        with get_icpc_db_connection() as db:
            query = """
SELECT
    username,
    school,
    SUM(cf_count) AS cf_count,
    SUM(luogu_count) AS luogu_count,
    SUM(all_count) AS all_count
FROM (
        -- 洛谷提交统计
        SELECT
            u.username,
            u.school,
            0 AS cf_count,
            COUNT(DISTINCT sub.pid) AS luogu_count,
            COUNT(DISTINCT sub.pid) AS all_count
        FROM
            luogu_all_submissions AS sub
                JOIN platform_id AS p ON sub.uid = p.luogu
                JOIN user AS u ON p.user_id = u.id
        WHERE
            sub.isPass = 1
                AND sub.subTime BETWEEN %s AND %s
        GROUP BY
            u.username,
            u.school

        UNION ALL

        -- Codeforces提交统计
        SELECT
        u.username,
        u.school,
            COUNT(DISTINCT s.problemName) AS cf_count,
            0 AS luogu_count,
            COUNT(DISTINCT s.problemName) AS all_count
        FROM
            cf_all_submissions s
                JOIN platform_id AS p ON s.handle = p.codeforces
                JOIN user AS u ON p.user_id = u.id
        WHERE
            s.creationTime BETWEEN %s AND %s
        AND s.verdict = 'OK'
        GROUP BY
            u.username,
            u.school
    ) AS combined
GROUP BY
    username,
    school
ORDER BY
    all_count DESC;
"""
            records = db.execute(query, (start_time, end_time, start_time, end_time)).fetchall()
            return records
        
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
            result_msg += f"{record['username']}: {record['cf_count']} - school: {record['school']}\n"
        result_msg += f"\n从上一日开始上溯 {upstream_days} 天luogu过题记录如下:"
        for record in records:
            result_msg += f"{record['username']}: {record['luogu_count']} - school: {record['school']}\n"
        # 去掉最后一个换行符
        result_msg = result_msg.rstrip('\n')
        return result_msg
    
    @classmethod
    async def create_ranking_table(cls, upstream_days: int = 7):
        """
        将数据转化为表格图片
        """
        end_time: datetime = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start_time: datetime = end_time - timedelta(days=upstream_days)
        
        data = cls._get_range_sub_records(
            start_time=start_time,
            end_time=end_time
        )
        if not data:
            return (False, f"前 {upstream_days} 日没有数据")
        logger.info(data)

        # 创建存放路径
        output_dir = os.path.abspath(DiTingData.SUB_RANKING_DIR)
        output_filename = f"sub_ranking_table-{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            logger.debug(f"表格图片存放目录已创建：{output_dir}")
        output_path = os.path.join(output_dir, output_filename)

        # 3. 构建HTML表格（纯内存操作，无需异步）
        headers = ["排名", "用户名", "CF题数", "洛谷题数", "总题数", "学校"]
        # 给数据添加排名
        for i, item in enumerate(data, 1):
            item["rank"] = i

        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body { font-family: "WenQuanYi Micro Hei", "Heiti TC", "Microsoft YaHei", Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; display: flex; justify-content: center; align-items: flex-start; }
                .container { background-color: white; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); overflow: hidden; width: 900px; margin: 0 auto; }
                .header { background-color: #2c3e50; color: white; padding: 15px; text-align: center; font-size: 20px; font-weight: bold; }
                table { width: 100%; border-collapse: collapse; table-layout: fixed; }
                th { background-color: #3498db; color: white; padding: 12px 10px; text-align: center; font-weight: bold; border: 1px solid #2980b9; }
                td { padding: 12px 10px; border: 1px solid #e0e0e0; text-align: center !important; vertical-align: middle; }
                tr:nth-child(even) { background-color: #f8f9fa; }
                tr:hover { background-color: #e8f4fc; }
                .rank { font-weight: bold; color: #2c3e50; width: 60px; }
                .username { text-align: center !important; width: 120px; font-weight: bold; }
                .school { text-align: center !important; width: 180px; }
                .count { font-weight: bold; color: #e74c3c; width: 80px; }
                .total { font-weight: bold; color: #27ae60; width: 80px; }
            </style>
        </head>
        """
        html_content += f"""
        <body>
            <div class="container">
                <div class="header">前 {upstream_days} 日过题数排行榜</div>
                <table>
                    <thead><tr>
        """
        # 添加表头
        for header in headers:
            html_content += f"<th>{header}</th>"
        html_content += "</tr></thead><tbody>"
        # 添加数据行
        for row in data:
            html_content += f"""
            <tr>
                <td class="rank">{row['rank']}</td>
                <td class="username">{row['username']}</td>
                <td class="count">{row['cf_count']}</td>
                <td class="count">{row['luogu_count']}</td>
                <td class="total">{row['all_count']}</td>
                <td class="school">{row['school'].strip()}</td>
            </tr>
            """
        html_content += """
                    </tbody>
                </table>
            </div>
        </body>
        </html>
        """

        # 4. 异步生成图片（用playwright替换html2image）
        image_width = 950
        base_height = 200  # 基础高度（表头+标题）
        row_height = 45    # 每行高度
        image_height = min(base_height + len(data) * row_height, 10000)  # 限制最大高度

        # 异步截图时的优化
        try:
            # 异步启动playwright浏览器（headless=True 无界面模式）
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu", "--font-render-hinting=medium"])  # 增加字体渲染参数
                page = await browser.new_page()
                # 设置页面大小，增加一些边距
                await page.set_viewport_size({"width": 1000, "height": image_height + 50})
                # 异步设置HTML内容（等待页面渲染）
                await page.set_content(html_content, wait_until="networkidle")  # 等待网络空闲，确保CSS加载完成
                # 等待额外时间确保字体完全渲染
                await page.wait_for_timeout(1000)
                # 获取容器元素的边界框，确保精确截图
                container = await page.query_selector(".container")
                if container:
                    box = await container.bounding_box()
                    if box:
                        await container.screenshot(path=output_path)
                    else:
                        await page.screenshot(path=output_path, full_page=True)
                else:
                    await page.screenshot(path=output_path, full_page=True)
                
                await browser.close()  # 异步关闭浏览器

            logger.success(f"过题表格图片已生成：{output_path}")
            return (True, output_path)
        except Exception as e:
            logger.error(f"表格图片生成失败：{str(e)}", exc_info=True)  # exc_info=True 打印完整堆栈
            return (False, None)