from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    priority: int = 10

    post_url: str = 'http://8.163.30.212:1145/api/generate-image'

    post_timeout: float = 30.0

    DEFAULT_MSG: str = (
        "云剪切板：\n"
        "回复文本消息并使用该命令，即可获取文本'代码语法高亮'后的图片\n"
        "注：该命令只能转化有效的纯文本内容"
    )