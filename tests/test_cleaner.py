# tests/test_cleaner.py

# 测试对象：core/rule/processor_rule.py 的清洗部分
#
# 清洗器把各种来源的规则解析成项目内部统一的两栏结构：
#     (类型, 值)
# 原始数据的第三段及以后一律丢弃。
#
# 这里的用例锁定两件事：
#   1. 各种来源格式能被正确识别成标准类型
#   2. 值按类型规范化（域名小写去尾点、ASN 去前缀、国家代码大写）
#
# 运行方式（在项目根目录）：
#   python -m unittest discover -s tests -v

import unittest

from core.rule.processor_rule import (
    EMPTY_VALUE,
    _parse_line,
    clean_rule_line,
    process_rules,
)


class TestCleanBasic(unittest.TestCase):
    """基础：类型别名映射与常见格式转换。"""

    def test_host_alias_maps_to_domain(self):
        """HOST 是 QX 的叫法，内部统一成 DOMAIN。"""
        self.assertEqual(clean_rule_line("HOST,example.com"), ("DOMAIN", "example.com"))

    def test_host_suffix_alias(self):
        self.assertEqual(
            clean_rule_line("HOST-SUFFIX,example.com"), ("DOMAIN-SUFFIX", "example.com")
        )

    def test_full_keyword_maps_to_domain(self):
        """有些规则集用 FULL 表示精确匹配。"""
        self.assertEqual(
            clean_rule_line("FULL,a.example.com"), ("DOMAIN", "a.example.com")
        )

    def test_ipv6_alias(self):
        self.assertEqual(
            clean_rule_line("IP6-CIDR,2001:db8::/32"), ("IP-CIDR6", "2001:db8::/32")
        )

    def test_standard_line_passes_through(self):
        self.assertEqual(
            clean_rule_line("IP-CIDR,10.0.0.0/8"), ("IP-CIDR", "10.0.0.0/8")
        )


class TestCleanDropTail(unittest.TestCase):
    """第三段及以后一律丢弃：策略名不用，参数由客户端按类型决定。"""

    def test_policy_name_is_dropped(self):
        """源里的策略名不该跟着走，它由规则集自己的配置决定。"""
        self.assertEqual(
            clean_rule_line("DOMAIN,ai.google.dev,GoogleAI"),
            ("DOMAIN", "ai.google.dev"),
        )

    def test_param_is_dropped(self):
        self.assertEqual(
            clean_rule_line("IP-CIDR,10.0.0.0/8,no-resolve"),
            ("IP-CIDR", "10.0.0.0/8"),
        )

    def test_policy_and_param_are_both_dropped(self):
        """策略名和参数混写的情况，一样丢干净。"""
        self.assertEqual(
            clean_rule_line("IP-CIDR,10.0.0.0/8,Proxy,no-resolve"),
            ("IP-CIDR", "10.0.0.0/8"),
        )

    def test_same_rule_with_and_without_tail_is_identical(self):
        """带不带尾巴，清洗完是同一条，这样去重才准。"""
        self.assertEqual(
            clean_rule_line("DOMAIN,a.com,GoogleAI"),
            clean_rule_line("DOMAIN,a.com"),
        )


class TestCleanCase(unittest.TestCase):
    """值按类型规范化。"""

    def test_domain_is_lowercased(self):
        self.assertEqual(
            clean_rule_line("DOMAIN-SUFFIX,Example.COM"),
            ("DOMAIN-SUFFIX", "example.com"),
        )

    def test_trailing_dot_is_removed(self):
        """FQDN 末尾的点没有意义，去掉后才不会和同一条重复。"""
        self.assertEqual(
            clean_rule_line("DOMAIN,example.com."), ("DOMAIN", "example.com")
        )

    def test_keyword_keeps_trailing_dot(self):
        """DOMAIN-KEYWORD 是子串匹配，点属于关键词本身，不能当 FQDN 结束符删掉。"""
        self.assertEqual(
            clean_rule_line("HOST-KEYWORD,.zooplus."), ("DOMAIN-KEYWORD", ".zooplus.")
        )

    def test_ipv6_is_lowercased(self):
        self.assertEqual(
            clean_rule_line("IP-CIDR6,2001:DB8::/32"), ("IP-CIDR6", "2001:db8::/32")
        )

    def test_user_agent_keeps_case(self):
        """UA 字符串大小写有含义，不能动。"""
        self.assertEqual(
            clean_rule_line("USER-AGENT,MyApp/1.0"), ("USER-AGENT", "MyApp/1.0")
        )

    def test_process_name_keeps_case(self):
        self.assertEqual(
            clean_rule_line("PROCESS-NAME,Telegram"), ("PROCESS-NAME", "Telegram")
        )

    def test_geoip_is_uppercased(self):
        """国家代码统一大写，各家都写 CN、US。"""
        self.assertEqual(clean_rule_line("GEOIP,CN"), ("GEOIP", "CN"))
        self.assertEqual(clean_rule_line("GEOIP,cn"), ("GEOIP", "CN"))

    def test_ip_asn_strips_as_prefix(self):
        """AS 前缀可写可不写，内部统一成纯数字。"""
        self.assertEqual(clean_rule_line("IP-ASN,AS13335"), ("IP-ASN", "13335"))
        self.assertEqual(clean_rule_line("IP-ASN,as13335"), ("IP-ASN", "13335"))
        self.assertEqual(clean_rule_line("IP-ASN,13335"), ("IP-ASN", "13335"))


class TestCleanIpValidation(unittest.TestCase):
    """IP 判定改用标准库校验：像 IP 但实际不是的，一律不认。"""

    def test_two_ips_in_one_line_is_not_hosts(self):
        """一行两个 IP 不是任何正常格式，不能当成 hosts 生成域名规则。"""
        self.assertIsNone(clean_rule_line("10.0.0.1 10.0.0.2"))

    def test_colon_text_is_not_ipv6(self):
        """光有冒号和十六进制字符不等于 IPv6。"""
        self.assertIsNone(clean_rule_line("abc:def"))

    def test_numeric_dotted_line_is_not_a_domain(self):
        """999.999.999.999 只可能是写错的 IP，不能兜底成域名规则。"""
        self.assertIsNone(clean_rule_line("999.999.999.999"))

    def test_two_cidr_in_one_line_is_rejected(self):
        """两段 CIDR 用空格隔开，拼成一条规则客户端也解析不了。"""
        self.assertIsNone(clean_rule_line("10.0.0.0/8 192.168.0.0/16"))

    def test_ipv6_cidr_without_type(self):
        self.assertEqual(
            clean_rule_line("2001:db8::/32"), ("IP-CIDR6", "2001:db8::/32")
        )

    def test_single_ip_becomes_ip_rule(self):
        self.assertEqual(clean_rule_line("10.0.0.1"), ("IP-CIDR", "10.0.0.1"))


class TestCleanYamlPrefix(unittest.TestCase):
    """从 YAML 格式的源里抓下来的行，会带列表前缀 "- "。"""

    def test_dash_prefix_is_stripped(self):
        """Clash 的规则文件就是 YAML 列表，抓下来是 "  - DOMAIN,x"。"""
        self.assertEqual(
            clean_rule_line("- DOMAIN,a.com"), ("DOMAIN", "a.com")
        )

    def test_dash_prefix_with_extra_spaces(self):
        self.assertEqual(
            clean_rule_line("  - DOMAIN-SUFFIX,b.com  "), ("DOMAIN-SUFFIX", "b.com")
        )


class TestCleanEmptyValue(unittest.TestCase):
    """有类型但没值，属于"空值"，要和"认不出格式"区分开。"""

    def test_type_without_value_is_empty(self):
        rule, status = _parse_line("DOMAIN,")

        self.assertIsNone(rule)
        self.assertEqual(status, EMPTY_VALUE)

    def test_empty_value_counts_as_drop_not_skip(self):
        """它是一条规则（有类型），只是写坏了，所以算丢弃而不是跳过。"""
        _, stats = process_rules({"name": "x", "filters": {}}, ["DOMAIN,", "# 注释"])

        self.assertEqual(stats["drop"], 1)
        self.assertEqual(stats["skip"], 1)


class TestCleanAdBlock(unittest.TestCase):
    """AdBlock 风格的行要能被识别成域名规则。"""

    def test_double_pipe_suffix(self):
        self.assertEqual(
            clean_rule_line("||ads.example.com^"),
            ("DOMAIN-SUFFIX", "ads.example.com"),
        )

    def test_dot_prefix_suffix(self):
        self.assertEqual(
            clean_rule_line(".tracker.example.com"),
            ("DOMAIN-SUFFIX", "tracker.example.com"),
        )

    def test_wildcard_prefix(self):
        self.assertEqual(
            clean_rule_line("*.cdn.example.com"),
            ("DOMAIN-SUFFIX", "cdn.example.com"),
        )

    def test_inline_comment_is_stripped(self):
        self.assertEqual(
            clean_rule_line("DOMAIN,example.com # 这是注释"),
            ("DOMAIN", "example.com"),
        )


class TestCleanHosts(unittest.TestCase):
    """hosts 格式（IP + 域名）只保留域名。"""

    def test_hosts_line(self):
        self.assertEqual(
            clean_rule_line("127.0.0.1 example.com"), ("DOMAIN", "example.com")
        )

    def test_zero_ip_is_the_common_ads_style(self):
        """广告屏蔽常用 0.0.0.0 打头。"""
        self.assertEqual(
            clean_rule_line("0.0.0.0 ads.example.com"), ("DOMAIN", "ads.example.com")
        )

    def test_hosts_line_with_extra_spaces(self):
        self.assertEqual(
            clean_rule_line("  127.0.0.1   example.com  "), ("DOMAIN", "example.com")
        )

    def test_hosts_line_with_trailing_comment(self):
        self.assertEqual(
            clean_rule_line("127.0.0.1 example.com # 广告"),
            ("DOMAIN", "example.com"),
        )

    def test_bare_cidr(self):
        self.assertEqual(clean_rule_line("10.0.0.0/8"), ("IP-CIDR", "10.0.0.0/8"))

    def test_single_ip_is_still_ip_rule(self):
        """只有一段地址的，仍然是 IP 规则，不能误判成 hosts。"""
        self.assertEqual(clean_rule_line("10.0.0.1"), ("IP-CIDR", "10.0.0.1"))


class TestCleanReject(unittest.TestCase):
    """不该被接受的行必须返回 None（丢弃），而不是硬塞一条错规则。"""

    def test_empty_line(self):
        self.assertIsNone(clean_rule_line(""))

    def test_comment_only(self):
        self.assertIsNone(clean_rule_line("# 只是注释"))

    def test_adblock_element_rule(self):
        """## 开头的是 AdBlock 网页元素隐藏规则，不是分流规则。"""
        self.assertIsNone(clean_rule_line("##.ad-banner"))

    def test_unsupported_type(self):
        """DOMAIN-SET 需要外部文件引用，无法作为单条规则处理。"""
        self.assertIsNone(clean_rule_line("DOMAIN-SET,https://example.com/set.txt"))

    def test_unknown_type(self):
        """白名单之外的类型一律丢弃（靠日志计数报出，以后再做）。"""
        self.assertIsNone(clean_rule_line("SOMETHING-NEW,value"))

    def test_quoted_value_is_unwrapped(self):
        """YAML 里带引号的规则，引号要剥掉。"""
        self.assertEqual(
            clean_rule_line("'DOMAIN,example.com'"), ("DOMAIN", "example.com")
        )


if __name__ == "__main__":
    unittest.main()
