# tests/test_reporter.py

# 测试对象：core/reporter.py
#
# 这个模块负责在每个客户端目录下写 README.md：
# 每个规则集一段，条数/最后变更一行，订阅地址单独一行（方便复制）。
#
# 运行方式（在项目根目录）：
#   python -m unittest discover -s tests -v

import pathlib
import unittest

from core.reporter import _sub_dir, build_readme


def artifact(collection="Advertising", rules=1234, updated="2026-11-26 05:12:33",
             files=None):
    return {
        "collection": collection,
        "rules": rules,
        "updated": updated,
        "files": files or ["rule/QuantumultX/Block/Advertising.list"],
        "category": "rule",
        "client_dir": "QuantumultX",
    }


class TestPathSeparator(unittest.TestCase):
    """分组要能从反斜杠路径里正确切出来，否则 Windows 上 README 会排乱。"""

    def test_posix_path(self):
        self.assertEqual(
            _sub_dir("rule/QuantumultX/AI/OpenAI.list", "QuantumultX"), "AI"
        )

    def test_windows_path(self):
        self.assertEqual(
            _sub_dir("rule\\QuantumultX\\AI\\OpenAI.list", "QuantumultX"), "AI"
        )

    def test_root_level_file(self):
        self.assertEqual(
            _sub_dir("rule/QuantumultX/Direct.list", "QuantumultX"), ""
        )


class TestSingleFile(unittest.TestCase):
    """单文件客户端（Quantumult X）：地址单独一行。"""

    def setUp(self):
        self.md = build_readme(
            client_dir="QuantumultX",
            artifacts=[artifact()],
            run_time="2026-11-27 07:30:12",
            ok=12,
            total=12,
        )

    def test_title(self):
        self.assertIn("# Quantumult X 规则", self.md)

    def test_run_time(self):
        self.assertIn("最近一次运行：2026-11-27 07:30:12", self.md)
        self.assertIn("12/12", self.md)

    def test_collection_section(self):
        self.assertIn("#### Advertising", self.md)

    def test_stats_on_its_own_line(self):
        self.assertIn("条数：1,234 ｜ 最后变更：2026-11-26 05:12:33", self.md)

    def test_address_on_its_own_line(self):
        self.assertIn("订阅地址：https://raw.githubusercontent.com/", self.md)
        self.assertIn("/main/rule/QuantumultX/Block/Advertising.list", self.md)

    def test_address_is_not_in_the_stats_line(self):
        """地址和条数必须分行，不能挤在一起。"""
        stats_line = next(
            line for line in self.md.splitlines() if line.startswith("条数：")
        )
        self.assertNotIn("http", stats_line)


class TestMultipleFiles(unittest.TestCase):
    """多文件客户端（Clash）：每个分册一行地址。"""

    def setUp(self):
        files = [
            "rule/Clash/Block/Advertising_Domain.yaml",
            "rule/Clash/Block/Advertising_IP.yaml",
            "rule/Clash/Block/Advertising_Classical.yaml",
        ]
        self.md = build_readme(
            "Clash", [artifact(files=files)], "2026-11-27 07:30:12", 12, 12
        )

    def test_title_for_clash(self):
        self.assertIn("# Clash 规则", self.md)

    def test_each_part_is_listed(self):
        self.assertIn("- Domain：https://raw.githubusercontent.com/", self.md)
        self.assertIn("- IP：https://raw.githubusercontent.com/", self.md)
        self.assertIn("- Classical：https://raw.githubusercontent.com/", self.md)


class TestOrderStable(unittest.TestCase):
    """README 里的规则集顺序必须稳定，否则 git 里会出现大量无意义 diff。"""

    def test_sorted_by_collection(self):
        import pathlib
        import tempfile

        from core.reporter import write_client_readmes

        with tempfile.TemporaryDirectory() as d:
            artifacts = [
                artifact(collection="zeta", files=["rule/QuantumultX/zeta.list"]),
                artifact(collection="alpha", files=["rule/QuantumultX/alpha.list"]),
            ]
            write_client_readmes(d, artifacts, "2026-11-27 07:30:12", 2, 2)

            text = (pathlib.Path(d) / "rule" / "QuantumultX" / "README.md").read_text(
                encoding="utf-8"
            )
            self.assertLess(text.index("#### alpha"), text.index("#### zeta"))

    def test_sub_folder_before_root(self):
        """子文件夹里的规则集排在根目录之前，和 GitHub 文件列表一致。"""
        import pathlib
        import tempfile

        from core.reporter import write_client_readmes

        with tempfile.TemporaryDirectory() as d:
            artifacts = [
                artifact(collection="alpha", files=["rule/QuantumultX/alpha.list"]),
                artifact(collection="zeta", files=["rule/QuantumultX/AI/zeta.list"]),
            ]
            write_client_readmes(d, artifacts, "2026-11-27 07:30:12", 2, 2)

            text = (pathlib.Path(d) / "rule" / "QuantumultX" / "README.md").read_text(
                encoding="utf-8"
            )
            self.assertLess(text.index("#### zeta"), text.index("#### alpha"))


class TestFolderGrouping(unittest.TestCase):
    """README 要按子文件夹分组，根目录单独标出来。"""

    def _md(self, artifacts):
        return build_readme("QuantumultX", artifacts, "2026-11-27 07:30:12", 2, 2)

    def test_folder_heading(self):
        md = self._md([artifact(collection="OpenAI",
                                files=["rule/QuantumultX/AI/OpenAI.list"])])
        self.assertIn("### 📁 AI", md)

    def test_root_heading(self):
        md = self._md([artifact(collection="Direct",
                                files=["rule/QuantumultX/Direct.list"])])
        self.assertIn("### 📁 根目录", md)

    def test_separator_between_groups(self):
        md = self._md([
            artifact(collection="OpenAI", files=["rule/QuantumultX/AI/OpenAI.list"]),
            artifact(collection="Direct", files=["rule/QuantumultX/Direct.list"]),
        ])
        self.assertIn("---", md)
        self.assertLess(md.index("### 📁 AI"), md.index("### 📁 根目录"))


class TestMissingUpdated(unittest.TestCase):
    """没有更新时间时显示"未知"，而不是 None。"""

    def test_placeholder(self):
        md = build_readme(
            "QuantumultX", [artifact(updated=None)], "2026-11-27 07:30:12", 1, 1
        )
        self.assertIn("最后变更：未知", md)
        self.assertNotIn("None", md)


class TestMultiFileMerge(unittest.TestCase):
    """
    Clash 一个规则集会输出三个文件，README 里要合成一条记录。

    合成时有两件事需要决定：
        条数   —— 三个文件相加
        最后变更 —— 取三个文件里最晚的那个时间
    这里锁住这两个决定，因为它们是"凭直觉选的"，改错了不容易发现。
    """

    def test_rules_are_summed_and_time_takes_latest(self):
        import tempfile

        from core.reporter import write_client_readmes

        artifacts = [
            {
                "category": "rule",
                "client_dir": "Clash",
                "collection": "Direct",
                "rules": 10,
                "updated": "2026-11-20 10:00:00",
                "files": ["rule/Clash/Direct_Domain.yaml"],
            },
            {
                "category": "rule",
                "client_dir": "Clash",
                "collection": "Direct",
                "rules": 5,
                "updated": "2026-11-25 12:00:00",
                "files": ["rule/Clash/Direct_IP.yaml"],
            },
        ]

        with tempfile.TemporaryDirectory() as root:
            written = write_client_readmes(
                root, artifacts, "2026-11-27 07:00:00", 1, 1
            )
            text = pathlib.Path(written[0]).read_text(encoding="utf-8")

        self.assertIn("条数：15", text, "三个文件的条数要相加")
        self.assertIn("2026-11-25 12:00:00", text, "最后变更取最晚的那个")


class TestNoArtifacts(unittest.TestCase):
    """一个文件都没写成功时，不该凭空造出 README。"""

    def test_empty_artifacts_writes_nothing(self):
        import tempfile

        from core.reporter import write_client_readmes

        with tempfile.TemporaryDirectory() as root:
            written = write_client_readmes(
                project_root=root,
                artifacts=[],
                run_time="2026-11-27 07:30:12",
                ok=0,
                total=0,
            )

            self.assertEqual(written, [])
            self.assertEqual(
                list(pathlib.Path(root).rglob("README.md")), []
            )


if __name__ == "__main__":
    unittest.main()
