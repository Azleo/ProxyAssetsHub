# tests/test_loader.py

# 测试对象：core/loader.py
#
# 重点验证两件事：
#   1. loader 是"纯"的：只返回 (配置列表, 问题列表)，不打印任何东西
#   2. 各种配置错误都以"问题记录"的形式返回，而不是直接报错或崩溃
#
# 运行方式（在项目根目录）：
#   python -m unittest discover -s tests -v

import io
import os
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout

from core.loader import load_all_configs

VALID_CONFIG = """name: '测试规则集'
enabled: true
formats:
  - 'quantumultx'
sources:
  - 'https://example.com/a.list'
"""


class LoaderTestBase(unittest.TestCase):
    """在临时目录里搭一个最小的 configs/rule 结构，并把工作目录切过去。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        (self.root / "configs" / "rule").mkdir(parents=True)

        self._old_cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    def write(self, name: str, content: str):
        path = self.root / "configs" / "rule" / name
        path.write_text(content, encoding="utf-8")
        return path

    def load(self):
        """调用加载器，同时捕获 stdout，用来断言"什么都没打印"。"""
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            configs, problems = load_all_configs("rule")
        return configs, problems, buffer.getvalue()


class TestPurity(LoaderTestBase):
    """loader 不应该产生任何屏幕输出。"""

    def test_no_output_on_success(self):
        self.write("a.yaml", VALID_CONFIG)
        _, _, printed = self.load()
        self.assertEqual(printed, "")

    def test_no_output_on_error(self):
        self.write("bad.yaml", "name: [\n  broken\n")
        _, _, printed = self.load()
        self.assertEqual(printed, "")


class TestValidConfig(LoaderTestBase):
    def test_one_config_loaded(self):
        self.write("a.yaml", VALID_CONFIG)
        configs, _, _ = self.load()

        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0]["name"], "测试规则集")

    def test_formats_data_built(self):
        self.write("a.yaml", VALID_CONFIG)
        configs, _, _ = self.load()

        formats = configs[0]["formats_data"]
        self.assertIn("quantumultx", formats)
        # 没写 policy 时跟随 collection
        self.assertEqual(formats["quantumultx"]["policy"], "a")

    def test_collection_defaults_to_filename(self):
        self.write("a.yaml", VALID_CONFIG)
        configs, _, _ = self.load()

        # 没写 collection 就用配置文件名（去掉 .yaml）
        self.assertEqual(configs[0]["collection"], "a")
        self.assertEqual(configs[0]["policy"], "a")

    def test_policy_overrides_collection(self):
        content = VALID_CONFIG.replace(
            "name: '测试规则集'",
            "name: '测试规则集'\ncollection: 'Custom'\npolicy: 'Proxy'",
        )
        self.write("a.yaml", content)
        configs, _, _ = self.load()

        self.assertEqual(configs[0]["collection"], "Custom")
        self.assertEqual(configs[0]["formats_data"]["quantumultx"]["policy"], "Proxy")

    def test_no_error_problems(self):
        self.write("a.yaml", VALID_CONFIG)
        _, problems, _ = self.load()
        self.assertEqual([p for p in problems if p["level"] == "error"], [])


class TestDefaultsLoading(LoaderTestBase):
    """
    通用配置（configs/defaults_<阶段>.yaml）本身的错误处理。

    这份文件是"所有配置的默认值"，写错了会影响整批任务，
    所以它的异常必须被抓住并报出来，而不是崩掉或者静默忽略。
    """

    def write_defaults(self, content):
        path = self.root / "configs" / "defaults_rule.yaml"
        path.write_text(content, encoding="utf-8")

    def test_broken_yaml_reports_error(self):
        self.write("a.yaml", VALID_CONFIG)
        self.write_defaults("formats: [\n")

        _, problems, _ = self.load()

        self.assertTrue(any(p["code"] == "YAML_ERR" for p in problems))

    def test_not_a_dict_reports_error(self):
        self.write("a.yaml", VALID_CONFIG)
        self.write_defaults("- a\n- b\n")

        _, problems, _ = self.load()

        self.assertTrue(any(p["code"] == "DEFAULTS_NOT_DICT" for p in problems))

    def test_unknown_key_is_warned(self):
        """写了不认识的字段要告警：否则写错了毫无反应。"""
        self.write("a.yaml", VALID_CONFIG)
        self.write_defaults("formats: ['quantumultx']\nsources: []\n")

        _, problems, _ = self.load()

        ignored = [p for p in problems if p["code"] == "DEFAULTS_KEY_IGNORED"]
        self.assertEqual(len(ignored), 1)
        self.assertEqual(ignored[0]["params"]["key"], "sources")

    def test_empty_file_is_not_an_error(self):
        """空文件表示"没有默认值"，是正常状态。"""
        self.write("a.yaml", VALID_CONFIG)
        self.write_defaults("")

        configs, problems, _ = self.load()

        self.assertEqual(len(configs), 1)
        self.assertFalse(any(p["level"] == "error" for p in problems))

    def test_defaults_can_disable_everything(self):
        """defaults 里写 enabled: false 可以一键全关，显式写 true 的配置不受影响。"""
        self.write("a.yaml", VALID_CONFIG.replace("enabled: true\n", ""))
        self.write("b.yaml", VALID_CONFIG.replace("name: '测试规则集'", "name: '显式启用'"))
        self.write_defaults("enabled: false\n")

        configs, _, _ = self.load()

        self.assertEqual([c["name"] for c in configs], ["显式启用"])


class TestProjectRoot(LoaderTestBase):
    """配置目录靠显式传入的项目根定位，不依赖当前工作目录。"""

    def test_explicit_project_root_works_from_elsewhere(self):
        self.write("a.yaml", VALID_CONFIG)

        elsewhere = tempfile.mkdtemp()
        old_cwd = os.getcwd()
        os.chdir(elsewhere)
        try:
            configs, _ = load_all_configs("rule", project_root=str(self.root))
        finally:
            os.chdir(old_cwd)

        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0]["name"], "测试规则集")

    def test_missing_dir_is_error_not_silent(self):
        """配置目录不存在时一个任务都跑不了，必须报错误，不能静默通过。"""
        configs, problems = load_all_configs(
            "no-such-phase", project_root=str(self.root)
        )

        self.assertEqual(configs, [])
        self.assertTrue(any(p["level"] == "error" for p in problems))
        self.assertTrue(any(p["code"] == "DIR_NOT_FOUND" for p in problems))


class TestBadConfigIsolated(LoaderTestBase):
    """一份配置写错，不能影响其它配置，更不该让程序崩溃。"""

    def test_root_is_list(self):
        """根节点不是字典时跳过这个文件，其它配置照常加载。"""
        self.write("bad.yaml", "- a\n- b\n")
        self.write("good.yaml", VALID_CONFIG)

        configs, problems, _ = self.load()

        self.assertEqual(len(configs), 1)
        self.assertTrue(any(p["code"] == "CONFIG_NOT_DICT" for p in problems))

    def test_formats_written_as_string(self):
        """formats 少写方括号时会被拆成单个字符，必须拦住。"""
        self.write(
            "bad.yaml",
            "name: 'X'\nformats: 'clash'\nsources:\n  - 'https://x/a.list'\n",
        )

        configs, problems, _ = self.load()

        self.assertEqual(configs, [])
        self.assertTrue(any(p["code"] == "FORMATS_NOT_LIST" for p in problems))

    def test_custom_headers_not_dict(self):
        cfg = VALID_CONFIG + "custom_headers: 'abc'\n"
        self.write("bad.yaml", cfg)

        configs, problems, _ = self.load()

        self.assertEqual(configs, [])
        self.assertTrue(
            any(p["code"] == "CUSTOM_HEADERS_NOT_DICT" for p in problems)
        )

    def test_filters_not_dict(self):
        cfg = VALID_CONFIG + "filters: []\n"
        self.write("bad.yaml", cfg)

        configs, problems, _ = self.load()

        self.assertEqual(configs, [])
        self.assertTrue(any(p["code"] == "FILTERS_NOT_DICT" for p in problems))

    def test_filter_item_not_list(self):
        cfg = VALID_CONFIG + "filters:\n  exclude_keywords: 'ads'\n"
        self.write("bad.yaml", cfg)

        configs, problems, _ = self.load()

        self.assertEqual(configs, [])
        self.assertTrue(any(p["code"] == "FILTER_ITEM_NOT_LIST" for p in problems))

    def test_collection_not_string(self):
        cfg = VALID_CONFIG + "collection: 123\n"
        self.write("bad.yaml", cfg)

        configs, problems, _ = self.load()

        self.assertEqual(configs, [])
        self.assertTrue(any(p["code"] == "IDENT_NOT_STR" for p in problems))

    def test_bad_one_does_not_block_good_one(self):
        """坏配置排在好配置前面，也不影响好配置。"""
        self.write("a_bad.yaml", "just a string\n")
        self.write("b_good.yaml", VALID_CONFIG)

        configs, _, _ = self.load()

        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0]["name"], "测试规则集")


class TestOrder(LoaderTestBase):
    """配置的加载顺序必须固定，不依赖文件系统的遍历顺序。"""

    def test_sorted_by_path(self):
        for name in ["c.yaml", "a.yaml", "b.yaml"]:
            self.write(name, VALID_CONFIG)

        configs, _, _ = self.load()
        names = [c["__filename__"] for c in configs]

        self.assertEqual(names, ["a.yaml", "b.yaml", "c.yaml"])


class TestConfigErrors(LoaderTestBase):
    """各种写错的配置都应该变成"问题记录"，而不是异常。"""

    def test_broken_yaml(self):
        self.write("bad.yaml", "name: [\n  broken\n")
        configs, problems, _ = self.load()

        self.assertEqual(configs, [])
        self.assertTrue(any(p["code"] == "YAML_ERR" for p in problems))

    def test_empty_config(self):
        self.write("empty.yaml", "")
        configs, problems, _ = self.load()

        self.assertEqual(configs, [])
        self.assertTrue(any(p["code"] == "CONFIG_EMPTY" for p in problems))

    def test_empty_sources(self):
        self.write("a.yaml", "name: 'X'\nenabled: true\nformats: ['quantumultx']\nsources: []\n")
        configs, problems, _ = self.load()

        self.assertEqual(configs, [])
        self.assertTrue(any(p["code"] == "SOURCES_EMPTY" for p in problems))

    def test_disabled_config_is_skipped(self):
        self.write("a.yaml", VALID_CONFIG.replace("enabled: true", "enabled: false"))
        configs, problems, _ = self.load()

        self.assertEqual(configs, [])
        # 禁用不是错误，只是调试信息
        self.assertTrue(any(p["code"] == "CONFIG_DISABLED"
                            and p["level"] == "debug" for p in problems))

    def test_missing_enabled_means_enabled(self):
        """不写 enabled 就是启用，不再依赖 defaults 里有 enabled: true。"""
        self.write("a.yaml", VALID_CONFIG.replace("enabled: true\n", ""))
        configs, problems, _ = self.load()

        self.assertEqual(len(configs), 1)
        self.assertFalse(any(p["code"] == "CONFIG_DISABLED" for p in problems))

    def test_enabled_string_is_an_error(self):
        """写成字符串（例如带了引号）要报错，不能静默当成禁用。"""
        self.write("a.yaml", VALID_CONFIG.replace("enabled: true", 'enabled: "false"'))
        configs, problems, _ = self.load()

        self.assertEqual(configs, [])
        self.assertTrue(any(p["code"] == "ENABLED_TYPE_ERR"
                            and p["level"] == "error" for p in problems))

    def test_enabled_number_is_an_error(self):
        self.write("a.yaml", VALID_CONFIG.replace("enabled: true", "enabled: 0"))
        configs, problems, _ = self.load()

        self.assertEqual(configs, [])
        self.assertTrue(any(p["code"] == "ENABLED_UNKNOWN"
                            and p["level"] == "error" for p in problems))


class TestMissingDir(LoaderTestBase):
    """阶段目录不存在时返回空列表 + 一条 debug 问题，不崩溃。"""

    def test_missing_rule_dir(self):
        (self.root / "configs" / "rule").rmdir()

        configs, problems, printed = self.load()

        self.assertEqual(configs, [])
        self.assertEqual(printed, "")
        self.assertTrue(any(p["code"] == "DIR_NOT_FOUND" for p in problems))


if __name__ == "__main__":
    unittest.main()