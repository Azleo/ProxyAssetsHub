# tests/test_downloader.py

# 测试对象：core/downloader.py
#
# 重点验证两件事：
#   1. 值得重试的失败会重试，不值得的（404/403）立刻放弃
#   2. 编码不再强行按 utf-8 解，GBK 的源也能读对
#
# 运行方式（在项目根目录）：
#   python -m unittest discover -s tests -v

import unittest
from unittest.mock import Mock, patch

import requests

from core import downloader


def make_response(body: bytes = b"", status: int = 200, encoding: str | None = "utf-8"):
    """造一个 requests 响应的替身。"""
    resp = Mock()
    resp.content = body
    resp.status_code = status
    resp.encoding = encoding
    resp.raise_for_status = Mock()
    return resp


def http_error(status: int):
    """造一个带状态码的 HTTPError。"""
    resp = make_response(status=status)
    return requests.exceptions.HTTPError(response=resp)


class TestRetry(unittest.TestCase):
    """重试只针对"可能自愈"的失败。"""

    @patch("core.downloader.time.sleep")
    @patch("core.downloader.requests.get")
    def test_timeout_then_success(self, mock_get, mock_sleep):
        mock_get.side_effect = [
            requests.exceptions.Timeout(),
            make_response(b"a.com\nb.com"),
        ]

        lines, error = downloader._download_single_url("https://x/1.list")

        self.assertEqual(lines, ["a.com", "b.com"])
        self.assertIsNone(error)
        mock_sleep.assert_called_once()

    @patch("core.downloader.time.sleep")
    @patch("core.downloader.requests.get")
    def test_gives_up_after_max_attempts(self, mock_get, mock_sleep):
        mock_get.side_effect = requests.exceptions.Timeout()

        lines, error = downloader._download_single_url("https://x/1.list")

        self.assertIsNone(lines)
        self.assertEqual(error, "Timeout")
        # 一共尝试 RETRY_TIMES + 1 次，中间等待 RETRY_TIMES 次
        self.assertEqual(mock_get.call_count, downloader.RETRY_TIMES + 1)
        self.assertEqual(mock_sleep.call_count, downloader.RETRY_TIMES)

    @patch("core.downloader.time.sleep")
    @patch("core.downloader.requests.get")
    def test_404_is_not_retried(self, mock_get, mock_sleep):
        resp = make_response(status=404)
        resp.raise_for_status.side_effect = http_error(404)
        mock_get.return_value = resp

        lines, error = downloader._download_single_url("https://x/1.list")

        self.assertIsNone(lines)
        self.assertEqual(error, "HTTP 404")
        mock_sleep.assert_not_called()
        self.assertEqual(mock_get.call_count, 1)

    @patch("core.downloader.time.sleep")
    @patch("core.downloader.requests.get")
    def test_500_is_retried(self, mock_get, mock_sleep):
        first = make_response(status=500)
        first.raise_for_status.side_effect = http_error(500)
        mock_get.side_effect = [first, make_response(b"ok.com")]

        lines, error = downloader._download_single_url("https://x/1.list")

        self.assertEqual(lines, ["ok.com"])
        self.assertIsNone(error)
        mock_sleep.assert_called_once()


class TestDownloadSources(unittest.TestCase):
    """
    多个源的汇总逻辑：一个源失败不能影响其它源，每个结果都要如实记录。

    这是下载模块对外的主入口，但之前只测了"下载单个源"，
    多个源拼在一起会发生什么从没验证过。
    """

    @patch("core.downloader._download_single_url")
    def test_one_failure_does_not_lose_the_other(self, mock_single):
        mock_single.side_effect = [
            (["a.com", "b.com"], None),
            (None, "Timeout"),
        ]

        lines, results = downloader.download_sources(
            ["https://x/1.list", "https://x/2.list"], scope="Direct"
        )

        self.assertEqual(lines, ["a.com", "b.com"], "成功的源内容要保留")
        self.assertEqual(len(results), 2, "每个源都要有一条结果")
        self.assertTrue(results[0]["ok"])
        self.assertEqual(results[0]["lines"], 2)
        self.assertFalse(results[1]["ok"])
        self.assertEqual(results[1]["lines"], 0)
        self.assertEqual(results[1]["error"], "Timeout")
        self.assertEqual(results[1]["scope"], "Direct", "scope 要带到结果里，日志才知道是谁")

    @patch("core.downloader._download_single_url")
    def test_all_failed_gives_empty_lines(self, mock_single):
        mock_single.return_value = (None, "网络错误")

        lines, results = downloader.download_sources(["https://x/1.list"])

        self.assertEqual(lines, [])
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["ok"])

    @patch("core.downloader._download_single_url")
    def test_empty_source_is_not_an_error(self, mock_single):
        """源能下载但内容为空：算是成功，只是 0 行。"""
        mock_single.return_value = ([], None)

        lines, results = downloader.download_sources(["https://x/1.list"])

        self.assertEqual(lines, [])
        self.assertTrue(results[0]["ok"])
        self.assertEqual(results[0]["lines"], 0)


class TestDecode(unittest.TestCase):
    """编码优先按响应头，其次 utf-8，最后 gb18030。"""

    def test_utf8(self):
        resp = make_response("中文".encode(), encoding="utf-8")
        self.assertEqual(downloader._decode(resp), "中文")

    def test_gbk_without_declared_encoding(self):
        resp = make_response("中文".encode("gb18030"), encoding=None)
        self.assertEqual(downloader._decode(resp), "中文")

    def test_declared_encoding_is_wrong(self):
        """响应头说是 utf-8，实际是 GBK，也要能救回来。"""
        resp = make_response("中文".encode("gb18030"), encoding="utf-8")
        self.assertEqual(downloader._decode(resp), "中文")

    def test_unknown_encoding_name(self):
        """响应头里是个不认识的编码名，不能因此把整个源丢掉。"""
        resp = make_response("中文".encode(), encoding="x-unknown")
        self.assertEqual(downloader._decode(resp), "中文")


if __name__ == "__main__":
    unittest.main()
