"""

权限系统测试插件



用法: authban @成员 60

      authunban @成员

      authkick @成员

      authauthtest [次数]



所有命令与 group_ban 功能完全相同，仅加了 auth 前缀用于测试环境。

"""



from __future__ import annotations



import os

import time



from nonebot import get_driver, on_command

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message

from nonebot.exception import FinishedException

from nonebot.log import logger

from nonebot.params import CommandArg

from nonebot.plugin import PluginMetadata



from ...common import JsonUtils

from ...common.siqi_auth_client import siqi_auth

from .config import Config



__plugin_meta__ = PluginMetadata(

    name="权限系统测试",

    description="通过 auth 前缀命令测试司契权限系统，功能与 group_ban 完全相同",

    usage="authban @成员 60 / authunban @成员 / authkick @成员 / authauthtest",

    type="application",

    supported_adapters={"~onebot.v11"},

)



# 本地白名单配置（当司契权限系统不可用时的降级方案）

# 注意：文件名现在也支持从配置读取，但为了保持最小改动逻辑，这里优先使用配置， fallback 到常量

WHITELIST_FILENAME_DEFAULT = "ban_whitelist.json"

DEFAULT_WHITELIST = {

    "group_whitelist": [],

    "user_whitelist": ["3026754892","434732989"],

}



driver = get_driver()

global_config = driver.config

# 加载插件专属配置

try:

    plugin_config = Config(**global_config.model_dump())

except Exception:

    # 兼容旧版或配置缺失情况，使用默认值

    plugin_config = Config()



def _get_whitelist_filename() -> str:

    return getattr(plugin_config, 'group_ban_whitelist_filename', WHITELIST_FILENAME_DEFAULT)



def _load_whitelist() -> dict:

    """加载本地 JSON 白名单（降级用）"""

    filename = _get_whitelist_filename()

    data, _ = JsonUtils.read(filename, DEFAULT_WHITELIST)

    if not isinstance(data, dict):

        # 如果读取失败，尝试合并配置中的默认白名单

        default_data = DEFAULT_WHITELIST.copy()

        if hasattr(plugin_config, 'group_ban_default_group_whitelist'):

            default_data['group_whitelist'] = plugin_config.group_ban_default_group_whitelist

        if hasattr(plugin_config, 'group_ban_default_user_whitelist'):

            default_data['user_whitelist'] = plugin_config.group_ban_default_user_whitelist

        return default_data



    # 合并配置中的默认白名单（如果文件中没有定义）

    if "group_whitelist" not in data:

        data["group_whitelist"] = getattr(plugin_config, 'group_ban_default_group_whitelist', [])

    if "user_whitelist" not in data:

        data["user_whitelist"] = getattr(plugin_config, 'group_ban_default_user_whitelist', ["3026754892","434732989"])



    return data





def _is_allowed_local(event: GroupMessageEvent) -> bool:

    """本地白名单检查（降级方案）"""

    whitelist = _load_whitelist()

    user_id = str(event.user_id)

    group_id = str(event.group_id)



    if user_id in driver.config.superusers:

        return True

    if user_id in whitelist["user_whitelist"]:

        return True

    if group_id in whitelist["group_whitelist"]:

        return True

    return False





async def _is_allowed(event: GroupMessageEvent, perm_key: str = "member:ban") -> tuple[bool, str]:

    """

    权限检查：优先使用司契权限系统，失败时降级到本地白名单



    Args:

        event: 群消息事件

        perm_key: 权限标识，如 "member:ban", "member:kick"

    """

    user_id = str(event.user_id)





    # 如果司契权限系统已启用，优先使用

    if siqi_auth.enabled:

        try:

            allowed, reason = await siqi_auth.check(perm_key, user_id)

            return allowed, reason

        except Exception as e:

            logger.warning(f"[auth_plugin] 司契权限系统调用失败，降级到本地白名单: {e}")

            return _is_allowed_local(event), "权限系统调用失败，且本地白名单未命中"



    # 未启用司契权限系统，使用本地白名单

    return _is_allowed_local(event), "local_whitelist" if _is_allowed_local(event) else "本地白名单未命中"





def _extract_target(event: GroupMessageEvent) -> int | None:

    """返回要禁言的用户 QQ 号"""

    for seg in event.get_message():

        if seg.type != "at":

            continue

        qq = seg.data.get("qq")

        if not qq or qq in ("all", str(event.self_id)):

            continue

        try:

            return int(qq)

        except ValueError:

            return None

    return None





def _parse_duration(arg_text: str) -> int | None:

    text = arg_text.strip()

    if not text:

        return None

    # 允许简单单位（s/m/h），默认秒

    factor = 1

    if text[-1].lower() in ("s", "m", "h"):

        unit = text[-1].lower()

        text = text[:-1]

        if unit == "m":

            factor = 60

        elif unit == "h":

            factor = 3600

    if not text.isdigit():

        return None

    seconds = int(text) * factor

    return seconds if seconds > 0 else None





# 使用配置中的指令名称，默认为 authban, authunban, authkick

ban_cmd = on_command(plugin_config.group_ban_cmd, priority=plugin_config.group_ban_priority, block=plugin_config.group_ban_block)

unban_cmd = on_command(plugin_config.group_unban_cmd, priority=plugin_config.group_ban_priority, block=plugin_config.group_ban_block)

kick_cmd = on_command(plugin_config.group_kick_cmd, priority=plugin_config.group_ban_priority, block=plugin_config.group_ban_block)

authtest_cmd = on_command(plugin_config.group_authtest_cmd, priority=5, block=True)





@ban_cmd.handle()

async def handle_ban(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):

    try:

        if not isinstance(event, GroupMessageEvent):

            await ban_cmd.finish("仅支持在群聊中使用禁言功能")

            return



        # 获取权限检查结果

        if event.user_id in driver.config.superusers:

            allowed = True

            reason = "superuser"

        else:

            if siqi_auth.enabled:

                try:

                    allowed, reason = await siqi_auth.check("member:ban", str(event.user_id))

                except Exception as e:

                    logger.warning(f"[auth_plugin] 权限系统调用失败，降级到本地白名单: {e}")

                    allowed = _is_allowed_local(event)

                    reason = "local_whitelist" if allowed else "权限系统调用失败，且本地白名单未命中"

            else:

                allowed = _is_allowed_local(event)

                reason = "local_whitelist" if allowed else "本地白名单未命中"



        if not allowed:

            await ban_cmd.finish(f"你没有权限使用禁言功能: {reason or '无权限'}")

            return



        target_user = _extract_target(event)

        if not target_user:

            await ban_cmd.finish("请 @ 需要禁言的用户")

            return



        # 检查被禁言对象是否为管理员/群主

        try:

            member_info = await bot.get_group_member_info(

                group_id=event.group_id, user_id=target_user, no_cache=True

            )

        except Exception as e:

            logger.error(f"获取成员信息失败: {e}")

            await ban_cmd.finish("无法获取成员信息，禁言已取消")

            return



        role = member_info.get("role")

        if role in ("admin", "owner"):

            await ban_cmd.finish("无法禁言管理员或群主")

            return



        duration = _parse_duration(args.extract_plain_text())

        if duration is None:

            await ban_cmd.finish("请提供禁言时长（数字或带 s/m/h），例如 60、10m")

            return



        try:

            await bot.set_group_ban(group_id=event.group_id, user_id=target_user, duration=duration)



            # 再次获取信息以确认禁言是否生效

            verify_info = await bot.get_group_member_info(

                group_id=event.group_id, user_id=target_user, no_cache=True

            )

            shut_up_timestamp = verify_info.get("shut_up_timestamp", 0)

            if shut_up_timestamp <= time.time():

                await ban_cmd.finish("禁言可能未生效（用户可能为管理员），请人工确认")

                return



            await ban_cmd.finish(f"已禁言 {target_user}，时长 {duration} 秒")

        except FinishedException:

            raise

        except Exception as e:

            logger.error(f"设置禁言失败: {e}")

            await ban_cmd.finish("禁言失败，请检查机器人权限")

    finally:

        logger.info(f"[auth_plugin] ban user={event.user_id} group={event.group_id}")





@unban_cmd.handle()

async def handle_unban(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):

    try:

        if not isinstance(event, GroupMessageEvent):

            await unban_cmd.finish("仅支持在群聊中使用禁言功能")

            return



        # 获取权限检查结果

        if event.user_id in driver.config.superusers:

            allowed = True

            reason = "superuser"

        else:

            if siqi_auth.enabled:

                try:

                    allowed, reason = await siqi_auth.check("member:ban", str(event.user_id))

                except Exception as e:

                    logger.warning(f"[auth_plugin] 权限系统调用失败，降级到本地白名单: {e}")

                    allowed = _is_allowed_local(event)

                    reason = "local_whitelist" if allowed else "权限系统调用失败，且本地白名单未命中"

            else:

                allowed = _is_allowed_local(event)

                reason = "local_whitelist" if allowed else "本地白名单未命中"



        if not allowed:

            await unban_cmd.finish(f"你没有权限使用解除禁言功能: {reason or '无权限'}")

            return



        target_user = _extract_target(event)

        if not target_user:

            await unban_cmd.finish("请 @ 需要解除禁言的用户")

            return



        try:

            member_info = await bot.get_group_member_info(

                group_id=event.group_id, user_id=target_user, no_cache=True

            )

        except Exception as e:

            logger.error(f"获取成员信息失败: {e}")

            await unban_cmd.finish("无法获取成员信息，解除禁言已取消")

            return



        shut_up_timestamp = member_info.get("shut_up_timestamp", 0)

        if shut_up_timestamp <= time.time():

            await unban_cmd.finish("该用户当前没有被禁言")

            return



        try:

            await bot.set_group_ban(group_id=event.group_id, user_id=target_user, duration=0)

            await unban_cmd.finish(f"已解除 {target_user} 的禁言")

        except FinishedException:

            raise

        except Exception as e:

            logger.error(f"解除禁言失败: {e}")

            await unban_cmd.finish("解除禁言失败，请检查机器人权限")

    finally:

        logger.info(f"[auth_plugin] unban user={event.user_id} group={event.group_id}")





async def _bot_can_manage(bot: Bot, group_id: int) -> bool:

    """检查机器人是否为管理员/群主"""

    try:

        info = await bot.get_group_member_info(group_id=group_id, user_id=bot.self_id, no_cache=True)

        return info.get("role") in {"admin", "owner"}

    except Exception as e:

        logger.error(f"获取机器人身份失败: {e}")

        return False





@kick_cmd.handle()

async def handle_kick(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):

    try:

        if not isinstance(event, GroupMessageEvent):

            await kick_cmd.finish("仅支持在群聊中使用踢人功能")

            return



        # 获取权限检查结果

        if event.user_id in driver.config.superusers:

            allowed = True

            reason = "superuser"

        else:

            if siqi_auth.enabled:

                try:

                    allowed, reason = await siqi_auth.check("member:kick", str(event.user_id))

                except Exception as e:

                    logger.warning(f"[auth_plugin] 权限系统调用失败，降级到本地白名单: {e}")

                    allowed = _is_allowed_local(event)

                    reason = "local_whitelist" if allowed else "权限系统调用失败，且本地白名单未命中"

            else:

                allowed = _is_allowed_local(event)

                reason = "local_whitelist" if allowed else "本地白名单未命中"



        if not allowed:

            await kick_cmd.finish(f"你没有权限使用踢人功能: {reason or '无权限'}")

            return



        if not await _bot_can_manage(bot, event.group_id):

            await kick_cmd.finish("机器人没有管理员权限，无法踢人")

            return



        target_user = _extract_target(event)

        if not target_user:

            await kick_cmd.finish("请 @ 需要踢出的用户")

            return



        if target_user == event.self_id:

            await kick_cmd.finish("不能踢出机器人自己")

            return



        try:

            member_info = await bot.get_group_member_info(

                group_id=event.group_id, user_id=target_user, no_cache=True

            )

        except Exception as e:

            logger.error(f"获取成员信息失败: {e}")

            await kick_cmd.finish("无法获取成员信息，踢人已取消")

            return



        role = member_info.get("role")

        if role in ("admin", "owner"):

            await kick_cmd.finish("无法踢出管理员或群主")

            return



        try:

            await bot.set_group_kick(group_id=event.group_id, user_id=target_user, reject_add_request=False)

            await kick_cmd.finish(f"已将 {target_user} 移出群聊")

        except FinishedException:

            raise

        except Exception as e:

            logger.error(f"踢出成员失败: {e}")

            await kick_cmd.finish("踢出失败，请检查机器人权限")

    finally:

        logger.info(f"[auth_plugin] kick user={event.user_id} group={event.group_id}")

# =============================================================================

# 延迟测试命令 - 用于测量司契权限系统的实际响应延迟

# 用法: authauthtest          (默认测10次)

#       authauthtest 20       (测20次)

# =============================================================================



@authtest_cmd.handle()

async def handle_authtest(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):

    """测试司契权限系统延迟"""

    if not isinstance(event, GroupMessageEvent):

        await authtest_cmd.finish("仅支持在群聊中使用")

        return



    user_id = str(event.user_id)





    if not siqi_auth.enabled:

        await authtest_cmd.finish("❌ 司契权限系统未启用 (SIQI_AUTH_ENABLED=false)")

        return



    # 解析测试次数

    raw = args.extract_plain_text().strip()



    rounds = 10

    if raw.isdigit():

        rounds = max(1, min(int(raw), 100))  # 限制 1-100



    await bot.send(event, f"⏳ 正在进行 {rounds} 次延迟测试（含缓存命中 & 未命中）...")



    # --- 测试1: 缓存命中测试（固定 user_id，首次 miss 后全部 hit） ---

    cached_stats = await siqi_auth.batch_check_latency("member:ban", user_id, rounds)

    # 分离首次请求（可能含连接建立/缓存miss）与后续请求（连接复用/缓存hit）

    cached_first_ms = cached_stats['latencies'][0] if cached_stats['latencies'] else 0

    cached_rest = cached_stats['latencies'][1:] if len(cached_stats['latencies']) > 1 else []

    cached_rest_avg = sum(cached_rest) / len(cached_rest) if cached_rest else 0



    # --- 测试2: 缓存未命中测试（每次随机 user_id，强制每次 DB 查询） ---

    nocache_stats = await siqi_auth.batch_check_latency_nocache("member:ban", rounds)



    # --- 测试3: 对比本地白名单延迟 ---

    local_start = time.perf_counter()

    for _ in range(rounds):

        _is_allowed_local(event)

    local_total_ms = (time.perf_counter() - local_start) * 1000

    local_avg_ms = local_total_ms / rounds



    # --- 测试4: 模拟完整命令流程延迟（权限检查 + 获取成员信息） ---

    e2e_start = time.perf_counter()

    await siqi_auth.check("member:ban", user_id)

    try:

        await bot.get_group_member_info(

            group_id=event.group_id, user_id=event.user_id, no_cache=True

        )

    except Exception:

        pass

    e2e_ms = (time.perf_counter() - e2e_start) * 1000



    result = (

        f"📊 司契权限系统延迟测试报告\n"

        f"{'=' * 30}\n"

        f"🔗 目标: {siqi_auth.base_url}\n"

        f"📡 端口: {siqi_auth.port} "

        f"({'auth_agent 本地从库' if siqi_auth.port == 8881 else 'auth_server 主库'})\n"

        f"🔑 权限: member:ban\n"

        f"👤 用户: {user_id}\n"

        f"{'=' * 30}\n"

        f"\n"

        f"【缓存命中测试】({rounds}次，固定user_id)\n"

        f"  首次：{cached_first_ms:.2f}ms (含连接建立+缓存miss)\n"

        f"  后续平均：{cached_rest_avg:.2f}ms (连接复用+缓存hit)\n"

        f"  整体平均：{cached_stats['avg_ms']:.2f}ms\n"

        f"  最快：{cached_stats['min_ms']:.2f}ms\n"

        f"  最慢：{cached_stats['max_ms']:.2f}ms\n"

        f"  P50:  {cached_stats['p50_ms']:.2f}ms\n"

        f"  P99:  {cached_stats['p99_ms']:.2f}ms\n"

        f"  成功：{cached_stats['success_count']}/{rounds}\n"

        f"  结果：{'✅ 允许' if cached_stats['last_allowed'] else '❌ 拒绝'}\n"

        f"\n"

        f"【缓存未命中测试】({rounds}次，每次随机user_id)\n"

        f"  平均：{nocache_stats['avg_ms']:.2f}ms (每次都查DB)\n"

        f"  最快：{nocache_stats['min_ms']:.2f}ms\n"

        f"  最慢：{nocache_stats['max_ms']:.2f}ms\n"

        f"  P50:  {nocache_stats['p50_ms']:.2f}ms\n"

        f"  P99:  {nocache_stats['p99_ms']:.2f}ms\n"

        f"  成功：{nocache_stats['success_count']}/{rounds}\n"

        f"\n"

        f"【本地白名单延迟】({rounds}次)\n"

        f"  平均：{local_avg_ms:.4f}ms\n"

        f"\n"

    )



    await authtest_cmd.finish(result)