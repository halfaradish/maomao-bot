# src/plugins/icpc_ac_monitor/state.py
"""全局配置与可变状态（单点初始化）

data/icpc_ac_monitor.json 同时存目标群、学校、监控比赛、艾特白名单。
conf / TARGET_GROUPS / SCHOOLS / AT_WHITELIST / memory 全部在本模块初始化，
其余模块只 import 引用（同一对象），不得复制。import 本模块即触发
data 目录创建与 JSON 读取，因此仅在插件启用分支加载。
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from nonebot import logger

# ==============================================================================
# 一、路径相关
# ==============================================================================
# 计算项目根目录：插件文件向上 4 级就是项目根
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
# 单文件配置路径：data/icpc_ac_monitor.json
CONF_FILE = BASE_DIR / "data" / "icpc_ac_monitor.json"
# 城市拼音映射文件，用于将赛站拼音转换为中文
CITY_MAP_FILE = BASE_DIR / "data" / "city_pinyin_map.json"
# 学校名称映射文件，用于支持中英文名称匹配
SCHOOL_MAP_FILE = BASE_DIR / "data" / "school_name_map.json"
# 若 data 目录不存在则自动创建
CONF_FILE.parent.mkdir(exist_ok=True)

# ==============================================================================
# 二、配置读写函数（原子写入，防写残）
# ==============================================================================
def load_conf() -> Dict[str, Any]:
    """
    加载整个 json 配置；
    若文件不存在则生成模板（目标群为空，学校默认广西大学）。
    """
    if not CONF_FILE.exists():
        tpl = {"target_groups": [], "schools": ["广西大学"], "monitors": {}, "at_whitelist": []}
        save_conf(tpl)
        return tpl
    try:
        with CONF_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("target_groups", [])
            data.setdefault("schools", [])
            data.setdefault("monitors", {})
            data.setdefault("at_whitelist", [])
            return data
    except Exception as e:
        logger.warning(f"读取配置失败：{e}，返回空模板")
        return {"target_groups": [], "schools": [], "monitors": {}, "at_whitelist": []}

def save_conf(data: Dict[str, Any]):
    """
    原子写入：先写临时文件，再 replace，避免写一半崩溃导致 JSON 损坏。
    """
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False, dir=CONF_FILE.parent, prefix="tmp_"
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())          # 强制落盘
        os.replace(tmp.name, CONF_FILE)     # 瞬间替换，几乎不可能出现半文件
    except Exception as e:
        logger.error(f"保存配置失败：{e}")
        try:
            os.unlink(tmp.name)             # 清理临时文件
        except:
            pass

# ==============================================================================
# 三、启动时一次性加载配置
# ==============================================================================
conf = load_conf()
# 目标群号列表（推送白名单）——你手动改 json 即可
TARGET_GROUPS: List[int] = conf["target_groups"]
# 监控学校列表——你手动改 json 即可
SCHOOLS: List[str] = conf["schools"]


# 可被艾特提醒的 QQ 白名单（qq -> 所属群id，None表示全局）
def _normalize_whitelist(raw: Any) -> Dict[int, Optional[int]]:
    result: Dict[int, Optional[int]] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                qq = int(k)
            except Exception:
                continue
            group_id = None
            if isinstance(v, dict):
                group_id = v.get("group_id")
            elif isinstance(v, int):
                group_id = v
            elif v is None:
                group_id = None
            elif isinstance(v, str) and v.isdigit():
                group_id = int(v)
            result[qq] = int(group_id) if isinstance(group_id, int) else None
        return result
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                qq = item.get("qq")
                group_id = item.get("group_id")
            else:
                qq = item
                group_id = None
            try:
                qq_int = int(qq)
            except Exception:
                continue
            try:
                gid_int = int(group_id)
            except Exception:
                gid_int = None
            result[qq_int] = gid_int
    elif raw and isinstance(raw, (int, str)):
        try:
            result[int(raw)] = None
        except Exception:
            pass
    return result


AT_WHITELIST: Dict[int, Optional[int]] = _normalize_whitelist(conf.get("at_whitelist", []))
# 正在全局监控的比赛字典（url 为 key）；与 conf["monitors"] 是同一对象
memory: Dict[str, Any] = conf["monitors"]
