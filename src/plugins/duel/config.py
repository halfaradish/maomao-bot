from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    # 优先级
    priority: int = 10
    # 是否阻塞
    block: bool = True

    filename: str = 'duel.json'

    # 没有参数时的默认消息, 
    DEFAULT_MSG: str = (
        "[duel/cf推题] 命令使用方法\n"
        "[使用示例]\n"
        "> /duel daily  每日推题(随机推送一题)\n"
        "> /duel problem *rating '*tags...'  随机匹配符合rating和tags的题。如\"duel problem 2300 'dp' 'binary search'\"\n"
        "> /duel map  与搜题时的映射相关, 使用该命令查看详细"
    )

    # 搜题映射默认消息
    MAP_DEFAULT_MSG: str = (
        "[duel map] 子命令使用详细\n"
        "> /duel map 查看使用帮助\n"
        "> /duel map tags  查看可映射的tags\n"
        "> /duel map current 查看目前的已有的映射对\n"
        "> /duel map add '*tag' '*tag_to_map' 添加映射。如\"duel map add 'binary search' '二分'\"\n"
        "> /duel map rm '*tag' '*tag_to_map' 删除映射。如\"duel map add 'binary search' '二分'\""
    )