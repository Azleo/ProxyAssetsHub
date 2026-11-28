# tests/test_formatters.py

# 测试对象：三个规则 formatter 的"输出契约"
#
# 契约：每个 formatter 返回一个列表，每项描述一个要写出的文件：
#   {"dir", "filename", "content", "header", "comment"}
#
# 输入统一是两栏结构（类型 / 值）。
# 类型改名、是否追加参数（例如 no-resolve）都由各 formatter 自己决定。
#
# 运行方式（在项目根目录）：
#   python -m unittest discover -s tests -v

import unittest

from core.rule import (
    formatter_rule_clash,
    formatter_rule_loon,
    formatter_rule_quantumultx,
)
from core.rule.processor_rule import Rule

# 测试数据用处理器定义的两栏结构，和真实链路保持一致
RULES = [
    Rule("DOMAIN", "a.com"),
    Rule("DOMAIN-SUFFIX", "b.com"),
    Rule("IP-CIDR", "10.0.0.0/8"),
]

REQUIRED_KEYS = {"dir", "filename", "content", "header", "comment"}


class ContractMixin:
    def assertContract(self, item):
        self.assertTrue(REQUIRED_KEYS.issubset(item.keys()), item)
        self.assertIsInstance(item["filename"], str)
        self.assertIsInstance(item["content"], list)


class TestQuantumultX(ContractMixin, unittest.TestCase):
    def setUp(self):
        self.out = formatter_rule_quantumultx.format_rules(
            RULES, "Test", policy="Test"
        )

    def test_single_file(self):
        self.assertEqual(len(self.out), 1)

    def test_filename_and_dir(self):
        self.assertEqual(self.out[0]["filename"], "Test.list")
        self.assertEqual(self.out[0]["dir"], "QuantumultX")

    def test_contract(self):
        self.assertContract(self.out[0])

    def test_rule_lines_carry_policy(self):
        self.assertIn("HOST,a.com,Test", self.out[0]["content"])


class TestClash(ContractMixin, unittest.TestCase):
    def setUp(self):
        self.out = formatter_rule_clash.format_rules(RULES, "Test")

    def test_three_files(self):
        self.assertEqual(len(self.out), 3)

    def test_filenames(self):
        names = [item["filename"] for item in self.out]
        self.assertEqual(
            names,
            ["Test_Domain.yaml", "Test_IP.yaml", "Test_Classical.yaml"],
        )

    def test_dir(self):
        for item in self.out:
            self.assertEqual(item["dir"], "Clash")

    def test_contract(self):
        for item in self.out:
            self.assertContract(item)

    def test_content_is_yaml_list_item(self):
        domain = self.out[0]["content"]
        self.assertTrue(any(line.startswith("  - DOMAIN") for line in domain))


class TestClashPassthrough(unittest.TestCase):
    """占位实现：类型和值原样输出，不做映射、不追加参数。"""

    def test_all_files_start_with_payload(self):
        out = formatter_rule_clash.format_rules(RULES, "Test")
        for item in out:
            self.assertEqual(item["content"][0], "payload:")

    def test_no_resolve_is_not_added(self):
        out = formatter_rule_clash.format_rules(
            [Rule("IP-CIDR", "10.0.0.0/8")], "Test"
        )
        ip_lines = "\n".join(out[1]["content"])
        self.assertIn("  - IP-CIDR,10.0.0.0/8", ip_lines)
        self.assertNotIn("no-resolve", ip_lines)

    def test_unknown_type_goes_to_classical(self):
        out = formatter_rule_clash.format_rules(
            [Rule("PROCESS-NAME", "Telegram")], "Test"
        )
        classical = "\n".join(out[2]["content"])
        self.assertIn("  - PROCESS-NAME,Telegram", classical)

    def test_user_agent_is_dropped(self):
        """Clash 不支持 USER-AGENT，不该写进产物。"""
        out = formatter_rule_clash.format_rules(
            [Rule("USER-AGENT", "Telegram*"), Rule("DOMAIN", "a.com")], "Test"
        )
        joined = "\n".join(line for item in out for line in item["content"])
        self.assertNotIn("USER-AGENT", joined)
        # 被跳过的那条不计入条数
        self.assertEqual(sum(item["rule_count"] for item in out), 1)

    def test_rule_count_excludes_payload_line(self):
        """payload: 是文件结构，不能算进规则条数。"""
        out = formatter_rule_clash.format_rules(RULES, "Test")
        self.assertEqual(out[0]["rule_count"], 2)  # Domain：两条域名规则
        self.assertEqual(out[1]["rule_count"], 1)  # IP：一条 IP 规则
        self.assertEqual(out[2]["rule_count"], 0)  # Classical：空


class TestClashWildcard(unittest.TestCase):
    """通配符规则必须用 Clash 原生的 DOMAIN-WILDCARD，不能退化成 DOMAIN-SUFFIX。"""

    def test_wildcard_keeps_its_type(self):
        out = formatter_rule_clash.format_rules(
            [Rule("DOMAIN-WILDCARD", "scontent-*.xx.fbcdn.net")], "Test"
        )
        domain = "\n".join(out[0]["content"])
        self.assertIn("DOMAIN-WILDCARD,scontent-*.xx.fbcdn.net", domain)
        self.assertNotIn("DOMAIN-SUFFIX,scontent-*", domain)


class TestLoon(ContractMixin, unittest.TestCase):
    def setUp(self):
        self.out = formatter_rule_loon.format_rules(RULES, "Test")

    def test_single_file(self):
        self.assertEqual(len(self.out), 1)

    def test_filename_and_dir(self):
        self.assertEqual(self.out[0]["filename"], "Test.list")
        self.assertEqual(self.out[0]["dir"], "Loon")

    def test_contract(self):
        self.assertContract(self.out[0])

    def test_rule_line_is_type_and_value(self):
        self.assertIn("DOMAIN-SUFFIX,b.com", self.out[0]["content"])


if __name__ == "__main__":
    unittest.main()
