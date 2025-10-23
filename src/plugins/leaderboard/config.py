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