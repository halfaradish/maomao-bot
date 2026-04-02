from typing import List
from pydantic import BaseModel

class GroupConfig(BaseModel):
    group_id: int
    group_name: str = ""

# 改成你要监控的QQ群号
MONITORED_GROUPS = [
    GroupConfig(group_id=1081564994, group_name="文件分享群1"),
    # 添加更多群...
]