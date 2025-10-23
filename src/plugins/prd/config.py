from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    block: bool = True
    priority: int = 15

    data_filename: str = "prd.json"

    # 图片生成相关配置
    enable_image_output: bool = True  # 是否启用图片输出功能
    image_output_dir: str = "data/pictures"  # 图片输出目录
    custom_image_path: str = "/home/cityTS/maomao-bot/napcat/app/data/prd_images"  # 自定义图片保存路径，为空则使用默认路径
    image_width: int = 1200  # 图片宽度
    image_height: int = 800  # 图片高度
    single_card_width: int = 800  # 单个需求卡片宽度
    single_card_height: int = 600  # 单个需求卡片高度

    # 分页相关配置
    max_requirements_per_page: int = 12  # 每页最大需求数量 - 减少每页数量以生成更多页面
    max_image_height: int = 4000  # 单张图片最大高度（像素）- 降低高度以生成更多页面
    enable_pagination: bool = True  # 是否启用分页功能

    # 缓存相关配置
    enable_cache: bool = True  # 是否启用图片缓存功能
    cache_dir: str = "cache"  # 缓存子目录名
    cache_expire_days: int = 7  # 缓存过期天数

    default_msg: str = (
        "[prd]命令使用详细\n"
        "[例子]:\n"
        "/prd ls (列出未完成的需求)\n"
        "/prd ok (列出已完成的需求)\n"
        "/prd add 需求 (添加需求)\n"
        "/prd md 编号 修改后的内容 (修改需求)\n"
        "/prd rm 编号 (删除需求)\n"
        "/prd x 编号 (更改需求完成状态True-False)\n"
        "/prd 执行人名字 xxx 编号 (给需求分配指定执行人)\n"
        "/prd img 编号 (生成单个需求图片)\n"
        "/prd img all (生成未完成的需求图片，支持分页显示)\n"
        "/prd img ok (生成已经完成的需求图片，支持分页显示)"
    )
