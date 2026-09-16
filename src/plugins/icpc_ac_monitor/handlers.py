# src/plugins/icpc_ac_monitor/handlers.py
"""全部命令 matcher 与 handler（含赛时过题查询）"""

import asyncio
import threading

import requests
from nonebot import logger, on_command
from nonebot.adapters.onebot.v11 import Bot, Event, Message
from nonebot.params import CommandArg

from .mappings import (
    SCHOOL_NAME_MAP,
    _ensure_comp_display,
    _is_school_match,
    _resolve_city_display_name,
)
from .monitor_service import monitor_loop
from .push import set_bot_instance
from .standings import _pid_to_char, _to_base_url
from .state import AT_WHITELIST, SCHOOLS, TARGET_GROUPS, conf, memory, save_conf
from .whitelist import (
    _extract_mentions,
    _is_authorized,
    _parse_qq_numbers,
    _persist_at_whitelist,
)

# ==============================================================================
# 命令注册
# ==============================================================================
start_monitor = on_command("开始监控", aliases={"monitor"}, priority=5)
stop_monitor = on_command("取消监控", aliases={"stop"}, priority=5)
add_at_whitelist = on_command(
    "添加监控", aliases={"添加监控名单", "添加监控指令", "添加监控艾特", "添加监控提醒", "添加ac艾特"}, priority=5, block=True
)
remove_at_whitelist = on_command(
    "移除监控", aliases={"移除监控艾特", "删除监控艾特", "删除ac艾特"}, priority=5, block=True
)
list_at_whitelist = on_command(
    "查看监控名单", aliases={"查看监控艾特", "查看ac艾特", "ac艾特名单"}, priority=5, block=True
)
monitor_help = on_command("监控", priority=5, block=True)
logger.info("icpc_ac_monitor 插件加载完成")


@add_at_whitelist.handle()
async def handle_add_at(event: Event, args: Message = CommandArg()):
    if not await _is_authorized(event):
        await add_at_whitelist.finish("只有白名单成员或管理员可执行此命令。")
    text = args.extract_plain_text().strip()
    mention_qqs = _extract_mentions(args)
    group_id = getattr(event, "group_id", None)

    parsed_numbers: list[int] = []
    if text:
        try:
            parsed_numbers = _parse_qq_numbers(text)
        except ValueError as e:
            await add_at_whitelist.finish(str(e))

    qqs = mention_qqs + parsed_numbers
    if not qqs:
        await add_at_whitelist.finish("请在命令后提供要添加的 QQ 号，可直接输入或 @ 指定。")

    added = []
    for qq in qqs:
        previous = AT_WHITELIST.get(qq)
        if previous == group_id:
            continue
        AT_WHITELIST[qq] = group_id if group_id is not None else None
        added.append(qq)
    if added:
        _persist_at_whitelist()
        msg = f"成功添加 {len(added)} 个 QQ 到艾特白名单：" + ", ".join(map(str, added))
    else:
        msg = "全部 QQ 已存在于白名单。"
    await add_at_whitelist.finish(msg)


@remove_at_whitelist.handle()
async def handle_remove_at(event: Event, args: Message = CommandArg()):
    if not await _is_authorized(event):
        await remove_at_whitelist.finish("只有白名单成员或管理员可执行此命令。")
    text = args.extract_plain_text().strip()
    mention_qqs = _extract_mentions(args)

    parsed_numbers: list[int] = []
    if text:
        try:
            parsed_numbers = _parse_qq_numbers(text)
        except ValueError as e:
            await remove_at_whitelist.finish(str(e))

    qqs = mention_qqs + parsed_numbers
    if not qqs:
        await remove_at_whitelist.finish("请在命令后提供要移除的 QQ 号，可直接输入或 @ 指定。")

    removed = []
    for qq in qqs:
        if qq in AT_WHITELIST:
            AT_WHITELIST.pop(qq, None)
            removed.append(qq)
    if removed:
        _persist_at_whitelist()
        msg = f"已从艾特白名单移除 {len(removed)} 个 QQ：" + ", ".join(map(str, removed))
    else:
        msg = "这些 QQ 不在白名单中。"
    await remove_at_whitelist.finish(msg)


async def _resolve_display_name(bot: Bot, qq: int, group_id: int | None) -> str:
    """优先返回群名片，其次昵称"""
    if group_id:
        try:
            info = await bot.get_group_member_info(group_id=group_id, user_id=qq, no_cache=True)
            card = (info.get("card") or "").strip()
            nickname = (info.get("nickname") or "").strip()
            if card:
                return card
            if nickname:
                return nickname
        except Exception as e:
            logger.debug(f"获取群成员信息失败：qq={qq}, group={group_id}, err={e}")
    try:
        info = await bot.get_stranger_info(user_id=qq, no_cache=True)
        nickname = (info.get("nickname") or "").strip()
        if nickname:
            return nickname
    except Exception as e:
        logger.debug(f"获取陌生人信息失败：qq={qq}, err={e}")
    return str(qq)


async def _resolve_group_name(bot: Bot, group_id: int | None) -> str:
    if group_id is None:
        return "所有群"
    try:
        info = await bot.get_group_info(group_id=group_id, no_cache=True)
        name = info.get("group_name")
        if name:
            return name
    except Exception as e:
        logger.debug(f"获取群信息失败：group_id={group_id}, err={e}")
    return str(group_id)


@list_at_whitelist.handle()
async def handle_list_at(bot: Bot, event: Event):
    if not await _is_authorized(event):
        await list_at_whitelist.finish("只有白名单成员或管理员可执行此命令。")
    if not AT_WHITELIST:
        await list_at_whitelist.finish("当前艾特白名单为空，可使用『添加监控』命令添加。")

    group_id = getattr(event, "group_id", None)
    lines = []
    for qq, bind_group in AT_WHITELIST.items():
        display = await _resolve_display_name(bot, qq, group_id)
        group_label = await _resolve_group_name(bot, bind_group)
        lines.append(f"{display} - {qq}（{group_label}）")

    await list_at_whitelist.finish("当前艾特白名单：\n" + "\n".join(lines))


@monitor_help.handle()
async def handle_monitor_help():
    msg = (
        "监控指令一览：\n"
        "1. 开始监控 <比赛URL>\n"
        "2. 取消监控 <比赛URL>\n"
        "3. 添加监控 <QQ/@成员>\n"
        "4. 移除监控 <QQ/@成员>\n"
        "5. 查看监控名单"
    )
    await monitor_help.finish(msg)

# ==============================================================================
# 开始监控 —— 全局开关
# ==============================================================================
@start_monitor.handle()
async def handle_start_monitor(bot: Bot, event: Event, args: Message = CommandArg()):
    """开始监控比赛"""
    set_bot_instance(bot)
    url = args.extract_plain_text().strip()
    if not url or not url.startswith("https://board.xcpcio.com"):
        await start_monitor.finish(
            "请输入正确比赛网址，例如：\n开始监控 https://board.xcpcio.com/icpc/50th/shenyang"
        )
    base_url = _to_base_url(url)

    # 全局重复判断
    if base_url in memory:
        await start_monitor.finish("该比赛已在监控列表中，无需重复添加。")

    # 获取比赛配置信息（包含开始时间戳）
    contest_start_timestamp = None
    try:
        # 尝试读取 config.json
        config_resp = requests.get(f"{base_url}/config.json", timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        config_data = config_resp.json()
        contest_start_timestamp = config_data.get("start_time")
        if contest_start_timestamp:
            logger.info(f"读取到比赛开始时间戳：{contest_start_timestamp}")
    except Exception as e:
        # 如果 config.json 不存在，尝试 contest.json
        try:
            contest_resp = requests.get(f"{base_url}/contest.json", timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            contest_data = contest_resp.json()
            contest_start_timestamp = contest_data.get("start_time")
            if contest_start_timestamp:
                logger.info(f"从 contest.json 读取到比赛开始时间戳：{contest_start_timestamp}")
        except Exception:
            logger.warning(f"获取比赛配置失败：{e}")

    # 拉队伍并过滤学校
    try:
        resp = requests.get(f"{base_url}/team.json", timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        data = resp.json()

        # 兼容数组和字典两种格式
        if isinstance(data, list):
            team_list = data
        elif isinstance(data, dict):
            team_list = list(data.values())
        else:
            raise ValueError("team.json 返回的数据不是列表或字典")

    except Exception as e:
        logger.error(f"获取队伍数据失败：{e}, 内容: {resp.text[:500]}")
        await start_monitor.finish(f"获取队伍数据失败：{e}")

    watched_teams = [t for t in team_list if _is_school_match(t.get("organization", ""), SCHOOLS, SCHOOL_NAME_MAP)]
    if not watched_teams:
        await start_monitor.finish(f"{base_url.split('/')[-1]} 中没有指定学校队伍")

    team_ids_list = []
    watched_ids = []
    id_to_name_dict = {}
    id_to_school_dict = {}
    for t in team_list:
        tid_raw = t.get("id") or t.get("team_id")
        tid = str(tid_raw) if tid_raw is not None else ""
        team_ids_list.append(tid)
        id_to_name_dict[tid] = t.get("name", "未知队伍")
        id_to_school_dict[tid] = t.get("organization", "未知")
        if _is_school_match(t.get("organization", ""), SCHOOLS, SCHOOL_NAME_MAP):
            watched_ids.append(tid)

    comp_slug = base_url.split("/")[-1]
    meta = {
        "comp_name": comp_slug,
        "comp_display_name": _resolve_city_display_name(comp_slug),
        "run_url": f"{base_url}/run.json",
        "team_ids": team_ids_list,
        "watched_ids": watched_ids,
        "id_to_name": id_to_name_dict,
        "id_to_school": id_to_school_dict,
        "already_solved": [],
        "contest_start_timestamp": contest_start_timestamp,  # 存储比赛开始时间戳（Unix 时间戳）
    }
    logger.info(f"监控配置：队伍数量={len(team_ids_list)}, 目标群={len(TARGET_GROUPS)}个")
    memory[base_url] = meta
    conf["monitors"] = memory
    save_conf(conf)
    await start_monitor.send(f"已添加全局监控：{_ensure_comp_display(meta)}")

    # 启动唯一轮询线程
    thread = threading.Thread(target=monitor_loop, args=(base_url,), daemon=True)
    memory[base_url]["thread"] = thread
    thread.start()

# ==============================================================================
# 取消监控 —— 全局关闭
# ==============================================================================
@stop_monitor.handle()
async def handle_stop_monitor(bot: Bot, event: Event, args: Message = CommandArg()):
    """取消监控比赛"""
    url = args.extract_plain_text().strip()
    if not url or not url.startswith("https://board.xcpcio.com"):
        await stop_monitor.finish("请输入要暂停的比赛网址，例如：\n取消监控 https://board.xcpcio.com/icpc/50th/shenyang")
    base_url = _to_base_url(url)

    meta = memory.pop(base_url, None)
    if not meta:
        await stop_monitor.finish("目前没有该比赛的监控～")

    # 立刻落盘
    conf["monitors"] = memory
    save_conf(conf)
    await stop_monitor.finish(f"已完全停止监控：{_ensure_comp_display(meta)}")

# -------------------- 新增指令：赛时过题（按队输出） --------------------
query_status = on_command("赛时过题", aliases={"过题情况"}, priority=5)


def fetch_ac_status(base_url: str, schools: list[str]) -> dict:
    """
    在同步线程中执行：拉 team.json 和 run.json，返回统计结果字典：
    {
      "comp_name": "zhengzhou",
      "teams": [
         {"id": "67", "name": "远航者的幻想乡", "solved": ["A","C"], "count": 2},
         ...
      ]
    }
    """
    comp_slug = base_url.split("/")[-1]
    result = {
        "comp_name": _resolve_city_display_name(comp_slug),
        "comp_slug": comp_slug,
        "teams": [],
    }
    try:
        t_resp = requests.get(f"{base_url}/team.json", timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        t_resp.raise_for_status()
        teams = t_resp.json()  # list of team objects
    except Exception as e:
        raise RuntimeError(f"读取 team.json 失败：{e}")

    try:
        r_resp = requests.get(f"{base_url}/run.json", timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        r_resp.raise_for_status()
        runs = r_resp.json()  # list of run objects
    except Exception as e:
        raise RuntimeError(f"读取 run.json 失败：{e}")

    # 过滤出我们关注的正式队伍（organization in schools）
    # team entries example: {"id":"67","name":"远航者的幻想乡","organization":"广西大学", ...}
    id_to_name = {}
    watched_team_ids = set()
    for t in teams:
        try:
            tid = t.get("id")
        except Exception:
            continue
        org = t.get("organization", "")
        if _is_school_match(org, schools, SCHOOL_NAME_MAP):
            watched_team_ids.add(tid)
            id_to_name[tid] = t.get("name", str(tid))

    # 如果没有关注的队伍，直接返回空 teams
    if not watched_team_ids:
        return result

    # 统计每队已 AC 的题目集合（去重）
    accept_statuses = {"CORRECT", "ACCEPTED", "AC"}  # 兼容多种写法
    team_solved: dict[str, set] = {tid: set() for tid in watched_team_ids}
    for run in runs:
        tid = run.get("team_id")
        if tid not in watched_team_ids:
            continue
        status = run.get("status", "")
        if status not in accept_statuses:
            continue
        pid = run.get("problem_id")
        # 把 pid 转为字母
        ch = _pid_to_char(pid)
        team_solved[tid].add(ch)

    # 组装结果
    for tid in sorted(watched_team_ids, key=lambda x: id_to_name.get(x, x)):
        solved_list = sorted(team_solved.get(tid, []), key=lambda s: (len(s) > 1, s))  # 尽量按字母排序，数字题号靠后
        result["teams"].append({
            "id": tid,
            "name": id_to_name.get(tid, str(tid)),
            "solved": solved_list,
            "count": len(solved_list),
        })
    return result

@query_status.handle()
async def handle_query_status(bot: Bot, event: Event, args: Message = CommandArg()):
    """
    用法：
      @bot 赛时过题 https://board.xcpcio.com/ccpc/11th/zhengzhou
    输出（每队一行）：
      远航者的幻想乡 在 zhengzhou 已过了 A,B 共 2 题
    """
    text = args.extract_plain_text().strip()
    if not text:
        await query_status.finish("请在命令后提供比赛链接，例如：\n@bot 赛时过题 https://board.xcpcio.com/ccpc/11th/zhengzhou")

    # 只取第一个看起来像 URL 的部分（本命令只处理一个 URL）
    url = text.split()[0]
    if not url.startswith("https://board.xcpcio.com"):
        await query_status.finish("请输入合法的 board.xcpcio.com 比赛链接，例如：\n@bot 赛时过题 https://board.xcpcio.com/ccpc/11th/zhengzhou")

    base_url = _to_base_url(url)

    # 在线程池里同步请求远程数据，避免阻塞 nonebot 事件循环
    try:
        info = await asyncio.to_thread(fetch_ac_status, base_url, SCHOOLS)
    except Exception as e:
        await query_status.finish(f"查询失败：{e}")

    if info.get("comp_name"):
        comp_name = info["comp_name"]
    else:
        comp_name = _resolve_city_display_name(info.get("comp_slug", base_url.split("/")[-1]))
    teams = info.get("teams", [])

    if not teams:
        await query_status.finish(f"{comp_name} 中没有来自配置 schools 的队伍（{', '.join(SCHOOLS)}）或没有数据。")

    # 构建消息，每队一行
    lines = []
    for t in teams:
        name = t["name"]
        solved = t["solved"]
        count = t["count"]
        if count == 0:
            lines.append(f"{name} 在 {comp_name} 还未通过任何题目")
        else:
            # 按你的示例要求，用逗号分隔题号（不加空格更紧凑）
            lines.append(f"{name} 在 {comp_name} 已过了 {','.join(solved)} 共 {count} 题")

    # 如果行数过多可截断或分页——这里一次性返回全部
    msg = "\n".join(lines)
    await query_status.finish(msg)
