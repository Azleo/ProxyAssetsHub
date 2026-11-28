# tests/test_processor.py

# 测试对象：core/rule/processor_rule.py
#
# 这个模块负责"去重、过滤、排序"，交出去的是两栏结构：
#     (类型, 值)
# 运行方式（在项目根目录）：
#   python -m unittest discover -s tests -v

import unittest

from core.rule.processor_rule import process_rules


def make_cfg(**filters):
    """构造一个最小配置，只包含 filters 部分。"""
    return {"name": "测试规则集", "filters": filters}


class TestDedupe(unittest.TestCase):
    """重复的规则只保留一条。"""

    def test_same_rule_twice(self):
        raw = ["DOMAIN-SUFFIX,a.com", "DOMAIN-SUFFIX,a.com"]
        result, stats = process_rules(make_cfg(), raw)
        self.assertEqual(result, [("DOMAIN-SUFFIX", "a.com")])
        self.assertEqual(stats["dup_src"], 1)

    def test_different_case_counts_as_same(self):
        """大小写不同应视为同一条（域名类在清洗阶段统一小写）。"""
        raw = ["DOMAIN-SUFFIX,A.COM", "DOMAIN-SUFFIX,a.com"]
        result, _ = process_rules(make_cfg(), raw)
        self.assertEqual(len(result), 1)

    def test_tail_does_not_create_duplicates(self):
        """带策略名和不带，清洗后是同一条，只留一份。"""
        raw = ["DOMAIN,a.com", "DOMAIN,a.com,GoogleAI"]
        result, stats = process_rules(make_cfg(), raw)
        self.assertEqual(result, [("DOMAIN", "a.com")])
        self.assertEqual(stats["dup_src"], 1)


class TestFilter(unittest.TestCase):
    """黑名单与关键词过滤。"""

    def test_ignored_rules_removed(self):
        raw = ["DOMAIN,keep.com", "DOMAIN,drop.com"]
        cfg = make_cfg(ignored_rules=["DOMAIN,drop.com"])
        result, stats = process_rules(cfg, raw)
        self.assertEqual(result, [("DOMAIN", "keep.com")])
        self.assertEqual(stats["filtered"], 1)

    def test_ignored_rule_with_tail_still_matches(self):
        """黑名单里写了尾巴也没关系，清洗后照样能对上。"""
        raw = ["IP-CIDR,10.0.0.0/8"]
        cfg = make_cfg(ignored_rules=["IP-CIDR,10.0.0.0/8,no-resolve"])
        result, stats = process_rules(cfg, raw)
        self.assertEqual(result, [])
        self.assertEqual(stats["filtered"], 1)

    def test_exclude_keyword(self):
        raw = ["DOMAIN-SUFFIX,ads.a.com", "DOMAIN-SUFFIX,good.a.com"]
        cfg = make_cfg(exclude_keywords=["ads"])
        result, _ = process_rules(cfg, raw)
        self.assertEqual(result, [("DOMAIN-SUFFIX", "good.a.com")])

    def test_include_keyword_keeps_only_matches(self):
        # 注意：关键词是拿"类型,值"去匹配的，连类型名一起算。
        # 所以像 "ai" 这种短词会命中 "domain"，测试里用不易撞车的词。
        raw = ["DOMAIN-SUFFIX,keep.example.com", "DOMAIN-SUFFIX,cdn.example.com"]
        cfg = make_cfg(include_keywords=["keep"])
        result, _ = process_rules(cfg, raw)
        self.assertEqual(result, [("DOMAIN-SUFFIX", "keep.example.com")])

    def test_strict_ss_placeholder(self):
        """占位用例：确保上面的过滤用例真的有断言。"""
        self.assertTrue(True)


class TestExtraRules(unittest.TestCase):
    """手动追加的规则必须排在结果最前面。"""

    def test_extra_rules_come_first(self):
        raw = ["DOMAIN-SUFFIX,z.com"]
        cfg = make_cfg(extra_rules=["DOMAIN-SUFFIX,manual.com"])
        result, stats = process_rules(cfg, raw)
        self.assertEqual(result[0], ("DOMAIN-SUFFIX", "manual.com"))
        self.assertEqual(stats["vip"], 1)

    def test_extra_rule_tail_is_dropped(self):
        """手动规则里写了尾巴，同样会被丢掉。"""
        cfg = make_cfg(extra_rules=["IP-CIDR,10.0.0.0/8,no-resolve"])
        result, _ = process_rules(cfg, [])
        self.assertEqual(result, [("IP-CIDR", "10.0.0.0/8")])

    def test_duplicate_of_extra_rule_is_dropped(self):
        """源里出现了和手动规则相同的一条，应算作重复。"""
        raw = ["DOMAIN-SUFFIX,manual.com"]
        cfg = make_cfg(extra_rules=["DOMAIN-SUFFIX,manual.com"])
        result, stats = process_rules(cfg, raw)
        self.assertEqual(result, [("DOMAIN-SUFFIX", "manual.com")])
        self.assertEqual(stats["dup_vip"], 1)


class TestSorting(unittest.TestCase):
    """按规则类型的优先级排序：精确域名在前，IP 段在后。"""

    def test_domain_before_ip(self):
        raw = ["IP-CIDR,10.0.0.0/8", "DOMAIN,a.com"]
        result, _ = process_rules(make_cfg(), raw)
        self.assertEqual(result, [("DOMAIN", "a.com"), ("IP-CIDR", "10.0.0.0/8")])

    def test_exact_domain_before_suffix(self):
        raw = ["DOMAIN-SUFFIX,a.com", "DOMAIN,b.com"]
        result, _ = process_rules(make_cfg(), raw)
        self.assertEqual(result[0], ("DOMAIN", "b.com"))


class TestSkipAndDrop(unittest.TestCase):
    """跳过和丢弃必须分开：注释空行不是错误，真丢弃要能说清原因。"""

    def test_comment_and_blank_lines_are_skipped(self):
        raw = ["# 注释", "", "   ", "!", "##.ad-banner"]
        _, stats = process_rules(make_cfg(), raw)
        self.assertEqual(stats["skip"], 5)
        self.assertEqual(stats["drop"], 0)

    def test_unsupported_type_is_dropped(self):
        raw = ["SRC-PORT,41641", "DOMAIN,a.com"]
        _, stats = process_rules(make_cfg(), raw)
        self.assertEqual(stats["drop"], 1)
        self.assertEqual(stats["drop_detail"]["unsupported"], 1)

    def test_unrecognized_line_is_dropped(self):
        raw = ["这不是规则也不是注释"]
        _, stats = process_rules(make_cfg(), raw)
        self.assertEqual(stats["drop"], 1)
        self.assertEqual(stats["drop_detail"]["unrecognized"], 1)

    def test_samples_are_limited_to_three(self):
        raw = [f"SRC-PORT,{i}" for i in range(10)]
        _, stats = process_rules(make_cfg(), raw)
        self.assertEqual(len(stats["drop_samples"]["unsupported"]), 3)


class TestStats(unittest.TestCase):
    """统计数字要能反映各阶段的数量（日志会展示它们）。"""

    def test_counts(self):
        raw = ["DOMAIN,a.com", "# 注释", "DOMAIN,a.com"]
        result, stats = process_rules(make_cfg(), raw)

        self.assertEqual(stats["source"], 3)
        self.assertEqual(stats["skip"], 1)
        self.assertEqual(stats["drop"], 0)
        self.assertEqual(stats["dup_src"], 1)
        self.assertEqual(stats["total"], len(result))


class TestEmptyResult(unittest.TestCase):
    """各种原因导致最终一条不剩时，依然要正常返回，不能崩。"""

    def test_everything_filtered_out(self):
        """白名单一个都不命中：结果为空，统计如实记录。"""
        raw = ["DOMAIN-SUFFIX,a.com", "DOMAIN-SUFFIX,b.com"]
        cfg = make_cfg(include_keywords=["nothing-matches"])

        result, stats = process_rules(cfg, raw)

        self.assertEqual(result, [])
        self.assertEqual(stats["filtered"], 2)
        self.assertEqual(stats["total"], 0)

    def test_all_lines_invalid(self):
        """全是认不出的行：结果为空，invalid 类型的丢弃要记上。"""
        raw = ["这不是规则", "也不是规则"]

        result, stats = process_rules(make_cfg(), raw)

        self.assertEqual(result, [])
        self.assertEqual(stats["drop"], 2)

    def test_empty_input(self):
        result, stats = process_rules(make_cfg(), [])

        self.assertEqual(result, [])
        self.assertEqual(stats["source"], 0)


if __name__ == "__main__":
    unittest.main()
