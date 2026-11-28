# tests/test_logger.py

# 测试对象：core/logger.py
#
# 这里不测"好看不好看"，只测"该有的信息在不在、符号对不对"：
#   - 终端模式：四行阶段、总表、问题清单
#   - CI 模式：紧凑标签、GitHub 注解、结尾统计
#
# 运行方式（在项目根目录）：
#   python -m unittest discover -s tests -v

import io
import os
import unittest
from contextlib import redirect_stdout

from core.constants import LOG_LEVEL_DEBUG, LOG_LEVEL_INFO
from core.logger import MARK_FAIL, MARK_OK, MARK_WARN, Logger, _pad, _width


def record(state="成功", collection="Direct", ok_src=1, n_src=1):
    """构造一条任务运行结果，字段与 Manager 传给日志的一致。"""
    mark = {"成功": MARK_OK, "警告": MARK_WARN, "失败": MARK_FAIL}[state]
    return {
        "category": "rule",
        "collection": collection,
        "ok_src": ok_src,
        "n_src": n_src,
        "lines_in": 100,
        "out": 80,
        "secs": 1.2,
        "state": state,
        "state_mark": mark,
    }


class LoggerTestBase(unittest.TestCase):
    """公共准备：每个用例前后重置环境变量和日志器状态。"""

    def setUp(self):
        self._saved_ci = os.environ.pop("CI", None)
        self._saved_gha = os.environ.pop("GITHUB_ACTIONS", None)

    def tearDown(self):
        os.environ.pop("CI", None)
        os.environ.pop("GITHUB_ACTIONS", None)
        if self._saved_ci is not None:
            os.environ["CI"] = self._saved_ci
        if self._saved_gha is not None:
            os.environ["GITHUB_ACTIONS"] = self._saved_gha

    def run_logger(self, func, level=LOG_LEVEL_INFO):
        """执行一段日志调用，返回它打印出来的文字。"""
        Logger.init(level=level)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            func()
        return buffer.getvalue()


class TestMessageLookup(unittest.TestCase):
    """文案模板的占位符参数名叫 key 时不能和形参冲突。"""

    def test_message_with_key_param(self):
        from core.logger import Logger

        self.assertEqual(
            Logger.msg("DEFAULTS_KEY_IGNORED", key="unknown_key"),
            "通用配置里不支持的字段：unknown_key",
        )


class TestTerminalMode(LoggerTestBase):
    """终端模式：树状四行 + 总表 + 清单。"""

    def test_full_task_block(self):
        def scenario():
            Logger.run_start(total=1, start_time="12:00:00")
            Logger.task_start(1, 1, "Direct规则集")
            Logger.download_summary(
                [{"index": 1, "total": 1, "ok": True, "lines": 100,
                  "url": "https://x/a.list", "error": None, "scope": "Direct"}]
            )
            Logger.parse_summary(
                {"source": 100, "skip": 8, "drop": 2, "dup_src": 5, "dup_vip": 0,
                 "filtered": 0, "vip": 0, "total": 85,
                 "drop_detail": {"unsupported": 2},
                 "drop_samples": {"unsupported": ["SRC-PORT,41641"]}}
            )
            Logger.convert_summary([{"format": "quantumultx", "rules": 85, "files": 1,
                                     "ok": True, "scope": "Direct"}])
            Logger.write_summary(
                [{"format": "quantumultx", "rules": 85, "files": 1, "ok": True,
                  "error": None, "scope": "Direct"}],
                1.2,
            )
            Logger.task_end()
            Logger.run_end([record()], 1.2, "12:00:01")

        out = self.run_logger(scenario)

        self.assertIn("ProxyAssetsHub · 开始 12:00:00 · 1 个任务", out)
        self.assertIn("[1/1] Direct规则集", out)
        self.assertIn("下载  1/1 成功 · 100 行", out)
        self.assertIn("解析  输入 100 → 输出 85", out)
        self.assertIn("类型不支持 2", out)
        self.assertIn("跳过 8", out)
        self.assertIn("转换  quantumultx: 85 条", out)
        self.assertIn("写入  quantumultx: 1 文件", out)
        self.assertIn("阶段", out)
        self.assertIn(MARK_OK, out)
        self.assertIn(MARK_OK + " 全部正常", out)

    def test_source_failure_is_visible_inline(self):
        def scenario():
            Logger.task_start(1, 1, "Direct规则集")
            Logger.download_summary(
                [
                    {"index": 1, "total": 2, "ok": True, "lines": 10,
                     "url": "https://x/ok.list", "error": None, "scope": "Direct"},
                    {"index": 2, "total": 2, "ok": False, "lines": 0,
                     "url": "https://raw.githubusercontent.com/a/b/c.list",
                     "error": "HTTP 500", "scope": "Direct"},
                ]
            )

        out = self.run_logger(scenario)

        self.assertIn("1/2 成功", out)
        # 失败必须在发生处单独一行，并且带地址和原因
        # 带上源序号、去掉协议的网址、醒目的错误符号，三者都要在同一行
        self.assertIn("源 2/2 [raw.githubusercontent.com/a/b/c.list] ❗ HTTP 500", out)

    def test_problem_list_at_the_end(self):
        def scenario():
            Logger.task_start(1, 1, "Direct规则集")
            Logger.download_summary(
                [{"index": 1, "total": 1, "ok": False, "lines": 0,
                  "url": "https://x/a.list", "error": "Timeout", "scope": "Direct"}]
            )
            Logger.task_no_output("Direct")
            Logger.task_end()
            Logger.run_end([record(state="失败", ok_src=0)], 1.0, "12:00:01")

        out = self.run_logger(scenario)

        self.assertIn("全部下载失败，本任务没有产出", out)
        self.assertIn(MARK_FAIL + " 发现 1 个问题", out)
        self.assertIn("Direct · 源 1/1 下载失败：Timeout", out)
        self.assertIn("Direct", out)
        self.assertIn(MARK_FAIL, out)

    def test_write_failure_line(self):
        def scenario():
            Logger.task_start(1, 1, "Direct规则集")
            Logger.write_summary(
                [{"format": "clash", "rules": 10, "files": 2, "ok": False,
                  "error": "写入失败：clash（permission denied）", "scope": "Direct"}],
                0.5,
            )

        out = self.run_logger(scenario)
        self.assertIn("写入失败：clash（permission denied）", out)


class TestUnknownState(LoggerTestBase):
    """收尾汇总时遇到未知状态不能崩。

    目前任务状态只有"成功/警告/失败"三种，但总数统计跑在最后一步：
    万一以后加了第四种状态，这里若用 counts[state] 会直接 KeyError，
    产物已经写完，CI 却只看到红叉，真实原因还藏在汇总代码里。
    """

    @staticmethod
    def _record_with_unknown_state():
        rec = record()
        rec["state"] = "跳过"
        rec["state_mark"] = "·"
        return rec

    def test_unknown_state_does_not_crash_terminal_mode(self):
        out = self.run_logger(
            lambda: Logger.run_end([self._record_with_unknown_state()], 1.0, "12:00:01")
        )
        # 未知状态不参与三个已知计数，但总表要照常打完
        self.assertIn("结束 12:00:01", out)

    def test_unknown_state_does_not_crash_ci_mode(self):
        os.environ["CI"] = "true"
        out = self.run_logger(
            lambda: Logger.run_end([self._record_with_unknown_state()], 0.3, "12:00:01")
        )
        self.assertIn("summary", out)


class TestDebugMode(LoggerTestBase):
    """debug 级别会多出逐源明细。"""

    def test_per_source_lines_only_in_debug(self):
        results = [
            {"index": 1, "total": 1, "ok": True, "lines": 42,
             "url": "https://x/a.list", "error": None, "scope": "Direct"}
        ]

        info_out = self.run_logger(lambda: Logger.download_summary(results))
        debug_out = self.run_logger(
            lambda: Logger.download_summary(results), level=LOG_LEVEL_DEBUG
        )

        self.assertNotIn("源 1/1 ·", info_out)
        self.assertIn("源 1/1 · 42 行", debug_out)


class TestCiMode(LoggerTestBase):
    """CI 模式：紧凑标签、注解、单行统计。"""

    def test_ci_output_shape(self):
        os.environ["CI"] = "1"

        def scenario():
            Logger.run_start(total=1, start_time="12:00:00")
            Logger.task_start(1, 1, "Direct规则集")
            Logger.download_summary(
                [{"index": 1, "total": 1, "ok": True, "lines": 10,
                  "url": "https://x/a.list", "error": None, "scope": "Direct"}]
            )
            Logger.parse_summary(
                {"source": 10, "skip": 0, "drop": 0, "dup_src": 0, "dup_vip": 0,
                 "filtered": 0, "vip": 0, "total": 10}
            )
            Logger.convert_summary([{"format": "quantumultx", "rules": 10, "files": 1,
                                     "ok": True, "scope": "Direct"}])
            Logger.write_summary(
                [{"format": "quantumultx", "rules": 10, "files": 1, "ok": True,
                  "error": None, "scope": "Direct"}],
                0.3,
            )
            Logger.run_end([record()], 0.3, "12:00:01")

        out = self.run_logger(scenario)

        self.assertIn("--- ProxyAssetsHub start · 1 tasks · 12:00:00 ---", out)
        self.assertIn("[DL]", out)
        self.assertIn("[PARSE]", out)
        self.assertIn("[CONV]", out)
        self.assertIn("[WRITE]", out)
        self.assertIn(f"--- summary: {MARK_OK} ok=1", out)
        # CI 模式不出终端表格
        self.assertNotIn("阶段  规则集", out)

    def test_ci_error_annotation(self):
        os.environ["CI"] = "1"

        def scenario():
            Logger.download_summary(
                [{"index": 1, "total": 1, "ok": False, "lines": 0,
                  "url": "https://x/a.list", "error": "HTTP 404", "scope": "Direct"}]
            )

        out = self.run_logger(scenario)
        self.assertIn("::error::", out)
        self.assertIn("下载失败：HTTP 404", out)


class TestDisplayWidth(LoggerTestBase):
    """
    终端是等宽的：一个汉字占两列，一个字母占一列。
    总表能对齐全靠这个计算，算错了所有列都会歪。
    """

    def test_ascii_letter_counts_one(self):
        self.assertEqual(_width("abc"), 3)

    def test_chinese_char_counts_two(self):
        self.assertEqual(_width("中文"), 4)

    def test_mixed_text(self):
        self.assertEqual(_width("规则1"), 5)

    def test_pad_left_aligned(self):
        """普通文本左对齐，右边补空格。"""
        self.assertEqual(_pad("ab", 4), "ab  ")

    def test_pad_right_aligned(self):
        """数字列右对齐，左边补空格。"""
        self.assertEqual(_pad("1", 4, right=True), "   1")

    def test_pad_never_truncates(self):
        """文字比目标宽度还长时，原样返回，不截断。"""
        self.assertEqual(_pad("abcdef", 3), "abcdef")


class TestTaskLifecycle(LoggerTestBase):
    """任务开始/结束/没有产出时的输出。"""

    def test_task_no_output_in_terminal(self):
        out = self.run_logger(lambda: Logger.task_no_output("Direct"))
        self.assertIn("全部下载失败", out)

    def test_task_no_output_in_ci(self):
        os.environ["CI"] = "true"
        out = self.run_logger(lambda: Logger.task_no_output("Direct"))
        self.assertIn("all sources failed", out)

    def test_task_end_prints_blank_line_except_in_ci(self):
        terminal = self.run_logger(lambda: Logger.task_end())
        self.assertEqual(terminal.strip(), "", "终端模式用一个空行分隔相邻任务")

        os.environ["CI"] = "true"
        ci = self.run_logger(lambda: Logger.task_end())
        self.assertEqual(ci, "", "CI 模式不插入空行")


class TestProblemReporting(LoggerTestBase):
    """
    问题报告的三种来源：普通的错误/警告、配置里没有格式、任务抛异常。
    共同点是都要进结尾的问题清单——CI 里这是唯一能看到原因的地方。
    """

    def test_error_problem_uses_fail_mark(self):
        out = self.run_logger(lambda: Logger.problem("error", "出错了", scope="X"))
        self.assertIn(MARK_FAIL, out)
        self.assertIn("[X] 出错了", out)

    def test_warn_problem_uses_warn_mark(self):
        out = self.run_logger(lambda: Logger.problem("warn", "注意一下", scope="X"))
        self.assertIn(MARK_WARN, out)

    def test_problem_without_scope_has_no_prefix(self):
        out = self.run_logger(lambda: Logger.problem("error", "没有来源"))
        self.assertNotIn("[", out.split("没有来源")[0].split()[-1], "没给 scope 就不该有方括号")

    def test_no_output_format_is_warning(self):
        out = self.run_logger(lambda: Logger.no_output_format("Direct"))
        self.assertIn(MARK_WARN, out)
        self.assertIn("没有可输出的格式", out)

    def test_task_exception_keeps_error_message(self):
        out = self.run_logger(
            lambda: Logger.task_exception("Direct", ValueError("boom"))
        )
        self.assertIn(MARK_FAIL, out)
        self.assertIn("boom", out, "异常原文要带上，不然排查时看不到原因")

    def test_process_failed_is_error(self):
        out = self.run_logger(lambda: Logger.process_failed("Direct"))
        self.assertIn(MARK_FAIL, out)

    def test_problems_are_collected_for_final_list(self):
        def scenario():
            Logger.problem("error", "第一个问题", scope="A")
            Logger.problem("warn", "第二个问题", scope="B")

        self.run_logger(scenario)
        self.assertEqual(len(Logger._problems), 2)
        self.assertEqual(Logger._problems[0][0], "A")


class TestDebugSamples(LoggerTestBase):
    """--debug 时会把被丢弃的原始行打出来，方便判断"丢的到底是什么"。"""

    @staticmethod
    def stats():
        return {
            "source": 3,
            "skip": 0,
            "drop": 2,
            "drop_detail": {"unsupported": 2},
            "drop_samples": {"unsupported": ["SRC-PORT,41641"]},
            "filtered": 0,
            "dup_src": 0,
            "dup_vip": 0,
            "vip": 0,
            "total": 1,
        }

    def test_samples_are_printed_in_debug_mode(self):
        out = self.run_logger(
            lambda: Logger.parse_summary(self.stats()), level=LOG_LEVEL_DEBUG
        )

        self.assertIn("SRC-PORT,41641", out)

    def test_samples_are_not_printed_in_normal_mode(self):
        out = self.run_logger(
            lambda: Logger.parse_summary(self.stats()), level=LOG_LEVEL_INFO
        )

        self.assertNotIn("SRC-PORT,41641", out, "默认级别不刷屏")


class TestCiSummaries(LoggerTestBase):
    """
    CI 模式没有总表，只有几行紧凑摘要。
    这里检查摘要里该有的字段都在——少一个字段，日志里就少一条线索。
    """

    def test_ci_parse_summary_contains_skip_and_drop(self):
        os.environ["CI"] = "true"
        stats = {
            "source": 10,
            "skip": 3,
            "drop": 2,
            "drop_detail": {"unsupported": 2},
            "drop_samples": {},
            "filtered": 1,
            "dup_src": 4,
            "dup_vip": 0,
            "vip": 0,
            "total": 5,
        }

        out = self.run_logger(lambda: Logger.parse_summary(stats))

        for piece in ("raw=10", "skip=3", "drop=2", "dup_src=4", "out=5"):
            self.assertIn(piece, out)

    def test_ci_convert_summary_contains_dropped(self):
        os.environ["CI"] = "true"
        formats = [
            {"format": "quantumultx", "rules": 10, "files": 1, "dropped": 0},
            {"format": "clash", "rules": 8, "files": 3, "dropped": 2},
        ]

        out = self.run_logger(lambda: Logger.convert_summary(formats))

        self.assertIn("quantumultx=10", out)
        self.assertIn("clash=8", out)
        self.assertIn("drop 2", out, "有丢弃才显示括号，没有就不显示")

    def test_ci_download_summary_lists_failed_source(self):
        os.environ["CI"] = "true"
        results = [
            {"index": 1, "total": 2, "ok": True, "lines": 10,
             "url": "https://x/1.list", "error": None, "scope": "Direct"},
            {"index": 2, "total": 2, "ok": False, "lines": 0,
             "url": "https://x/2.list", "error": "Timeout", "scope": "Direct"},
        ]

        out = self.run_logger(lambda: Logger.download_summary(results))

        self.assertIn("FAIL Timeout", out)
        self.assertIn("::error::", out, "CI 里要用注解的形式，才会浮到页面顶部")


if __name__ == "__main__":
    unittest.main()
