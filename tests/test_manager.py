# tests/test_manager.py

# 测试对象：core/manager.py 的写入分发逻辑
#
# 重点验证"同一客户端目录下文件名必须唯一"这条规则：
# 第二个规则集想写同名文件时，应该被拒绝，而不是互相覆盖。
#
# 运行方式（在项目根目录）：
#   python -m unittest discover -s tests -v

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import core.manager as manager_module
from core.manager import Manager


class FakeFormatter:
    """测试用的假翻译器：一个规则集输出一个文件。"""

    @staticmethod
    def format_rules(rules, collection, policy="Default", header_lines=None):
        return [
            {
                "dir": "Fake",
                "filename": f"{collection}.list",
                "content": list(rules),
                "rule_count": len(rules),
                "header": True,
                "comment": "#",
            }
        ]


class TestJudge(unittest.TestCase):
    """任务状态判定：失败要能传出去，别把"没产出"报成成功。"""

    @staticmethod
    def record(ok_src=1, n_src=1, out=10):
        return {"ok_src": ok_src, "n_src": n_src, "out": out}

    def test_all_good_is_success(self):
        state, _ = Manager._judge(self.record(), [{"ok": True}])
        self.assertEqual(state, "成功")

    def test_no_source_succeeded_is_failure(self):
        state, _ = Manager._judge(self.record(ok_src=0, out=0), [])
        self.assertEqual(state, "失败")

    def test_zero_output_is_warning_not_success(self):
        """下载成功但一条规则都没剩下，不能报绿。"""
        state, _ = Manager._judge(self.record(out=0), [{"ok": True}])
        self.assertEqual(state, "警告")

    def test_partial_sources_is_warning(self):
        state, _ = Manager._judge(self.record(ok_src=1, n_src=2), [{"ok": True}])
        self.assertEqual(state, "警告")

    def test_write_failure_is_warning(self):
        state, _ = Manager._judge(self.record(), [{"ok": True}, {"ok": False}])
        self.assertEqual(state, "警告")

    def test_no_output_format_is_warning(self):
        """没写输出格式是配置问题，不是源出错，不该记失败。"""
        record = self.record(ok_src=0, out=0)
        record["no_format"] = True
        state, _ = Manager._judge(record, [])
        self.assertEqual(state, "警告")

    def test_crashed_task_is_failure(self):
        """任务中途抛异常必须判失败，不能因为"无产出"只报警告。

        警告的退出码是 0：CI 绿着、产物少一份，不点开日志根本看不出来。
        """
        record = self.record()
        record["crashed"] = True
        state, _ = Manager._judge(record, [{"ok": True}])
        self.assertEqual(state, "失败")


class TestOutputConflict(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_cwd = os.getcwd()
        os.chdir(self._tmp.name)

        manager_module.AVAILABLE_FORMATTERS["rule"]["fake"] = FakeFormatter
        manager_module.AVAILABLE_FORMATTERS["rewrite"]["fake"] = FakeFormatter
        self.mgr = Manager(level=1)

    def tearDown(self):
        manager_module.AVAILABLE_FORMATTERS["rule"].pop("fake", None)
        manager_module.AVAILABLE_FORMATTERS["rewrite"].pop("fake", None)
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    @staticmethod
    def make_cfg(name, collection):
        return {"name": name, "collection": collection, "__sub_path__": ""}

    def dispatch(self, cfg, category="rule"):
        """调用一次写入分发；日志输出被吞掉，避免污染测试输出。"""
        with redirect_stdout(io.StringIO()):
            return self.mgr._dispatch_write(cfg, ["DOMAIN,a.com"], "fake", {}, category)

    def test_first_write_is_ok(self):
        row = self.dispatch(self.make_cfg("A规则集", "Same"))
        self.assertTrue(row["ok"])
        self.assertEqual(row["files"], 1)

    def test_second_write_with_same_filename_is_blocked(self):
        self.dispatch(self.make_cfg("A规则集", "Same"))
        row = self.dispatch(self.make_cfg("B规则集", "Same"))

        self.assertFalse(row["ok"])
        self.assertEqual(row["files"], 0, "冲突时不应该写文件")
        self.assertIn("文件名冲突", row["error"])
        self.assertIn("A规则集", row["error"], "错误里要能看出是谁占用了这个名字")

    def test_same_name_in_different_phase_is_not_conflict(self):
        """rule 和 rewrite 是两个输出根目录，同名文件互不影响。"""
        self.dispatch(self.make_cfg("A规则集", "Same"), category="rule")
        row = self.dispatch(self.make_cfg("B规则集", "Same"), category="rewrite")

        self.assertTrue(row["ok"], "不同阶段同名文件不该判冲突")
        self.assertEqual(row["files"], 1)

    def test_different_ident_has_no_conflict(self):
        self.dispatch(self.make_cfg("A规则集", "A"))
        row = self.dispatch(self.make_cfg("B规则集", "B"))

        self.assertTrue(row["ok"])
        self.assertEqual(row["files"], 1)


class TestRunTaskFlow(unittest.TestCase):
    """
    跑通一个任务的完整骨架：下载 -> 解析 -> 转换 -> 写入 -> 判定。

    这些场景在真实数据里很难凑齐（比如"所有源同时失败"要看运气），
    用假的下载器和处理器来构造，毫秒级就能把四种结局都验证一遍。
    这正是单元测试相对"跑一次真实程序"的价值所在。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_cwd = os.getcwd()
        os.chdir(self._tmp.name)

        manager_module.AVAILABLE_FORMATTERS["rule"]["fake"] = FakeFormatter
        self.mgr = Manager(level=1)

    def tearDown(self):
        manager_module.AVAILABLE_FORMATTERS["rule"].pop("fake", None)
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    @staticmethod
    def make_cfg(with_formats=True):
        cfg = {
            "name": "测试规则集",
            "collection": "Test",
            "__sub_path__": "",
            "sources": ["https://x/1.list", "https://x/2.list"],
            "formats_data": {"fake": {"policy": "Test", "header_lines": []}},
        }
        if not with_formats:
            cfg["formats_data"] = {}
        return cfg

    @staticmethod
    def stats(total):
        """处理器返回的统计，字段和真实处理器保持一致。"""
        return {
            "source": total,
            "skip": 0,
            "drop": 0,
            "drop_detail": {},
            "drop_samples": {},
            "filtered": 0,
            "dup_src": 0,
            "dup_vip": 0,
            "vip": 0,
            "total": total,
        }

    @staticmethod
    def sources(*oks):
        """
        按顺序构造每个源的结果，参数就是每个源成功与否。

        配置里写了两个源，这里就必须给两条结果——数量对不上会被判成
        "部分源失败"，测试就测不到想测的东西了。
        """
        return [
            {
                "index": i + 1,
                "total": len(oks),
                "ok": ok,
                "lines": 10 if ok else 0,
                "url": f"https://x/{i + 1}.list",
                "error": None if ok else "Timeout",
                "scope": "测试规则集",
            }
            for i, ok in enumerate(oks)
        ]

    def run_task(self, download, cfg=None, processor=None, seen=None):
        """执行一次 _run_task，把处理器收到的原始行记在 seen 里。"""
        cfg = cfg or self.make_cfg()

        def default_processor(processor_cfg, raw):
            if seen is not None:
                seen.append(raw)
            return ["DOMAIN,a.com"], self.stats(1)

        with patch.object(
            manager_module, "download_sources", return_value=download
        ), redirect_stdout(io.StringIO()):
            return self.mgr._run_task("rule", cfg, processor or default_processor, 1, 1)

    def test_all_sources_ok_is_success(self):
        record = self.run_task(
            (["DOMAIN,a.com"], self.sources(True, True))
        )

        self.assertEqual(record["state"], "成功")
        self.assertEqual(record["ok_src"], 2)
        self.assertEqual(record["n_src"], 2)
        self.assertEqual(record["lines_in"], 20)
        self.assertEqual(record["out"], 1)

    def test_partial_source_failure_is_warning(self):
        """一个源挂了但还有数据：能用，但不完整，记警告。"""
        record = self.run_task(
            (["DOMAIN,a.com"], self.sources(True, False))
        )

        self.assertEqual(record["state"], "警告")
        self.assertEqual(record["ok_src"], 1)

    def test_no_data_stops_before_parsing(self):
        """一个源都没成功，解析阶段不该被调用——没有原料就别开工。"""
        seen = []
        record = self.run_task(([], self.sources(False, False)), seen=seen)

        self.assertEqual(record["state"], "失败")
        self.assertEqual(seen, [])
        self.assertEqual(record["out"], 0)

    def test_no_format_skips_download(self):
        """配置里没写输出格式，连下载都不该发生。"""
        with patch.object(
            manager_module, "download_sources"
        ) as mock_download, redirect_stdout(io.StringIO()):
            record = self.mgr._run_task(
                "rule", self.make_cfg(with_formats=False), lambda c, r: ([], {}), 1, 1
            )

        mock_download.assert_not_called()
        self.assertEqual(record["state"], "警告", "没格式是配置问题，不是源失败")

    def test_processor_exception_is_failure(self):
        """处理器抛异常时任务记失败，但不能把整批拖垮。

        异常必须判失败：记成"警告"的话退出码是 0，CI 绿着，
        而实际产物已经缺了一份——不点开日志根本发现不了。
        """

        def broken_processor(processor_cfg, raw):
            raise ValueError("处理炸了")

        record = self.run_task(
            (["DOMAIN,a.com"], self.sources(True, True)), processor=broken_processor
        )

        self.assertEqual(record["out"], 0)
        self.assertEqual(record["state"], "失败")


if __name__ == "__main__":
    unittest.main()
