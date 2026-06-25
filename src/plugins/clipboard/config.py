from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    clip_cmd: str = "cv"

    clip_priority: int

    clip_post_url: str
    clip_md_post_url: str = "http://172.16.40.37:1145/api/generate-markdown-image"

    clip_post_timeout: float = 30.0

    DEFAULT_MSG: str = (
        "云剪切板（cv、cvmd）：\n"
        "回复文本消息并使用该命令，即可获取文本'代码语法高亮'后的图片\n"
        "注：cv命令只能转化有效的纯文本内容\n"
        "cvmd适配markdown语法，可以对md格式的文件使用"
    )