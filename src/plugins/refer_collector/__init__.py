from __future__ import annotations

import hashlib
import json
import random
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment
from nonebot.exception import FinishedException
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from src.common.model.model import PluginBadgeColor, PluginGroupEnum

__plugin_meta__ = PluginMetadata(
    name="内推码收集器",
    description="保存图片并支持随机/最新提取，适合群内收集内推码截图。",
    usage=(
        "保存图片 <图片> —— 保存消息中的图片\n"
        "保存内推 <图片> —— 保存消息中的图片\n"
        "提取图片 —— 随机返回一张已保存图片\n"
        "内推码 —— 随机返回一张已保存图片\n"
        "最新内推 —— 返回最近保存的一张图片\n"
        "图片列表 —— 查看最近保存记录\n"
        "清空图片 —— 删除本地保存内容"
    ),
    type="application",
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.UTILITY.value,
        "badge_color": PluginBadgeColor.GREEN.value,
    },
)

SAVE_COMMANDS = {"保存图片", "保存内推", "存图", "收图"}
GET_RANDOM_COMMANDS = {"提取图片", "内推码", "取图", "随机图片"}
GET_LATEST_COMMANDS = {"最新图片", "最新内推", "最近图片", "最新一张"}
LIST_COMMANDS = {"图片列表", "内推列表", "查看图片"}
CLEAR_COMMANDS = {"清空图片", "删除图片库", "清空内推"}

DATA_DIR = Path(__file__).resolve().parent / "data"
IMAGE_DIR = DATA_DIR / "images"
DATA_FILE = DATA_DIR / "records.json"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

save_matcher = on_command("保存图片", aliases=SAVE_COMMANDS, priority=10, block=True)
get_random_matcher = on_command("提取图片", aliases=GET_RANDOM_COMMANDS, priority=10, block=True)
get_latest_matcher = on_command("最新内推", aliases=GET_LATEST_COMMANDS, priority=10, block=True)
list_matcher = on_command("图片列表", aliases=LIST_COMMANDS, priority=10, block=True)
clear_matcher = on_command("清空图片", aliases=CLEAR_COMMANDS, priority=10, block=True)


@save_matcher.handle()
async def handle_save(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    images = [seg for seg in event.get_message() + args if seg.type == "image"]
    if not images:
        await save_matcher.finish("请在命令后附带图片，例如：保存图片 + 图片", at_sender=True)

    records = load_data()
    existing_hashes = {
        record.get("content_hash")
        for record in records
        if record.get("content_hash")
    }
    saved_count = 0
    skipped_count = 0
    errors: list[str] = []

    for idx, seg in enumerate(images, start=1):
        try:
            source_path = await _resolve_image_path(bot, seg)
            content_hash = _file_md5(source_path)
            if content_hash in existing_hashes:
                skipped_count += 1
                continue

            saved_path = await _save_image(source_path, event, idx)
            records.append(
                {
                    "saved_file": str(saved_path),
                    "sender_id": event.get_user_id(),
                    "group_id": getattr(event, "group_id", None),
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "source_file_id": seg.data.get("file", ""),
                    "content_hash": content_hash,
                }
            )
            existing_hashes.add(content_hash)
            saved_count += 1
        except Exception as exc:
            errors.append(f"第 {idx} 张：{exc}")

    save_data(records)

    if saved_count == 0 and skipped_count == 0:
        await save_matcher.finish("没有成功保存任何图片。\n" + "\n".join(errors), at_sender=True)

    msg = f"已保存 {saved_count} 张图片。"
    if skipped_count:
        msg += f"\n已跳过 {skipped_count} 张重复图片。"
    if errors:
        msg += "\n部分失败：\n" + "\n".join(errors)
    await save_matcher.finish(msg, at_sender=True)


@get_random_matcher.handle()
async def handle_get_random():
    await _send_record(mode="random")


@get_latest_matcher.handle()
async def handle_get_latest():
    await _send_record(mode="latest")


@list_matcher.handle()
async def handle_list():
    records = _valid_records()
    if not records:
        await list_matcher.finish("当前还没有保存任何图片。", at_sender=True)

    lines = [f"共保存 {len(records)} 张图片："]
    for i, record in enumerate(records[-10:], start=max(1, len(records) - 9)):
        lines.append(
            f"{i}. {record.get('time', '未知时间')[:19].replace('T', ' ')} | "
            f"提供者 {record.get('sender_id', '未知')} | {Path(record['saved_file']).name}"
        )
    await list_matcher.finish("\n".join(lines), at_sender=True)


@clear_matcher.handle()
async def handle_clear():
    records = load_data()
    deleted = 0
    for record in records:
        file_path = Path(record.get("saved_file", ""))
        if file_path.exists():
            try:
                file_path.unlink()
                deleted += 1
            except Exception:
                pass
    save_data([])
    await clear_matcher.finish(f"已清空图片库，共删除 {deleted} 个图片文件。", at_sender=True)


async def _send_record(mode: str) -> None:
    records = _valid_records()
    if not records:
        await save_matcher.finish("当前还没有保存任何图片。", at_sender=True)

    record = records[-1] if mode == "latest" else random.choice(records)
    img_path = Path(record["saved_file"])
    caption = (
        f"模式：{'最新' if mode == 'latest' else '随机'}\n"
        f"提供者：{record.get('sender_id', '未知')}\n"
        f"收录时间：{record.get('time', '未知')[:19].replace('T', ' ')}\n"
        f"总计：{len(records)} 张"
    )
    try:
        await save_matcher.send(Message(caption) + MessageSegment.image(img_path.as_uri()))
        await save_matcher.finish("图片已发送。", at_sender=True)
    except FinishedException:
        raise
    except Exception as exc:
        await save_matcher.finish(f"提取失败：{exc}", at_sender=True)


async def _save_image(source_path: Path, event: MessageEvent, index: int) -> Path:
    if not source_path.exists():
        raise FileNotFoundError(f"图片文件不存在: {source_path}")

    ext = source_path.suffix if source_path.suffix else ".jpg"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{timestamp}_{event.get_user_id()}_{index}{ext}"
    dest_path = IMAGE_DIR / filename
    dest_path.write_bytes(source_path.read_bytes())
    return dest_path


async def _resolve_image_path(bot: Bot, seg: MessageSegment) -> Path:
    file_id = seg.data.get("file", "")
    url = seg.data.get("url", "")

    candidates = []
    if file_id:
        candidates.append(file_id)
    if url:
        candidates.append(url)

    for candidate in candidates:
        if candidate.startswith("file://"):
            path = Path(candidate[7:])
            if path.exists():
                return path
        path = Path(candidate)
        if path.exists():
            return path
        if candidate.startswith("http://") or candidate.startswith("https://"):
            with urlopen(candidate) as resp:
                suffix = Path(candidate.split("?", 1)[0]).suffix or ".jpg"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(resp.read())
                    return Path(tmp.name)

    try:
        result: Any = await bot.call_api("get_image", file=file_id)
        data = result.get("data", result)
        file_path = data.get("file")
        if file_path:
            if file_path.startswith("file://"):
                file_path = file_path[7:]
            path = Path(file_path)
            if path.exists():
                return path
    except Exception:
        pass

    raise ValueError("无法解析图片本地路径，请确认 OneBot 端支持 get_image 或图片消息包含本地 file/url")


def _file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_records() -> list[dict[str, Any]]:
    return [r for r in load_data() if Path(r.get("saved_file", "")).exists()]


def load_data() -> list[dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_data(data: list[dict[str, Any]]) -> None:
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
