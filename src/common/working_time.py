import datetime
from collections import defaultdict
from datetime import timedelta

from ..config import CheckUpDay
from . import get_icpc_db_connection

day_start_hours = CheckUpDay.DAY_START
day_end_hours = CheckUpDay.DAY_END

def _get_range_records(range_start, range_end):
    """获取某个范围内的打卡记录"""
    with get_icpc_db_connection() as db:
        query = """
            SELECT name, time, checkType
            FROM checkup
            WHERE time >= %s AND time <= %s
            ORDER BY name ASC, time ASC
            """
        records = db.execute(query, (range_start, range_end)).fetchall()
        return records
    
def _calculate_attendance(records):
    """主计算函数"""
    total_duration = defaultdict(float)
    current_name = None
    current_group = []
    
    # 按姓名分组处理
    for record in records:
        if record['name'] != current_name:
            if current_name is not None:
                _process_user_records(current_name, current_group, total_duration)
            current_name = record['name']
            current_group = []
        current_group.append(record)
    
    # 处理最后一个用户
    if current_name is not None:
        _process_user_records(current_name, current_group, total_duration)
    
    return dict(total_duration)

def _process_user_records(name, records, total_duration):
    """处理单个用户记录"""
    attendance_days = defaultdict(list)
    
    # 按考勤日分组
    for r in records:
        day = _get_attendance_day(r['time'])
        if day is not None:
            attendance_days[day].append(r)
    
    # 处理每个考勤日
    for day, day_records in attendance_days.items():
        pairs = []
        i = 0
        
        # 生成On-Off配对
        while i < len(day_records):
            if day_records[i]['checkType'] == 'OnDuty':
                on_time = day_records[i]['time']
                last_off = None
                j = i + 1
                
                # 寻找最后一个OffDuty
                while j < len(day_records):
                    if day_records[j]['checkType'] == 'OnDuty':
                        break
                    elif day_records[j]['checkType'] == 'OffDuty':
                        last_off = day_records[j]['time']
                    j += 1
                
                if last_off:
                    pairs.append((on_time, last_off))
                    i = j  # 跳到下一个OnDuty位置
                else:
                    i += 1
            else:
                i += 1
        
        # 计算当日有效时长
        day_start = datetime.datetime.combine(day, datetime.time(8, 0))
        day_end = day_start + timedelta(hours=18)
        daily_total = 0.0
        
        for on, off in pairs:
            effective_start = max(on, day_start)
            effective_end = min(off, day_end)
            if effective_end > effective_start:
                duration = (effective_end - effective_start).total_seconds() / 3600
                daily_total += duration
        
        total_duration[name] += daily_total

def _get_attendance_day(t):
    """获取考勤日并过滤无效时间段"""
    if t.hour >= day_start_hours:
        return t.date()
    elif t.hour < day_end_hours:
        return (t - timedelta(days=1)).date()
    else:
        return None  # 2:00-8:00无效
    
def _format_duration(hours):
    """格式化时长输出：超过24小时转换为天+小时格式"""
    if hours < 24:
        return f"{hours:.1f} h"
    else:
        days = int(hours // 24)
        remaining_hours = hours % 24
        return f"{days} d {remaining_hours:.1f} h"

def get_working_time(date=datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0), range=1):
    """
    获取考勤时间
    date: datetime对象
    range: 整数类型
    """
    # 获取数据的范围
    range_start = date - timedelta(days = range - 1) + timedelta(hours=day_start_hours)
    range_end = date + timedelta(hours=24) + timedelta(hours=day_end_hours)

    # 获取对应范围的数据
    records = _get_range_records(range_start, range_end)
    if not records:
        return f"从 {date.date()} 日上溯 {range} 天内没有数据"
    # 根据数据计算结果
    result = _calculate_attendance(records)
    # 排序
    sorted_result = dict(sorted(result.items(), key=lambda item: item[1], reverse=True))
    
    # 将结果转化为字符串
    result_str = f"从 {date.date()} 日上溯 {range} 天内的考勤数据如下: \n"
    for name, value in sorted_result.items():
        # 使用新的格式化函数
        formatted_duration = _format_duration(value)
        result_str += f"{name}-考勤时长: {formatted_duration}\n"

    # 如果result_str不为空，去掉最后一个换行符
    if result_str:
        result_str = result_str.rstrip('\n')

    return result_str