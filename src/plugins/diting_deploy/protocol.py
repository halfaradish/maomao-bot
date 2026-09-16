"""
谛听部署 —— 协议契约层

容器内的插件与宿主机执行器（``scripts/diting-agent.sh``）通过 ``data/deploy/`` 目录
交换 JSON 文件完成一次部署作业。``data/`` 已经是 bind mount，因此容器内外看到的是同一份
文件，无需额外挂载或网络通道。

本模块只负责**契约**：目录布局、数据结构、原子读写、时间约定。不导入任何 NoneBot
运行时对象，便于单独验证与在宿主机侧对照实现。

目录所有权（谁写谁读必须严格区分，否则会互相覆盖）：

    queue/<job_id>.json       插件写   → 执行器读（用 mv 认领，认领后文件消失）
    running/<job_id>.json     执行器写 → 插件只读（残留说明执行器异常退出）
    status/<job_id>.json      执行器写 → 插件读（状态与结果，原子落盘）
    logs/<job_id>.log         执行器写 → 插件读尾部
    state.json                执行器写（心跳）→ 插件读
    boot.json                 插件写（每次启动）→ 执行器读（校验热重载是否真的生效）
    reported/<job_id>.json    插件写   → 插件读（回报去重标记，重启后不漏报不重报）
    pull.lock                 执行器写 → bot.py 的 watcher 读（热重载暂停哨兵）
    agent.lock                执行器 flock 自用
    build.fingerprint         执行器写 → 执行器读（构建指纹，决定是否需要重建镜像）

时间约定：机器判定一律用 epoch 秒整数字段（``*_ts``），ISO 字符串字段（``*_at``）
只用于展示。两者都写，避免跨进程解析时区字符串。
"""
from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Optional

from nonebot import logger

from ...config import DiTingData

PROTOCOL_VERSION = 1
PLUGIN_VERSION = "1.0.0"

# 会改动工作区/服务的动作（需要冷却、部分需要确认）
MUTATING_ACTIONS = ("pull", "build", "restart")
ACTIONS = MUTATING_ACTIONS

# 终态：到达后不再变化，插件可以回报并收尾
TERMINAL_STATES = ("succeeded", "failed", "rejected")

STATE_LABELS = {
    "queued": "排队中",
    "running": "执行中",
    "succeeded": "成功",
    "failed": "失败",
    "rejected": "被拒绝",
}
STATE_MARKS = {
    "queued": "⏳",
    "running": "🔄",
    "succeeded": "✅",
    "failed": "❌",
    "rejected": "⛔",
}
ACTION_LABELS = {
    "pull": "拉取代码",
    "build": "拉取并重建",
    "restart": "重启服务",
    "heartbeat": "心跳",
}
STEP_LABELS = {
    "preflight": "预检",
    "lock": "获取执行锁",
    "git-fetch": "拉取远端",
    "git-checkout": "切换代码",
    "reload": "等待热重载",
    "rebuild": "重建镜像",
    "restart": "重启容器",
    "health": "服务探活",
    "done": "完成",
}


# ── 时间 ────────────────────────────────────────────────────────
def now_ts() -> int:
    return int(time.time())


def now_iso() -> str:
    """宿主/容器本地时间（部署环境统一 TZ=Asia/Shanghai），仅用于展示"""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def format_ts(ts: Optional[int]) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return "—"


def human_duration(seconds: Optional[int]) -> str:
    if seconds is None or seconds < 0:
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} 秒"
    if seconds < 3600:
        return f"{seconds // 60} 分 {seconds % 60} 秒"
    return f"{seconds // 3600} 小时 {(seconds % 3600) // 60} 分"


# ── 目录布局 ────────────────────────────────────────────────────
def default_root() -> Path:
    """默认队列根目录：容器内 ``/app/data/deploy``，宿主机 ``<repo>/data/deploy``"""
    return Path(DiTingData.DATA_DIR) / "deploy"


@dataclass(frozen=True)
class DeployPaths:
    root: Path

    @property
    def queue(self) -> Path:
        return self.root / "queue"

    @property
    def running(self) -> Path:
        return self.root / "running"

    @property
    def status(self) -> Path:
        return self.root / "status"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def reported(self) -> Path:
        return self.root / "reported"

    @property
    def state_file(self) -> Path:
        return self.root / "state.json"

    @property
    def boot_file(self) -> Path:
        return self.root / "boot.json"

    @property
    def sentinel(self) -> Path:
        return self.root / "pull.lock"

    def status_file(self, job_id: str) -> Path:
        return self.status / f"{job_id}.json"

    def log_file(self, job_id: str) -> Path:
        return self.logs / f"{job_id}.log"

    def request_file(self, job_id: str) -> Path:
        return self.queue / f"{job_id}.json"

    def reported_file(self, job_id: str) -> Path:
        return self.reported / f"{job_id}.json"

    def ensure(self) -> None:
        for directory in (self.queue, self.running, self.status, self.logs, self.reported):
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:  # 目录不可建时不应打断插件加载
                logger.warning(f"[diting_deploy] 创建目录失败 {directory}: {exc}")


# ── 原子读写 ────────────────────────────────────────────────────
def write_json_atomic(path: Path, payload: dict) -> None:
    """先写 ``<name>.json.tmp`` 再 os.replace，读取方按 ``*.json`` 通配不会读到半成品

    显式用 ``newline="\\n"``：宿主机执行器按行解析这些文件，Windows 上的 CRLF 会让
    行尾多出一个 ``\\r`` 破坏取值（本地开发即会遇到）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2))
    os.replace(tmp, path)


def read_json(path: Path) -> Optional[dict]:
    """宽松读取：不存在、正被写入、内容非法一律返回 None，由调用方下次重试"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def tail_lines(path: Path, limit: int) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if limit > 0:
        lines = lines[-limit:]
    return "\n".join(lines)


# ── 作业标识 ────────────────────────────────────────────────────
def new_job_id(action: str) -> str:
    """形如 ``20260915-143012-build-8f3a2c``：可排序、可在 QQ 里肉眼引用"""
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{action}-{secrets.token_hex(3)}"


# ── 请求（插件 → 执行器） ───────────────────────────────────────
@dataclass
class JobRequest:
    job_id: str
    action: str
    branch: str
    requested_by: int
    session: dict
    env: str
    bot_self_id: str = ""
    requested_at: str = field(default_factory=now_iso)
    requested_ts: int = field(default_factory=now_ts)
    protocol: int = PROTOCOL_VERSION

    @classmethod
    def create(
        cls,
        *,
        action: str,
        branch: str,
        user_id: int,
        session: dict,
        env: str,
        bot_self_id: str = "",
    ) -> "JobRequest":
        return cls(
            job_id=new_job_id(action),
            action=action,
            branch=branch,
            requested_by=user_id,
            session=session,
            env=env,
            bot_self_id=bot_self_id,
        )

    def to_dict(self) -> dict:
        return {
            "protocol": self.protocol,
            "job_id": self.job_id,
            "action": self.action,
            "branch": self.branch,
            "requested_by": self.requested_by,
            "requested_at": self.requested_at,
            "requested_ts": self.requested_ts,
            "bot_self_id": self.bot_self_id,
            "env": self.env,
            "session": {
                "type": self.session.get("type", "private"),
                "group_id": self.session.get("group_id"),
                "user_id": self.session.get("user_id", self.requested_by),
            },
        }


# ── 状态（执行器 → 插件） ───────────────────────────────────────
@dataclass
class JobStatus:
    job_id: str
    action: str = ""
    state: str = "queued"
    step: str = ""
    message: str = ""
    exit_code: Optional[int] = None
    branch: str = ""
    requested_by: int = 0
    session: dict = field(default_factory=dict)
    started_at: str = ""
    started_ts: int = 0
    updated_at: str = ""
    updated_ts: int = 0
    finished_at: str = ""
    finished_ts: int = 0
    result: dict = field(default_factory=dict)
    log_file: str = ""
    protocol: int = PROTOCOL_VERSION

    @classmethod
    def from_dict(cls, data: dict) -> "JobStatus":
        known = {f.name for f in fields(cls)}
        payload = {k: v for k, v in data.items() if k in known}
        payload.setdefault("job_id", "")
        if not isinstance(payload.get("session"), dict):
            payload["session"] = {}
        if not isinstance(payload.get("result"), dict):
            payload["result"] = {}
        return cls(**payload)

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def action_label(self) -> str:
        return ACTION_LABELS.get(self.action, self.action or "任务")

    @property
    def state_label(self) -> str:
        return STATE_LABELS.get(self.state, self.state or "未知")

    @property
    def state_mark(self) -> str:
        return STATE_MARKS.get(self.state, "•")

    @property
    def step_label(self) -> str:
        return STEP_LABELS.get(self.step, self.step or "")

    @property
    def duration_sec(self) -> Optional[int]:
        if not self.started_ts:
            return None
        end = self.finished_ts or now_ts()
        return max(0, end - self.started_ts)

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


# ── 队列读写 ────────────────────────────────────────────────────
def write_job_request(paths: DeployPaths, request: JobRequest) -> Path:
    path = paths.request_file(request.job_id)
    write_json_atomic(path, request.to_dict())
    return path


def read_status(paths: DeployPaths, job_id: str) -> Optional[JobStatus]:
    data = read_json(paths.status_file(job_id))
    return JobStatus.from_dict(data) if data else None


def iter_statuses(paths: DeployPaths, limit: int = 20) -> list[JobStatus]:
    """按修改时间倒序返回最近的状态记录（跳过半写文件）"""
    try:
        candidates = sorted(
            paths.status.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return []

    result: list[JobStatus] = []
    for path in candidates[:limit]:
        data = read_json(path)
        if data is None:
            continue
        result.append(JobStatus.from_dict(data))
    return result


def latest_status(paths: DeployPaths) -> Optional[JobStatus]:
    statuses = iter_statuses(paths, limit=1)
    return statuses[0] if statuses else None


def pending_job_ids(paths: DeployPaths) -> list[str]:
    """待在队列里未认领 + 已被认领正在执行的作业 id"""
    ids: list[str] = []
    for directory in (paths.running, paths.queue):
        try:
            ids.extend(sorted(p.stem for p in directory.glob("*.json")))
        except OSError:
            continue
    return ids


def has_inflight_job(paths: DeployPaths) -> bool:
    return bool(pending_job_ids(paths))


def is_reported(paths: DeployPaths, job_id: str) -> bool:
    return paths.reported_file(job_id).is_file()


def mark_reported(paths: DeployPaths, job_id: str) -> None:
    try:
        write_json_atomic(
            paths.reported_file(job_id),
            {"job_id": job_id, "reported_at": now_iso(), "reported_ts": now_ts()},
        )
    except OSError as exc:
        logger.warning(f"[diting_deploy] 写入回报标记失败 {job_id}: {exc}")


# ── 心跳 / 启动记录 / 哨兵 ──────────────────────────────────────
def read_state(paths: DeployPaths) -> Optional[dict]:
    return read_json(paths.state_file)


def read_boot(paths: DeployPaths) -> Optional[dict]:
    return read_json(paths.boot_file)


def write_boot_record(paths: DeployPaths, env: str) -> None:
    """每次启动写一次。执行器在 pull 之后靠它的 mtime 判断热重载是否真的把 worker 拉起来了"""
    try:
        write_json_atomic(
            paths.boot_file,
            {
                "protocol": PROTOCOL_VERSION,
                "plugin_version": PLUGIN_VERSION,
                "booted_at": now_iso(),
                "booted_ts": now_ts(),
                "pid": os.getpid(),
                "env": env,
            },
        )
    except OSError as exc:
        logger.warning(f"[diting_deploy] 写入 boot.json 失败: {exc}")


def sentinel_info(paths: DeployPaths) -> dict:
    """哨兵是否在位、存在多久（超龄由消费方判定为残留）"""
    try:
        stat = paths.sentinel.stat()
    except OSError:
        return {"present": False, "age_sec": None}
    return {"present": True, "age_sec": max(0, now_ts() - int(stat.st_mtime))}


def queue_writable(paths: DeployPaths) -> tuple[bool, str]:
    """派发前探测队列目录可写性，把「黑洞任务」变成明确报错"""
    probe = paths.queue / ".write_probe"
    try:
        paths.queue.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True, ""
    except OSError as exc:
        return False, str(exc)
