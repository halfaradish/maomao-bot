from pydantic import BaseModel


class Config(BaseModel):
    # 响应优先级
    priority: int = 10
    # 是否阻塞
    block: bool = True
    # Chromium 空闲多少秒后自动关闭；<=0 表示常驻不关闭
    browser_idle_timeout: int = 300
    # 截图视口宽度（与模板 max-width 匹配）
    render_width: int = 900
