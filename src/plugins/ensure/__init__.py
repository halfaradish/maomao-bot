"""
nonebot项目启动时会立刻加载src/plugins内的插件
为确保谛听项目的api服务能在项目启动时便被加载
即设置ensure插件导入需要在启动时加载的服务
"""
from ...api import app