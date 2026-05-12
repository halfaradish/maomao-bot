import unittest
import datetime
import os
import json
import threading


class MockJsonUtils:
    """Mock JsonUtils for testing"""
    _file_locks = {}
    _global_lock = threading.RLock()

    @classmethod
    def _get_file_lock(cls, file_path):
        with cls._global_lock:
            if file_path not in cls._file_locks:
                cls._file_locks[file_path] = threading.RLock()
            return cls._file_locks[file_path]

    @classmethod
    def __pre_built_file(cls, file, default=None):
        default = default or {}
        is_new = False
        if not os.path.exists(file):
            is_new = True
            dir_path = os.path.dirname(file)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
        if is_new:
            with open(file, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=4, ensure_ascii=False)
        else:
            with open(file, "r", encoding="utf-8") as f:
                content = json.load(f)
            change = False
            for key, value in default.items():
                if key not in content:
                    content[key] = value
                    change = True
            if change:
                with open(file, "w", encoding="utf-8") as f:
                    json.dump(content, f, indent=4, ensure_ascii=False)
        return is_new

    @classmethod
    def read(cls, filename, default=None):
        file_url = os.path.join(os.environ.get('DI_TING_DATA_DIR', '.'), filename)
        with cls._get_file_lock(file_url):
            is_new = cls.__pre_built_file(file_url, default or {})
            try:
                with open(file_url, "r", encoding="utf-8") as f:
                    content = json.load(f)
                return (content, is_new)
            except Exception:
                return (default, is_new)

    @classmethod
    def update(cls, filename, updates):
        file_url = os.path.join(os.environ.get('DI_TING_DATA_DIR', '.'), filename)
        with cls._get_file_lock(file_url):
            content, _ = cls.read(filename)
            if not isinstance(content, dict):
                return False
            content.update(updates)
            with open(file_url, "w", encoding="utf-8") as f:
                json.dump(content, f, indent=4, ensure_ascii=False)
            return True


def get_plugin_config(json_utils):
    data, _ = json_utils.read("fakemsg.json", {
        "person_users": [],
        "group_users": [],
        "daily_times_log": {}
    })
    if not isinstance(data, dict):
        return [], [], {}
    return (
        data.get("person_users", []),
        data.get("group_users", []),
        data.get('daily_times_log', {})
    )


def get_last_refresh_date(json_utils):
    data, _ = json_utils.read("fakemsg.json", {})
    return data.get("last_refresh_date", "")


def set_last_refresh_date(json_utils, date_str):
    return json_utils.update("fakemsg.json", updates={"last_refresh_date": date_str})


def refresh_daily_times_log(json_utils):
    try:
        print("[fakemsg] 开始执行每日额度刷新任务")
        today = datetime.date.today().strftime("%Y-%m-%d")
        success = json_utils.update("fakemsg.json", updates={"daily_times_log": {}, "last_refresh_date": today})
        if success:
            print(f"[fakemsg] 每日额度刷新成功，日期: {today}")
        else:
            print("[fakemsg] 每日额度刷新失败")
        return success
    except Exception as e:
        print(f"[fakemsg] 每日额度刷新发生异常: {e}")
        return False


def check_and_refresh_on_demand(json_utils):
    try:
        today = datetime.date.today().strftime("%Y-%m-%d")
        last_refresh = get_last_refresh_date(json_utils)
        if last_refresh != today:
            print(f"[fakemsg] 检测到日期变更，上次刷新日期: {last_refresh}，当前日期: {today}，需要执行刷新")
            return refresh_daily_times_log(json_utils)
        return True
    except Exception as e:
        print(f"[fakemsg] 按需检查刷新发生异常: {e}")
        return False


class TestFakemsgRefresh(unittest.TestCase):
    """测试伪消息每日刷新功能"""

    def setUp(self):
        self.test_data_dir = os.path.join(os.path.dirname(__file__), 'test_data')
        os.makedirs(self.test_data_dir, exist_ok=True)
        os.environ['DI_TING_DATA_DIR'] = self.test_data_dir
        self.test_file = os.path.join(self.test_data_dir, 'fakemsg.json')
        self.original_data = {
            "person_users": ["123456789"],
            "group_users": ["987654321"],
            "daily_times_log": {"2091842518": 5, "123456789": 3},
            "last_refresh_date": "2026-04-27"
        }
        with open(self.test_file, 'w', encoding='utf-8') as f:
            json.dump(self.original_data, f, indent=4)

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_get_last_refresh_date(self):
        date = get_last_refresh_date(MockJsonUtils)
        self.assertEqual(date, "2026-04-27")

    def test_set_last_refresh_date(self):
        result = set_last_refresh_date(MockJsonUtils, "2026-04-28")
        self.assertTrue(result)
        with open(self.test_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(data["last_refresh_date"], "2026-04-28")

    def test_refresh_daily_times_log(self):
        result = refresh_daily_times_log(MockJsonUtils)
        self.assertTrue(result)
        with open(self.test_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(data["daily_times_log"], {})
        today = datetime.date.today().strftime("%Y-%m-%d")
        self.assertEqual(data["last_refresh_date"], today)
        self.assertEqual(data["person_users"], ["123456789"])
        self.assertEqual(data["group_users"], ["987654321"])

    def test_check_and_refresh_on_demand_needs_refresh(self):
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        with open(self.test_file, 'w', encoding='utf-8') as f:
            json.dump({
                "person_users": [],
                "group_users": [],
                "daily_times_log": {"test_user": 5},
                "last_refresh_date": yesterday
            }, f)
        result = check_and_refresh_on_demand(MockJsonUtils)
        self.assertTrue(result)
        with open(self.test_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(data["daily_times_log"], {})
        today = datetime.date.today().strftime("%Y-%m-%d")
        self.assertEqual(data["last_refresh_date"], today)

    def test_check_and_refresh_on_demand_no_refresh(self):
        today = datetime.date.today().strftime("%Y-%m-%d")
        with open(self.test_file, 'w', encoding='utf-8') as f:
            json.dump({
                "person_users": [],
                "group_users": [],
                "daily_times_log": {"test_user": 3},
                "last_refresh_date": today
            }, f)
        result = check_and_refresh_on_demand(MockJsonUtils)
        self.assertTrue(result)
        with open(self.test_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(data["daily_times_log"], {"test_user": 3})
        self.assertEqual(data["last_refresh_date"], today)

    def test_check_and_refresh_no_last_refresh_date(self):
        with open(self.test_file, 'w', encoding='utf-8') as f:
            json.dump({
                "person_users": [],
                "group_users": [],
                "daily_times_log": {"test_user": 5}
            }, f)
        result = check_and_refresh_on_demand(MockJsonUtils)
        self.assertTrue(result)
        with open(self.test_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(data["daily_times_log"], {})
        today = datetime.date.today().strftime("%Y-%m-%d")
        self.assertEqual(data["last_refresh_date"], today)

    def test_get_plugin_config_default(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        person_users, group_users, daily_times_log = get_plugin_config(MockJsonUtils)
        self.assertEqual(person_users, [])
        self.assertEqual(group_users, [])
        self.assertEqual(daily_times_log, {})


if __name__ == '__main__':
    unittest.main()
