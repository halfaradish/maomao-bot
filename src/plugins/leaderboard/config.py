from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    help_msg: str = (
        "[过题积分榜]\n"
        "[参数]\n"
        "现役、退役、预备役"
    )
    # https://acm.gxu.edu.cn/gxuicpc/scores/all
    qingluan_scores_data_base_url: str = "http://127.0.0.1:8090/scores/all"

    timeout: float = 3.0
    
    # 图片生成配置
    image_width: int = 1000  # 增加宽度以容纳卡片式布局
    image_height: int = 800  # 增加高度以容纳更多卡片
    max_ranks: int = 10
    theme: str = "card"  # card, modern, classic, neon, dark