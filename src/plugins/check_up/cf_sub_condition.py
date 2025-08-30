from datetime import datetime, timedelta

from ...common import get_icpc_db_connection

class CFSubmission(object):
    """
    获取cf过题数据
    """

    @staticmethod
    def _get_range_sub_records(start_time, end_time):
        """获取范围内cf过题数据"""
        with get_icpc_db_connection() as db:
            query = """
SELECT
    u.username,
    s.handle,
    COUNT(DISTINCT s.problemName) AS ok_count
FROM cf_all_submissions s
         INNER JOIN user u ON s.handle = u.account
WHERE
    s.creationTime BETWEEN %s AND %s
  AND s.verdict = 'OK'
GROUP BY
    u.username,
    s.handle
ORDER BY
    ok_count DESC;
"""
            records = db.execute(query, (start_time, end_time)).fetchall()
            return records
        
    @classmethod
    def get_records_msg(cls, upstream_days: int = 7):
        """获取cf过题消息"""
        end_time: datetime = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start_time: datetime = end_time - timedelta(days=upstream_days)

        records = cls._get_range_sub_records(start_time=start_time, end_time=end_time)
        if not records:
            return f"从上一日开始上溯 {upstream_days} 天没有cf过题记录"
        
        result_msg = f"从上一日开始上溯 {upstream_days} 天cf过题记录如下:\n"
        for record in records:
            result_msg += f"{record['username']}: {record['ok_count']}\n"

        # 去掉最后一个换行符
        result_msg = result_msg.rstrip('\n')

        return result_msg

            