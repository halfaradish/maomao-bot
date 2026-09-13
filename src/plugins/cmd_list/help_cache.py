"""帮助图磁盘缓存

缓存有效性 = meta.json 中记录的哈希匹配 且 PNG 文件存在。
meta.json 在 PNG 落盘之后最后写入，作为提交标记：缺失或不匹配一律视为未命中重建。
meta 与 PNG 同目录存放（单一事实来源），路径按 env_tag 隔离多环境。
"""

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Optional

from nonebot import logger

from src.common.database import current_env_tag
from src.common.plugin_meta import PluginUsageInfo
from src.config.local_config import DiTingData

TEMPLATE_DIR = Path(__file__).parent / "template"
HELP_TEMPLATE_FILENAME = "help_template.html"
DETAIL_TEMPLATE_FILENAME = "detail_template.html"

OVERVIEW_PNG = "overview.png"
DETAIL_SUBDIR = "detail"


def cache_root() -> Path:
    return Path(DiTingData.DATA_DIR) / "help_cache" / current_env_tag()


def _meta_path() -> Path:
    return cache_root() / "meta.json"


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _template_md5(filename: str) -> str:
    return _md5((TEMPLATE_DIR / filename).read_text(encoding="utf-8"))


def _plugin_brief(plugin: PluginUsageInfo) -> dict:
    return {
        "module_name": plugin.module_name,
        "name": plugin.name,
        "description": plugin.description,
        "usage": plugin.usage,
        "group": plugin.group,
        "badge_color": plugin.badge_color,
    }


def overview_hash(plugins_data: list[PluginUsageInfo]) -> str:
    payload = {
        "template": _template_md5(HELP_TEMPLATE_FILENAME),
        "plugins": [_plugin_brief(p) for p in plugins_data],
    }
    return _md5(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def detail_hash(plugin: PluginUsageInfo) -> str:
    payload = {
        "template": _template_md5(DETAIL_TEMPLATE_FILENAME),
        "plugin": _plugin_brief(plugin),
        # 详情图上展示插件ID（按排序的序号），随插件列表变化
        "id": plugin.id,
    }
    return _md5(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _load_meta() -> dict:
    try:
        return json.loads(_meta_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_meta(meta: dict) -> None:
    path = _meta_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _atomic_write_png(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".png.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _read_png(rel_path: str) -> Optional[bytes]:
    try:
        return (cache_root() / rel_path).read_bytes()
    except OSError:
        return None


def get_overview_cache(expected_hash: str) -> Optional[bytes]:
    entry = _load_meta().get("overview")
    if not entry or entry.get("hash") != expected_hash:
        return None
    return _read_png(entry.get("png", OVERVIEW_PNG))


def get_overview_stale() -> Optional[bytes]:
    """无视哈希读取旧总览图，仅用于渲染失败时降级"""
    entry = _load_meta().get("overview")
    if not entry:
        return None
    return _read_png(entry.get("png", OVERVIEW_PNG))


def save_overview_cache(expected_hash: str, png: bytes) -> None:
    _atomic_write_png(cache_root() / OVERVIEW_PNG, png)
    meta = _load_meta()
    meta["overview"] = {"hash": expected_hash, "png": OVERVIEW_PNG}
    _save_meta(meta)


def _detail_png_rel(module_name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in module_name)
    return f"{DETAIL_SUBDIR}/{safe}.png"


def get_detail_cache(module_name: str, expected_hash: str) -> Optional[bytes]:
    entry = _load_meta().get("details", {}).get(module_name)
    if not entry or entry.get("hash") != expected_hash:
        return None
    return _read_png(entry.get("png") or _detail_png_rel(module_name))


def get_detail_stale(module_name: str) -> Optional[bytes]:
    """无视哈希读取旧详情图，仅用于渲染失败时降级"""
    entry = _load_meta().get("details", {}).get(module_name)
    if not entry:
        return None
    return _read_png(entry.get("png") or _detail_png_rel(module_name))


def save_detail_cache(module_name: str, expected_hash: str, png: bytes) -> None:
    rel = _detail_png_rel(module_name)
    _atomic_write_png(cache_root() / rel, png)
    meta = _load_meta()
    meta.setdefault("details", {})[module_name] = {"hash": expected_hash, "png": rel}
    _save_meta(meta)


def prune_details(valid_module_names: set) -> None:
    """插件列表变化后，清理已卸载插件的详情缓存"""
    meta = _load_meta()
    details = meta.get("details")
    if not details:
        return
    removed = [name for name in details if name not in valid_module_names]
    if not removed:
        return
    for name in removed:
        rel = details.pop(name).get("png")
        if rel:
            (cache_root() / rel).unlink(missing_ok=True)
    _save_meta(meta)
    logger.info(f"[cmd_list] 已清理 {len(removed)} 个失效插件的详情缓存")


def clear_cache() -> None:
    shutil.rmtree(cache_root(), ignore_errors=True)
