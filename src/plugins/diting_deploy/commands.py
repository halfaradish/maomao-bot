"""
谛听部署 —— QQ 侧命令、鉴权、受理与回报

设计要点（与方案的边界一致）：

* **不接受任何来自 QQ 的自由参数** —— 分支只来自 ``DITING_DEPLOY_BRANCH``，
  没有路径、ref、选项，注入面为零。用户能给的只有子命令名和一个 job_id（只读查询用）。
* **确认用一次性令牌而不是 ``matcher.got()``** —— ``got()`` 在群里会吞掉下一条消息、
  无法超时、还会与其他 matcher 抢事件；令牌方案无状态冲突，重启后自然作废。
* **回报分两条腿** —— ``build``/``restart`` 会重建容器从而杀掉发起命令的进程，
  所以终态回报必须由「新实例的启动钩子」补上；``pull`` 这类不重启的由轮询任务回报。
  去重靠 ``reported/<job_id>.json`` 标记，重启后既不漏报也不重报。
"""
from __future__ import annotations

import asyncio
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from nonebot import get_bots, get_driver, get_plugin_config, logger, on_command
from nonebot.adapters import Message
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageEvent,
    Message as OneBotMessage,
)
from nonebot.params import CommandArg
from sqlalchemy import select

from src.common.database import async_session_factory
from src.common.permission import check_permission
from src.common.permission.models import PermissionGroup, PermissionGroupPerm
from src.common.send_forward_msg import SendForwardMsg

from . import protocol as pt
from .config import Config

plugin_config = get_plugin_config(Config)

ENVIRONMENT = os.getenv("ENVIRONMENT") or "dev"
HOT_RELOAD = os.getenv("HOT_RELOAD", "").lower() == "true"

_queue_root = plugin_config.diting_deploy_queue_dir.strip()
PATHS = pt.DeployPaths(Path(_queue_root) if _queue_root else pt.default_root())

# QQ 消息长度留出余量（NapCat 单条消息上限约 4500 字节）
_MESSAGE_LIMIT = 1900


# ── 子命令表 ────────────────────────────────────────────────────
@dataclass(frozen=True)
class SubCommand:
    name: str
    perm: str
    label: str
    needs_confirm: bool = False
    mutates: bool = False  # 会改动工作区或服务：需要冷却 + 分支预检


SUBCOMMANDS: dict[str, SubCommand] = {
    "pull": SubCommand("pull", "diting_deploy:pull", "拉取代码", mutates=True),
    "build": SubCommand(
        "build", "diting_deploy:build", "拉取并重建", needs_confirm=True, mutates=True
    ),
    "restart": SubCommand(
        "restart", "diting_deploy:restart", "重启服务", needs_confirm=True, mutates=True
    ),
    "status": SubCommand("status", "diting_deploy:view", "查看部署状态"),
    "log": SubCommand("log", "diting_deploy:view", "查看执行日志"),
}

ALIASES = {
    "state": "status",
    "logs": "log",
    "deploy": "pull",
    "rebuild": "build",
    "帮助": "help",
}


# ── 会话内的临时状态（内存，进程重启后自然作废） ────────────────
@dataclass
class _PendingConfirm:
    token: str
    action: str
    user_id: int
    session: dict
    expires_ts: float


_pending_confirms: dict[str, _PendingConfirm] = {}
_last_invoke: dict[int, float] = {}
_reported_memory: set[str] = set()


# ── 工具函数 ────────────────────────────────────────────────────
def _truncate(text: str, limit: int = _MESSAGE_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n…（内容过长已截断）"


def _truncate_tail(text: str, limit: int = _MESSAGE_LIMIT) -> str:
    """保尾部截断。日志的关键信息（报错、退出码）都在最后几行，丢头比丢尾好"""
    if len(text) <= limit:
        return text
    return "…（更早的内容已截断）\n" + text[-(limit - 20):]


def _cmd_text(*parts: str) -> str:
    """按当前 COMMAND_START 拼出可直接照抄的命令文本（dev 环境是 dev- 前缀）"""
    starts = list(get_driver().config.command_start or [""])
    if "/" in starts:
        prefix = "/"
    else:
        prefix = sorted(starts)[0] if starts else ""
    body = " ".join(str(p) for p in parts if p)
    return f"{prefix}{plugin_config.diting_deploy_cmd} {body}".strip()


def _session_of(event: MessageEvent) -> dict:
    if isinstance(event, GroupMessageEvent):
        return {"type": "group", "group_id": event.group_id, "user_id": event.user_id}
    return {"type": "private", "group_id": None, "user_id": event.user_id}


def _session_key(session: dict) -> str:
    return f"{session.get('type')}:{session.get('group_id') or 0}:{session.get('user_id')}"


async def _allowed(event: MessageEvent, perm_key: str) -> bool:
    """权限校验失败按拒绝处理（fail-closed）—— 部署命令不能因为 DB 抖动而放行"""
    try:
        return await check_permission(event, perm_key)
    except Exception as exc:
        logger.opt(exception=True).error(f"[diting_deploy] 权限校验异常，按拒绝处理: {exc}")
        return False


def _cooldown_remaining(user_id: int) -> int:
    cooldown = max(0, int(plugin_config.diting_deploy_user_cooldown))
    if cooldown <= 0:
        return 0
    elapsed = time.monotonic() - _last_invoke.get(user_id, 0.0)
    return max(0, int(cooldown - elapsed))


def _mirror_session(session: dict) -> Optional[dict]:
    """配置了 notify_group 时返回镜像目标（与主会话同群时不重复发）"""
    notify_group = int(plugin_config.diting_deploy_notify_group or 0)
    if not notify_group:
        return None
    if session.get("type") == "group" and int(session.get("group_id") or 0) == notify_group:
        return None
    return {
        "type": "group",
        "group_id": notify_group,
        "user_id": session.get("user_id", 0),
        "bot_self_id": session.get("bot_self_id", ""),
    }


def _get_bot(self_id: Optional[str] = None) -> Optional[Bot]:
    bots = get_bots()
    if not bots:
        return None
    if self_id and self_id in bots:
        return bots[self_id]
    return next(iter(bots.values()))


async def _wait_for_bot(timeout: float, self_id: Optional[str] = None) -> Optional[Bot]:
    """容器刚重建完成时 NapCat 连接可能还没建立，先等一个可用连接再回报"""
    deadline = time.monotonic() + timeout
    while True:
        bot = _get_bot(self_id)
        if bot is not None:
            return bot
        if time.monotonic() >= deadline:
            return None
        await asyncio.sleep(3)


async def _send_once(session: dict, text: str) -> bool:
    bot = _get_bot(session.get("bot_self_id"))
    if bot is None:
        return False
    try:
        if session.get("type") == "group" and session.get("group_id"):
            await bot.send_group_msg(group_id=int(session["group_id"]), message=text)
        else:
            await bot.send_private_msg(user_id=int(session["user_id"]), message=text)
        return True
    except Exception as exc:
        logger.warning(f"[diting_deploy] 发送消息失败: {exc}")
        return False


async def _report(
    session: dict, text: str, *, retries: int = 6, interval: float = 5.0
) -> bool:
    """回报到发起会话；镜像群只发一次，不做重试，避免重复刷屏"""
    delivered = False
    for attempt in range(1, retries + 1):
        if await _send_once(session, text):
            delivered = True
            break
        if attempt < retries:
            await asyncio.sleep(interval)

    mirror = _mirror_session(session)
    if mirror is not None:
        await _send_once(mirror, text)
    return delivered


async def _finish_report(session: dict, job_id: str, text: str) -> None:
    """终态回报：先落去重标记再发，保证「重启后不重报」；发失败则撤标记留给下次启动"""
    if not session:
        logger.warning(f"[diting_deploy] 作业 {job_id} 缺少回报目标，跳过回报")
        return
    if job_id in _reported_memory:
        return
    _reported_memory.add(job_id)
    pt.mark_reported(PATHS, job_id)

    if await _report(session, text):
        return

    _reported_memory.discard(job_id)
    try:
        PATHS.reported_file(job_id).unlink()
    except OSError:
        pass
    logger.error(f"[diting_deploy] 作业 {job_id} 的结果回报失败，将在下次启动时重试")


# ── 文本渲染 ────────────────────────────────────────────────────
def _render_help() -> str:
    lines = [
        "🛰️ 谛听部署",
        "拉取代码 / 重建服务，真正的 git 与 docker 操作在宿主机 agent 上执行",
        "",
        f"{_cmd_text('pull')} —— 拉取远端分支，靠热重载生效",
        f"{_cmd_text('build')} —— 拉取 → 按需重建镜像 → 重启 → 探活",
        f"{_cmd_text('restart')} —— 不拉代码，直接重启并探活",
        f"{_cmd_text('status')} —— 查看 agent 心跳、代码版本、容器与任务状态",
        f"{_cmd_text('log')} [job_id] —— 查看执行日志尾部",
        f"{_cmd_text('cancel')} —— 取消待确认的操作",
        "",
        "build / restart 会中断服务，需要二次确认",
    ]
    if not plugin_config.diting_deploy_branch.strip():
        lines.append("⚠️ 未配置 DITING_DEPLOY_BRANCH，pull / build 会被拒绝")
    return "\n".join(lines)


def _render_terminal(status: pt.JobStatus) -> str:
    lines = [f"{status.state_mark} {status.action_label}{status.state_label}｜{status.job_id}"]
    if status.message:
        lines.append(status.message)

    result = status.result or {}
    old_sha, new_sha = result.get("old_sha"), result.get("new_sha")
    if old_sha or new_sha:
        if old_sha and old_sha == new_sha:
            lines.append(f"代码：{status.branch or '—'} @ {new_sha}（无变化）")
        else:
            lines.append(f"代码：{old_sha or '—'} → {new_sha or '—'}（分支 {status.branch or '—'}）")

    flags = []
    if result.get("rebuilt"):
        flags.append("已重建镜像")
    if result.get("rebuild_skipped"):
        flags.append("跳过重建（构建指纹未变）")
    if result.get("restarted"):
        flags.append("已重启容器")
    if result.get("reloaded"):
        flags.append("热重载已生效")
    if flags:
        lines.append("；".join(flags))

    lines.append(
        f"耗时：{pt.human_duration(status.duration_sec)}｜结束：{pt.format_ts(status.finished_ts)}"
    )
    if status.exit_code not in (None, 0):
        lines.append(f"退出码：{status.exit_code}")
    if status.state != "succeeded" and result.get("rollback_hint"):
        lines.append(f"人工回滚：{result['rollback_hint']}")
    lines.append(f"日志：{_cmd_text('log', status.job_id)}")
    if status.state == "failed":
        lines.append("服务若未恢复，请到服务器查看：journalctl -u diting-agent -n 100")
    return _truncate("\n".join(lines))


def _render_status() -> str:
    lines = ["🛰️ 谛听部署状态"]
    branch = plugin_config.diting_deploy_branch.strip() or "未配置"
    lines.append(f"环境：{ENVIRONMENT}｜分支：{branch}｜热重载：{'开' if HOT_RELOAD else '关'}")

    boot = pt.read_boot(PATHS)
    if boot:
        uptime = pt.now_ts() - int(boot.get("booted_ts") or 0)
        lines.append(
            f"本次运行：已启动 {pt.human_duration(uptime)}（pid {boot.get('pid', '?')}，"
            f"v{boot.get('plugin_version', '?')}）"
        )
    else:
        lines.append("本次运行：尚无启动记录")

    fresh_limit = int(plugin_config.diting_deploy_require_agent_fresh or 0)
    state = pt.read_state(PATHS)
    if state is None:
        lines.append("宿主 agent：❌ 未探测到（state.json 不存在）")
        lines.append("→ 请在服务器安装并启动 diting-agent，队列目录：")
        lines.append(f"  {PATHS.root}")
    else:
        age = pt.now_ts() - int(state.get("updated_ts") or 0)
        stale = fresh_limit > 0 and age > fresh_limit
        lines.append(
            f"宿主 agent：{'⚠️ 心跳过期' if stale else '✅ 正常'}｜{pt.human_duration(age)}前"
            f"｜v{state.get('agent_version', '?')}"
        )
        behind = state.get("behind")
        drift = "" if behind in (None, 0) else f"，落后 {behind} 个提交"
        lines.append(
            f"代码：{state.get('branch') or branch} @ {state.get('local_sha') or '—'}"
            f"（远端 {state.get('remote_sha') or '—'}{drift}）"
        )
        if state.get("git_ok") is False:
            lines.append("⚠️ 执行器读不到 git（分支/SHA 为空）：检查仓库属主与宿主机 PATH")
        lines.append(f"工作区：{'有未提交改动' if state.get('dirty') else '干净'}")
        container = state.get("container") or {}
        lines.append(f"容器：{container.get('name') or '—'} {container.get('state') or '未知'}")
        sentinel = state.get("sentinel") or {}
        if sentinel.get("present"):
            lines.append(
                f"部署锁：在位 {pt.human_duration(sentinel.get('age_sec'))}"
                "（部署进行中；超过 10 分钟视为残留）"
            )
        if not state.get("dirs_writable", True):
            lines.append("⚠️ 执行器报告部署目录不可写，请检查属主（agent 需以 root 运行）")
        for warn in (state.get("warnings") or [])[:3]:
            lines.append(f"⚠️ {warn}")

    pending = pt.pending_job_ids(PATHS)
    lines.append(f"待执行：{'、'.join(pending) if pending else '无'}")

    last = pt.latest_status(PATHS)
    if last is None:
        lines.append("上次任务：无记录")
    else:
        when = pt.format_ts(last.finished_ts) if last.finished_ts else "进行中"
        lines.append(f"上次任务：{last.action_label}{last.state_label}｜{when}｜{last.job_id}")
    return _truncate("\n".join(lines))


def _log_payload(job_id: str) -> str | tuple[str, str, str]:
    """读取日志。返回错误提示字符串，或 (job_id, 头部摘要, 日志正文)"""
    job_id = job_id.strip()
    if not job_id:
        last = pt.latest_status(PATHS)
        if last is None:
            return "还没有任何部署任务记录"
        job_id = last.job_id

    path = PATHS.log_file(job_id)
    if not path.is_file():
        return f"未找到任务 {job_id} 的日志文件\n{path}"

    limit = max(1, int(plugin_config.diting_deploy_log_tail_lines))
    body = pt.tail_lines(path, limit)
    if not body:
        return f"任务 {job_id} 的日志文件是空的"

    status = pt.read_status(PATHS, job_id)
    if status is None:
        header = f"📄 {job_id} 日志尾部（{limit} 行）"
    else:
        when = pt.format_ts(status.finished_ts) if status.finished_ts else "进行中"
        header = (
            f"{status.state_mark} {status.action_label}{status.state_label}｜{job_id}\n"
            f"分支 {status.branch or '—'}｜耗时 {pt.human_duration(status.duration_sec)}｜{when}"
        )
    return job_id, header, body


def _log_nodes(job_id: str, header: str, body: str) -> list[OneBotMessage]:
    """把日志切成若干节点，供合并转发使用。

    节点数超过上限时从**最旧**的日志开始丢弃 —— 部署失败的关键信息（报错、退出码）
    都在尾部，留尾部比留开头有用。
    """
    per_node = max(200, int(plugin_config.diting_deploy_forward_chars_per_node))
    max_nodes = max(2, int(plugin_config.diting_deploy_forward_max_nodes))

    chunks: list[str] = []
    current = ""
    for line in body.splitlines():
        if current and len(current) + len(line) + 1 > per_node:
            chunks.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)

    keep = max_nodes - 1  # 头部摘要占一个节点
    dropped = max(0, len(chunks) - keep)
    if dropped:
        keep = max_nodes - 2  # 「已略去」说明节点也要占一个位置
        dropped = len(chunks) - keep
        chunks = chunks[dropped:]

    nodes = [OneBotMessage(header)]
    if dropped:
        nodes.append(OneBotMessage(f"……（更早的 {dropped} 段已略去；完整日志在宿主机 data/deploy/logs/{job_id}.log）"))
    nodes.extend(OneBotMessage(chunk) for chunk in chunks)
    return nodes


async def _send_forward_log(bot: Bot, session: dict, nodes: list[OneBotMessage]) -> bool:
    """合并转发；失败时返回 False，由调用方回退成纯文本"""
    try:
        info = await bot.get_login_info()
        name = info.get("nickname") or "谛听"
    except Exception:
        name = "谛听"
    uin = str(session.get("bot_self_id") or bot.self_id)
    payload = [SendForwardMsg.to_node(name=name, uin=uin, message=node) for node in nodes]

    try:
        if session.get("type") == "group" and session.get("group_id"):
            await bot.call_api(
                "send_group_forward_msg",
                group_id=str(session["group_id"]),
                messages=payload,
            )
        else:
            await bot.call_api(
                "send_private_forward_msg",
                user_id=str(session["user_id"]),
                messages=payload,
            )
        return True
    except Exception as exc:
        logger.warning(f"[diting_deploy] 合并转发日志失败，回退纯文本: {exc}")
        return False


async def _handle_log(bot: Bot, event: MessageEvent, arg: str) -> None:
    payload = _log_payload(arg)
    if isinstance(payload, str):
        await diting_cmd.finish(payload)
        return

    job_id, header, body = payload
    plain = f"{header}\n{body}"

    if await _send_forward_log(bot, _session_of(event), _log_nodes(job_id, header, body)):
        await diting_cmd.finish()
        return

    await diting_cmd.finish(_truncate_tail(plain))


# ── 派发 ────────────────────────────────────────────────────────
def _preflight(spec: SubCommand) -> Optional[str]:
    """派发前预检，把「写进去没人管」的黑洞任务变成明确报错"""
    if spec.mutates and not plugin_config.diting_deploy_branch.strip():
        return (
            "⛔ 未配置部署分支，拒绝执行。\n"
            "请在服务器 .env 里设置 DITING_DEPLOY_BRANCH"
            "（生产目录一般 master，开发目录 dev/1.0），重启后生效。"
        )

    writable, err = pt.queue_writable(PATHS)
    if not writable:
        return f"⛔ 部署队列目录不可写：\n{PATHS.queue}\n{err}"

    fresh_limit = int(plugin_config.diting_deploy_require_agent_fresh or 0)
    if fresh_limit > 0:
        state = pt.read_state(PATHS)
        if state is None:
            return (
                "⛔ 宿主机执行器未就绪（找不到 state.json）。\n"
                "请在服务器安装并启动 diting-agent，见 docs/diting-deploy.md。"
            )
        age = pt.now_ts() - int(state.get("updated_ts") or 0)
        if age > fresh_limit:
            return (
                f"⛔ 宿主机执行器心跳已过期（{pt.human_duration(age)}前）。\n"
                "请检查服务器上的 diting-agent.path 与 diting-agent.timer 是否在运行。"
            )

    inflight = pt.pending_job_ids(PATHS)
    if inflight:
        return f"⛔ 已有任务在执行：{'、'.join(inflight)}\n等它结束后再试。"

    sentinel = pt.sentinel_info(PATHS)
    if sentinel["present"] and (sentinel["age_sec"] or 0) < 600:
        return (
            f"⛔ 部署锁被占用（{pt.human_duration(sentinel['age_sec'])}），"
            "可能另有一次部署正在进行。"
        )
    return None


async def _dispatch(event: MessageEvent, spec: SubCommand) -> None:
    session = _session_of(event)
    session["bot_self_id"] = getattr(event, "self_id", "") or ""
    request = pt.JobRequest.create(
        action=spec.name,
        branch=plugin_config.diting_deploy_branch.strip(),
        user_id=event.user_id,
        session=session,
        env=ENVIRONMENT,
        bot_self_id=session["bot_self_id"],
    )
    try:
        pt.write_job_request(PATHS, request)
    except OSError as exc:
        logger.opt(exception=True).error(f"[diting_deploy] 写入作业请求失败: {exc}")
        await diting_cmd.finish(f"⛔ 写入作业请求失败：{exc}")
        return

    logger.info(
        f"[diting_deploy] 派发作业 {request.job_id} action={spec.name} "
        f"branch={request.branch} by={event.user_id}"
    )
    _last_invoke[event.user_id] = time.monotonic()
    asyncio.create_task(_watch_job(request.job_id, spec.name, session))

    tail = "\n服务会在执行期间短暂中断，完成后我会主动回报结果。" if spec.mutates else ""
    await diting_cmd.finish(
        f"🚀 已受理 {request.job_id}\n"
        f"{spec.label}｜分支 {request.branch}｜环境 {ENVIRONMENT}{tail}"
    )


async def _watch_job(job_id: str, action: str, session: dict) -> None:
    """跟踪未重启场景下的作业（pull）。build/restart 会把本进程一起换掉，由启动钩子接管"""
    accept_timeout = max(10, int(plugin_config.diting_deploy_accept_timeout))
    deadline_accept = time.monotonic() + accept_timeout
    deadline_total = time.monotonic() + 1800
    started_reported = False
    unclaimed_reported = False

    while time.monotonic() < deadline_total:
        await asyncio.sleep(3)

        if pt.is_reported(PATHS, job_id):
            return  # 已被启动钩子回报过

        status = pt.read_status(PATHS, job_id)
        if status is None:
            # 超过受理上限只是提醒，不写成终态：服务器若只装了 .timer 没装 .path，
            # 作业最晚 5 分钟后才被认领，那时仍然应该把真实结果报出来。
            if not unclaimed_reported and time.monotonic() > deadline_accept:
                unclaimed_reported = True
                await _report(
                    session,
                    f"⏳ 作业 {job_id} 还没被宿主机执行器认领"
                    f"（已超过 {pt.human_duration(accept_timeout)}）。\n"
                    "若服务器只启用了 diting-agent.timer 而没启用 diting-agent.path，"
                    "作业最晚 5 分钟后会被处理；一直没动静就检查 diting-agent.path 是否在运行。\n"
                    "结果出来后我会继续回报。",
                )
            continue

        if not started_reported and status.state in ("queued", "running"):
            started_reported = True
            detail = status.message or status.step_label or "已开始"
            await _report(session, f"🔄 {pt.ACTION_LABELS.get(action, action)}｜{job_id}\n{detail}")

        if status.is_terminal:
            await _finish_report(session, job_id, _render_terminal(status))
            return

    logger.warning(f"[diting_deploy] 作业 {job_id} 跟踪超时（30 分钟），停止跟踪")


# ── 命令处理 ────────────────────────────────────────────────────
diting_cmd = on_command(
    plugin_config.diting_deploy_cmd,
    force_whitespace=True,
    priority=int(plugin_config.diting_deploy_priority),
    block=bool(plugin_config.diting_deploy_block),
)


def _issue_confirm(action: str, user_id: int, session: dict) -> str:
    now = time.monotonic()
    for key, item in list(_pending_confirms.items()):
        if item.expires_ts <= now:
            _pending_confirms.pop(key, None)

    ttl = max(10, int(plugin_config.diting_deploy_confirm_ttl))
    token = secrets.token_hex(3)
    _pending_confirms[token] = _PendingConfirm(
        token=token,
        action=action,
        user_id=user_id,
        session=session,
        expires_ts=now + ttl,
    )
    label = SUBCOMMANDS[action].label
    return (
        f"⚠️ {label} 会中断当前服务，确认请发送：\n"
        f"{_cmd_text('confirm', token)}\n"
        f"（{ttl} 秒内有效，发送 {_cmd_text('cancel')} 可取消）"
    )


async def _handle_confirm(event: MessageEvent, token: str) -> None:
    pending = _pending_confirms.pop(token.strip(), None)
    if pending is None or pending.expires_ts <= time.monotonic():
        await diting_cmd.finish("⛔ 确认令牌无效或已过期，请重新发起命令")
        return
    if pending.user_id != event.user_id or _session_key(pending.session) != _session_key(
        _session_of(event)
    ):
        await diting_cmd.finish("⛔ 这个确认令牌不属于你或不属于本会话")
        return

    spec = SUBCOMMANDS.get(pending.action)
    if spec is None:
        await diting_cmd.finish("⛔ 确认对应的动作已失效，请重新发起命令")
        return
    if not await _allowed(event, spec.perm):
        await diting_cmd.finish("⛔ 你没有权限执行该操作")
        return

    problem = _preflight(spec)
    if problem:
        await diting_cmd.finish(problem)
        return

    await _dispatch(event, spec)


@diting_cmd.handle()
async def _handle_diting(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    tokens = args.extract_plain_text().strip().split()
    raw_sub = tokens[0].lower() if tokens else ""
    extra = tokens[1] if len(tokens) > 1 else ""

    if not raw_sub or raw_sub in ("help", "帮助", "-h", "--help"):
        await diting_cmd.finish(_render_help())
        return

    if raw_sub == "cancel":
        key = _session_key(_session_of(event))
        removed = [
            token
            for token, item in _pending_confirms.items()
            if item.user_id == event.user_id and _session_key(item.session) == key
        ]
        for token in removed:
            _pending_confirms.pop(token, None)
        await diting_cmd.finish(
            f"已取消 {len(removed)} 个待确认操作" if removed else "没有待确认的操作"
        )
        return

    sub_name = ALIASES.get(raw_sub, raw_sub)

    if sub_name == "confirm":
        await _handle_confirm(event, extra)
        return

    spec = SUBCOMMANDS.get(sub_name)
    if spec is None:
        await diting_cmd.finish(f"未知子命令：{raw_sub}\n\n{_render_help()}")
        return

    if not await _allowed(event, spec.perm):
        logger.info(f"[diting_deploy] 权限不足: user={event.user_id} sub={sub_name}")
        await diting_cmd.finish("⛔ 你没有权限执行该操作")
        return

    if sub_name == "status":
        await diting_cmd.finish(_render_status())
        return
    if sub_name == "log":
        await _handle_log(bot, event, extra)
        return

    # 以下都是会改动工作区/服务的动作
    remain = _cooldown_remaining(event.user_id)
    if remain > 0:
        await diting_cmd.finish(f"⏱️ 操作过于频繁，请 {remain} 秒后再试")
        return

    problem = _preflight(spec)
    if problem:
        await diting_cmd.finish(problem)
        return

    if spec.needs_confirm:
        await diting_cmd.finish(_issue_confirm(sub_name, event.user_id, _session_of(event)))
        return

    await _dispatch(event, spec)


# ── 启动钩子 ────────────────────────────────────────────────────
async def _ensure_default_perm_group() -> None:
    """自动创建 diting_deploy 权限组并绑定全部权限点，超管只需 perm 绑定 群 即可授权"""
    group_name = plugin_config.diting_deploy_perm_group.strip() or "diting_deploy"
    perm_keys = sorted({spec.perm for spec in SUBCOMMANDS.values()})

    async with async_session_factory() as session:
        existing = (
            await session.execute(select(PermissionGroup).where(PermissionGroup.name == group_name))
        ).scalars().first()

        if existing is None:
            group = PermissionGroup(
                name=group_name,
                display_name="谛听部署",
                description="自动创建：部署权限组（perm 绑定 群 <群号> 即可授权）",
                created_by=0,
            )
            session.add(group)
            await session.flush()
            for key in perm_keys:
                session.add(PermissionGroupPerm(group_id=group.id, perm_key=key))
            await session.commit()
            logger.info(f"[diting_deploy] 自动创建权限组 {group_name}，绑定 {len(perm_keys)} 个权限点")
            return

        bound = set(
            (
                await session.execute(
                    select(PermissionGroupPerm.perm_key).where(
                        PermissionGroupPerm.group_id == existing.id
                    )
                )
            ).scalars().all()
        )
        missing = [key for key in perm_keys if key not in bound]
        if missing:
            for key in missing:
                session.add(PermissionGroupPerm(group_id=existing.id, perm_key=key))
            await session.commit()
            logger.info(f"[diting_deploy] 权限组 {group_name} 补绑权限点 {missing}")


async def _settle_pending_jobs() -> None:
    """补齐回报：build/restart 会换掉进程，终态结果只能由新实例发出去"""
    try:
        statuses = [
            status
            for status in pt.iter_statuses(PATHS, limit=10)
            if status.action in pt.MUTATING_ACTIONS
        ]
        pending = [s for s in statuses if not pt.is_reported(PATHS, s.job_id)]
        if not pending:
            return

        if await _wait_for_bot(180) is None:
            logger.warning(
                "[diting_deploy] 启动后 180 秒内没有可用的 bot 连接，待回报任务留到下次启动"
            )
            return

        for status in pending:
            if status.is_terminal:
                # 超过一天的旧任务不再打扰，直接标记
                if status.finished_ts and pt.now_ts() - status.finished_ts > 86400:
                    pt.mark_reported(PATHS, status.job_id)
                    continue
                await _finish_report(status.session, status.job_id, _render_terminal(status))
            else:
                asyncio.create_task(_watch_job(status.job_id, status.action, status.session))
    except Exception as exc:
        logger.opt(exception=True).error(f"[diting_deploy] 启动补报失败: {exc}")


def _warn_about_command_name() -> None:
    """命令名与 COMMAND_START 重复加前缀是很容易踩的坑，且症状是「机器人完全静默」"""
    starts = {s for s in (get_driver().config.command_start or set()) if s}
    cmd = plugin_config.diting_deploy_cmd
    for start in sorted(starts):
        if cmd.startswith(start) and cmd != start:
            logger.warning(
                f"[diting_deploy] DITING_DEPLOY_CMD={cmd!r} 已经带了 COMMAND_START 前缀 "
                f"{start!r}，实际注册的命令是 {start}{cmd} —— 输入 {cmd} 不会有任何反应。"
                f"命令名保持默认 diting 即可，前缀由 COMMAND_START 自动补。"
            )
            break


@get_driver().on_startup
async def _diting_deploy_startup() -> None:
    PATHS.ensure()
    pt.write_boot_record(PATHS, ENVIRONMENT)
    _warn_about_command_name()
    try:
        await _ensure_default_perm_group()
    except Exception as exc:
        logger.opt(exception=True).error(f"[diting_deploy] 初始化默认权限组失败: {exc}")
    asyncio.create_task(_settle_pending_jobs())
