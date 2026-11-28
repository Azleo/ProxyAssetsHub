# tests/test_rewrite.py

# 测试对象：core/rewrite/ 下的处理器和两个翻译器
#
# 重写阶段目前是**占位实现**：
#   - 处理器只去掉空行，其余原样保留，不做任何语法解析
#   - 翻译器把拿到的行原样写进产物，不加任何软件专属的处理
#
# 既然内容是空的，这里测什么？测"外围"——因为这些外围才是真正需要
# 和 rule 阶段保持一致的东西：
#   1. 统计字段同一套口径（日志模块才能用同一套模板渲染）
#   2. 输出契约同一套结构（manager / writer 不需要区分是哪个阶段）
#   3. 文件名、扩展名、注释符这些元数据正确
#
# 将来真正实现重写语法时，这些用例不用动，只需在它们旁边补新的。
#
# 运行方式（在项目根目录）：
#   python -m unittest discover -s tests -v

import unittest

from core.rewrite import formatter_rewrite_loon, formatter_rewrite_quantumultx
from core.rewrite.processor_rewrite import process_rewrites

# 模拟 QX 能直接用的重写规则
RULES = [
    "^https://a.com/ads url reject",
    "^https://b.com/track url reject",
]

# 处理器返回的统计里必须有这几个字段，日志模块按名字取
REQUIRED_STATS = ("source", "skip", "drop", "total")

# 翻译器返回的文件描述必须有这几个字段
REQUIRED_KEYS = {"dir", "filename", "content", "rule_count", "header", "comment"}


def make_stats(source=0, skip=0, total=0):
    """构造一份处理器统计，字段和真实处理器保持一致。"""
    return {
        "source": source,
        "skip": skip,
        "drop": 0,
        "drop_detail": {},
        "drop_samples": {},
        "filtered": 0,
        "dup_src": 0,
        "dup_vip": 0,
        "vip": 0,
        "total": total,
    }


class TestProcessor(unittest.TestCase):
    """处理器：只去空行，其余原样。"""

    def test_blank_lines_are_skipped(self):
        """空行不是规则，不该进产物，也不该被算成丢弃。"""
        raw = ["^https://a.com url reject", "", "   ", "^https://b.com url reject"]

        result, stats = process_rewrites({}, raw)

        self.assertEqual(len(result), 2)
        self.assertEqual(stats["skip"], 2)
        self.assertEqual(stats["drop"], 0, "空行是跳过，不是丢弃")

    def test_leading_trailing_space_is_trimmed(self):
        """首尾空白去掉，中间的不能动——重写规则的语法靠中间的空格分隔。"""
        result, _ = process_rewrites({}, ["  ^https://a.com url reject  "])

        self.assertEqual(result, ["^https://a.com url reject"])

    def test_rule_content_is_untouched(self):
        """占位实现不做任何转换：给什么原样还什么。"""
        result, _ = process_rewrites({}, RULES)

        self.assertEqual(result, RULES)

    def test_stats_have_rule_stage_fields(self):
        """统计字段和 rule 阶段同一套口径，否则日志会显示"输出 0"。"""
        _, stats = process_rewrites({}, RULES)

        for key in REQUIRED_STATS:
            self.assertIn(key, stats)

    def test_empty_input_is_allowed(self):
        """一个源都没内容时不能崩，返回空结果和零统计。"""
        result, stats = process_rewrites({}, [])

        self.assertEqual(result, [])
        self.assertEqual(stats["source"], 0)
        self.assertEqual(stats["total"], 0)


class TestQuantumultX(unittest.TestCase):
    """QX 翻译器：一个 .conf 文件，内容是原始行。"""

    def setUp(self):
        self.out = formatter_rewrite_quantumultx.format_rules(
            RULES, "Test", header_lines=["来自配置的头部"]
        )

    def test_single_file_with_conf_extension(self):
        self.assertEqual(len(self.out), 1)
        self.assertEqual(self.out[0]["filename"], "Test.conf")

    def test_contract(self):
        """字段一个都不能少，manager / writer 按名字取值。"""
        self.assertTrue(REQUIRED_KEYS.issubset(self.out[0].keys()))

    def test_rules_are_passed_through(self):
        """占位实现：规则行原样进产物，不做语法解析。"""
        for rule in RULES:
            self.assertIn(rule, self.out[0]["content"])

    def test_header_lines_come_first(self):
        """自定义头部在最前面，且带注释符号。"""
        self.assertEqual(self.out[0]["content"][0], "# 来自配置的头部")

    def test_rule_count_excludes_header(self):
        """条数只数规则，不把头部算进去。"""
        self.assertEqual(self.out[0]["rule_count"], len(RULES))


class TestLoon(unittest.TestCase):
    """Loon 翻译器：一个 .plugin 文件。"""

    def setUp(self):
        self.out = formatter_rewrite_loon.format_rules(RULES, "Test")

    def test_single_file_with_plugin_extension(self):
        """Loon 的插件文件用 .plugin 扩展名，和 QX 的 .conf 区分开。"""
        self.assertEqual(len(self.out), 1)
        self.assertEqual(self.out[0]["filename"], "Test.plugin")

    def test_contract(self):
        self.assertTrue(REQUIRED_KEYS.issubset(self.out[0].keys()))

    def test_rules_are_passed_through(self):
        for rule in RULES:
            self.assertIn(rule, self.out[0]["content"])


if __name__ == "__main__":
    unittest.main()
