"""在隔离解释器中验证公共工具导入，不读取配置或连接外部服务。"""

from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[3]

FAKE_EXPORTS = """
import importlib
import importlib.abc
import importlib.util
from types import ModuleType

exports = {
    'get_icpc_db_connection': ('icpc_db_pool', 'get_icpc_db_connection'),
    'JsonUtils': ('json_utils', 'JsonUtils'),
    'CompressPic': ('compress_pics', 'CompressPic'),
    'SendForwardMsg': ('send_forward_msg', 'SendForwardMsg'),
    'utils': ('utils', None),
    'get_redis_connection': ('oj_redis_pool', 'get_redis_connection'),
    'TokenBucketLimiter': ('rate_limiter', 'TokenBucketLimiter'),
    'GroupRateLimiter': ('rate_limiter', 'GroupRateLimiter'),
    'AuthCheckResult': ('siqi_client', 'AuthCheckResult'),
    'SiqiAuthRequestError': ('siqi_client', 'SiqiAuthRequestError'),
    'siqi_client': ('siqi_client', 'siqi_client'),
    'current_env_tag': ('database', 'current_env_tag'),
    'ensure_tables': ('database', 'ensure_tables'),
    'get_session': ('database', 'get_session'),
}
loaded = []

class FakeServices(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith('src.common.'):
            name = fullname.rsplit('.', 1)[1]
            assert name in {entry[0] for entry in exports.values()}, fullname
            return importlib.util.spec_from_loader(fullname, self)

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        loaded.append(module.__name__)
        name = module.__name__.rsplit('.', 1)[1]
        for _, (module_name, attribute) in exports.items():
            if module_name == name and attribute is not None:
                setattr(module, attribute, object())

sys.meta_path.insert(0, FakeServices())
import src.common as common
assert loaded == [], loaded
"""


class CommonImportTests(unittest.TestCase):
    def assert_script(self, source):
        prefix = f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n"
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-c", prefix + textwrap.dedent(source)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_normal_email_import_needs_no_bot_or_service_dependencies(self):
        self.assert_script("""
            import importlib.abc

            class RejectServices(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname.split('.')[0] in {
                        'nonebot', 'sqlalchemy', 'redis', 'aiohttp', 'dotenv',
                        'cv2', 'PIL', 'httpx', 'pydantic',
                    } or fullname.startswith('src.config'):
                        raise AssertionError('Unexpected dependency: ' + fullname)

            sys.meta_path.insert(0, RejectServices())
            from src.common.email_sender import SMTPConfig, send_email
            assert callable(send_email)
            assert SMTPConfig().enabled is False
            assert {name for name in sys.modules if name.startswith('src.common.')} == {
                'src.common.email_sender'
            }
        """)

    def test_existing_public_exports_are_lazy_and_keep_identity(self):
        self.assert_script(FAKE_EXPORTS + """
assert common.__all__ == list(exports)
assert set(exports) <= set(dir(common))
assert loaded == []
from src.common import JsonUtils
assert loaded == ['src.common.json_utils']
assert JsonUtils is sys.modules['src.common.json_utils'].JsonUtils
for name, (module_name, attribute) in exports.items():
    namespace = {}
    exec('from src.common import ' + name, namespace)
    module = sys.modules['src.common.' + module_name]
    expected = getattr(module, attribute) if attribute is not None else module
    assert namespace[name] is expected, name
    assert getattr(common, name) is expected, name
assert len(loaded) == len(set(module_name for module_name, _ in exports.values()))
try:
    common.no_such_tool
except AttributeError:
    pass
else:
    raise AssertionError('Unknown attributes must raise AttributeError')
""")

    def test_utils_remains_a_submodule(self):
        self.assert_script(FAKE_EXPORTS + """
from src.common import utils
assert isinstance(utils, ModuleType)
assert utils is importlib.import_module('src.common.utils')
assert common.utils is utils
assert loaded == ['src.common.utils']
""")

    def test_siqi_singleton_export_first(self):
        self.assert_script(FAKE_EXPORTS + """
from src.common import siqi_client
module = importlib.import_module('src.common.siqi_client')
from src.common.siqi_client import siqi_client as direct_singleton
assert isinstance(module, ModuleType)
assert siqi_client is module.siqi_client is direct_singleton
assert common.siqi_client is siqi_client
assert loaded == ['src.common.siqi_client']
""")

    def test_siqi_other_export_first(self):
        self.assert_script(FAKE_EXPORTS + """
from src.common import AuthCheckResult, siqi_client, SiqiAuthRequestError
module = importlib.import_module('src.common.siqi_client')
assert AuthCheckResult is module.AuthCheckResult
assert SiqiAuthRequestError is module.SiqiAuthRequestError
assert siqi_client is module.siqi_client
assert loaded == ['src.common.siqi_client']
""")

    def test_siqi_submodule_first(self):
        self.assert_script(FAKE_EXPORTS + """
module = importlib.import_module('src.common.siqi_client')
from src.common import siqi_client, AuthCheckResult
from src.common.siqi_client import siqi_client as direct_singleton
assert isinstance(module, ModuleType)
assert siqi_client is module.siqi_client is direct_singleton
assert AuthCheckResult is module.AuthCheckResult
assert common.siqi_client is direct_singleton
assert loaded == ['src.common.siqi_client']
""")

    def test_auth_shutdown_hook_is_registered_when_client_is_imported(self):
        self.assert_script("""
            from types import ModuleType, SimpleNamespace
            import importlib

            hooks = []
            driver = SimpleNamespace(on_shutdown=lambda callback: hooks.append(callback))
            nonebot = ModuleType('nonebot')
            nonebot.get_driver = lambda: driver
            nonebot.logger = SimpleNamespace(info=lambda *args, **kwargs: None)
            sys.modules['nonebot'] = nonebot
            aiohttp = ModuleType('aiohttp')
            aiohttp.ClientSession = type('ClientSession', (), {})
            sys.modules['aiohttp'] = aiohttp
            config = ModuleType('src.config')
            config.SiqiAuthConfig = SimpleNamespace(
                HOST='unused.invalid', PORT=8001, APP_CODE='test', TIMEOUT=10, ENABLED=False,
            )
            sys.modules['src.config'] = config

            import src.common as common
            from src.common.email_sender import send_email
            assert hooks == []
            # 与现有 src.plugins.siqi_auth.plugin 的实际导入路径一致。
            from src.common.siqi_client import siqi_client, AuthCheckResult
            assert len(hooks) == 1
            assert hooks[0].__name__ == '_shutdown_siqi_client'
            assert common.siqi_client is siqi_client
            assert common.AuthCheckResult is AuthCheckResult
            assert importlib.import_module('src.common.siqi_client').siqi_client is siqi_client
            assert len(hooks) == 1
        """)


if __name__ == '__main__':
    unittest.main()
