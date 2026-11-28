# tests/test_writer.py

# 测试对象：core/writer.py
#
# 重点锁定"UPDATED 的语义"：
#   - 产物里保留 UPDATED 行
#   - 内容没变时，不碰文件，UPDATED 保持原值（记录最后一次实质性变化的时间）
#   - 内容变了才更新 UPDATED
#
# 运行方式（在项目根目录）：
#   python -m unittest discover -s tests -v

import os
import pathlib
import tempfile
import time
import unittest

from core.writer import write_output

FAKE_TIME = "# UPDATED: UTC+8 2000-01-01 00:00:00"


def make_cfg():
    return {"name": "测试规则集", "collection": "Test"}


class WriterTestBase(unittest.TestCase):
    """每个用例用独立的临时目录，互不干扰。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def write(
        self,
        rules,
        filename="Test.list",
        header=True,
        dir_name="QuantumultX",
        rule_count=None,
    ):
        """按新的输出契约调用 writer：给它一个"要写哪些文件"的描述。"""
        item = {
            "dir": dir_name,
            "filename": filename,
            "content": rules,
            "header": header,
            "comment": "#",
        }
        if rule_count is not None:
            item["rule_count"] = rule_count

        return write_output(
            project_root=self.root,
            category="rule",
            sub_path="",
            cfg=make_cfg(),
            item=item,
        )

    @property
    def path(self):
        return pathlib.Path(self.root) / "rule" / "QuantumultX" / "Test.list"

    def read(self):
        return self.path.read_text(encoding="utf-8")

    def replace_updated_with_fake_time(self):
        """把产物里的 UPDATED 改成一个人造的老时间，方便观察它有没有被覆盖。"""
        lines = [
            FAKE_TIME if line.startswith("# UPDATED:") else line
            for line in self.read().splitlines()
        ]
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestHeader(WriterTestBase):
    """文件头的内容。"""

    def test_updated_line_is_present(self):
        ok, error, _, _ = self.write(["DOMAIN,a.com"])
        self.assertTrue(ok, error)
        self.assertIn("# UPDATED: UTC+8 ", self.read())

    def test_header_has_identity(self):
        self.write(["DOMAIN,a.com"])
        text = self.read()
        self.assertIn("# NAME: 测试规则集", text)
        self.assertIn("# AUTHOR:", text)
        self.assertIn("# REPO:", text)

    def test_rule_type_counts(self):
        self.write(["DOMAIN,a.com", "DOMAIN,b.com", "IP-CIDR,10.0.0.0/8"])
        text = self.read()
        self.assertIn("# DOMAIN: 2", text)
        self.assertIn("# IP-CIDR: 1", text)
        self.assertIn("# TOTAL: 3", text)

    def test_rule_count_from_caller_wins(self):
        """调用方给了条数就用它——只有它知道哪些行算规则。"""
        self.write(
            [
                "^https://a.com/ads url reject",
                "^https://b.com/track url reject",
                "DOMAIN,a.com",
            ],
            rule_count=3,
        )
        text = self.read()
        self.assertIn("# TOTAL: 3", text)
        # 类型分布只统计能识别类型的行
        self.assertIn("# DOMAIN: 1", text)

    def test_falls_back_to_type_count_without_hint(self):
        """没给条数时，退回"能识别出类型的行数"。"""
        self.write(["DOMAIN,a.com", "payload:"])
        text = self.read()
        self.assertIn("# TOTAL: 1", text)


class TestUpdatedSemantics(WriterTestBase):
    """UPDATED 只在内容变化时更新。"""

    def test_unchanged_content_keeps_old_timestamp(self):
        rules = ["DOMAIN,a.com", "DOMAIN-SUFFIX,b.com"]
        self.write(rules)
        self.replace_updated_with_fake_time()

        # 内容一模一样，再写一次
        self.write(rules)

        self.assertIn(FAKE_TIME, self.read())

    def test_changed_content_updates_timestamp(self):
        self.write(["DOMAIN,a.com"])
        self.replace_updated_with_fake_time()

        # 内容变了，应该重写并更新时间
        self.write(["DOMAIN,a.com", "DOMAIN,b.com"])

        text = self.read()
        self.assertNotIn(FAKE_TIME, text)
        self.assertIn("# UPDATED: UTC+8 ", text)
        self.assertIn("# TOTAL: 2", text)

    def test_same_content_twice_is_byte_identical(self):
        rules = ["DOMAIN,a.com"]
        self.write(rules)
        first = self.read()

        self.write(rules)
        second = self.read()

        self.assertEqual(first, second)

    def test_removed_rule_updates_timestamp(self):
        self.write(["DOMAIN,a.com", "DOMAIN,b.com"])
        self.replace_updated_with_fake_time()

        self.write(["DOMAIN,a.com"])

        text = self.read()
        self.assertNotIn(FAKE_TIME, text)
        self.assertIn("# TOTAL: 1", text)


class TestContract(WriterTestBase):
    """writer 只按契约写文件，文件名/目录由调用方决定。"""

    def test_custom_filename_and_dir(self):
        ok, error, path, _ = self.write(
            ["DOMAIN,a.com"], filename="Whatever.yaml", dir_name="Clash"
        )
        self.assertTrue(ok, error)
        self.assertEqual(pathlib.Path(path).name, "Whatever.yaml")
        self.assertIn("Clash", path)

    def test_no_header_when_disabled(self):
        ok, error, path, _ = self.write(["DOMAIN,a.com"], header=False)
        self.assertTrue(ok, error)

        text = pathlib.Path(path).read_text(encoding="utf-8")
        self.assertNotIn("# NAME:", text)
        self.assertNotIn("UPDATED", text)
        self.assertEqual(text, "DOMAIN,a.com\n")


class TestFailure(WriterTestBase):
    """写入失败时返回 (False, 原因)，而不是抛异常。"""

    def test_write_failure_returns_reason(self):
        # 用一个"文件"占住本应是目录的位置，制造写入失败
        blocker = pathlib.Path(self.root) / "rule"
        blocker.write_text("not a directory", encoding="utf-8")

        ok, error, _, _ = self.write(["DOMAIN,a.com"])
        self.assertFalse(ok)
        self.assertIsNotNone(error)


class TestNoHeaderMode(WriterTestBase):
    """
    header=False 时不写标准头部（也就没有 UPDATED 行）。

    已知限制：没有 UPDATED 行可供比对，"内容没变就不动文件"的判断失效，
    每次都会重写一遍。内容虽然一样，但文件修改时间会变。

    这不影响正确性，等重写阶段真正启用、需要生成 .conf 时再处理。
    这个用例的作用是把现状固定下来：将来行为变了，测试会提醒。
    """

    def test_no_header_omits_identity_lines(self):
        self.write(["DOMAIN,a.com"], header=False)
        text = self.read()
        self.assertNotIn("# NAME:", text)
        self.assertNotIn("# UPDATED:", text)
        self.assertEqual(text, "DOMAIN,a.com\n")

    def test_file_is_rewritten_each_time_without_header(self):
        self.write(["DOMAIN,a.com"], header=False)
        first = os.path.getmtime(self.path)

        time.sleep(0.02)
        self.write(["DOMAIN,a.com"], header=False)
        second = os.path.getmtime(self.path)

        self.assertGreater(second, first, "没有 UPDATED 行可比对，所以每次都会重写")


if __name__ == "__main__":
    unittest.main()
