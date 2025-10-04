from nonebot import (
    get_plugin_config,
    logger,
    on_notice
)
from nonebot.adapters.onebot.v11 import (
    PokeNotifyEvent,
    MessageSegment,
)
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule
from nonebot.exception import FinishedException

from typing import Optional
import redis

from .config import Config
from ...config import RedisConfig

__plugin_meta__ = PluginMetadata(
    name="poke_notify",
    description="处理戳一戳事件",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

# 创建Redis连接池
redis_pool = redis.ConnectionPool(
    username="default",
    host=RedisConfig.NEW_OJ_HOST,
    port=RedisConfig.NEW_OJ_PORT,
    db=RedisConfig.NEW_OJ_DB,
    password=RedisConfig.NEW_OJ_PASSWORD
)

def get_redis_connection():
    """获取Redis连接"""
    return redis.Redis(connection_pool=redis_pool)

def is_poke(event) -> bool:
    return isinstance(event, PokeNotifyEvent)

poke = on_notice(rule=Rule(is_poke), priority=5, block=False)

@poke.handle()
async def _(bot, event: PokeNotifyEvent):
    """处理戳一戳事件"""
    # 事件类型
    sub_type: str = event.sub_type
    # 发起戳一戳的用户
    user_id: str = str(event.user_id)
    # 被戳一戳的用户
    target_id: str = str(event.target_id)
    # bot的qq号
    self_id: str = str(event.self_id)

    if sub_type != "poke" or target_id != self_id:
        return
    
    try:
        r = get_redis_connection()
        redis_user_key: str = f"DiTing:poke:request:{user_id}"
        redis_ban_id = f"DiTing:poke:ban:{user_id}"

        # 检查是否已被ban
        is_ban = r.get(redis_ban_id)
        if is_ban:
            return

        pipe = r.pipeline()
        pipe.incr(redis_user_key)
        pipe.expire(redis_user_key, config.expire_time)
        cur_cnt, _ = pipe.execute()

        # 记录过期时间
        ttl = r.ttl(redis_user_key)
        remain_time = ttl if ttl != -1 else config.expire_time
        # 查看是否超过限制
        exceeded = cur_cnt > config.max_request

        poke_user = MessageSegment.at(user_id)
        if not exceeded:
            logger.info(f"用户 {user_id} 戳了戳bot {cur_cnt} 次")
            # 根据不同次数返回不同回复
            responses = [
                "不要再戳我啦~",
                "好痒好痒，别戳啦~",
                "最后一次警告，再戳我就生气了！"
            ]
            response_idx = min(cur_cnt-1, len(responses)-1)
            await poke.finish(poke_user + responses[response_idx])
        else:
            logger.info(f"用户 {user_id} 戳了戳bot {cur_cnt} 次，剩余 {remain_time} 秒")
            r.set(redis_ban_id, 1, ex=config.expire_time)
            await poke.finish(poke_user + " 哼！不理你了")
    except FinishedException as e:
        pass
    except redis.RedisError as e:
        logger.error(f"Redis操作异常: {e}")
    except Exception as e:
        logger.error(f"处理戳一戳事件异常: {e}")