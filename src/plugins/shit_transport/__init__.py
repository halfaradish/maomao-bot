from nonebot import get_plugin_config

from .config import Config
from .transport import __plugin_meta__
from . import permissions  # noqa: F401

config = get_plugin_config(Config)

