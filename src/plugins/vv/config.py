from pydantic import BaseModel


class Config(BaseModel):
    """这就是VV 插件配置"""

    vv_min_ratio: float = 50.0  # 台词文本匹配度下限（0-100）
    vv_min_similarity: float = 0.5  # 人脸相似度下限（0-1，保证画面中是 VV 本人）
