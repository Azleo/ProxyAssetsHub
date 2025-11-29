# core/downloader.py

import requests
from typing import List, Tuple
from core.constants import DEFAULT_REQUEST_HEADERS, MSG_ERROR
from core.logger import Logger


def download_sources(url_list: List[str]) -> List[str]:
    """
    [下载器主入口]

    负责批量下载规则源。
    注意：这里不再包含任何中文字符串，全部调用 Logger 的变量。
    """
    all_lines = []
    total_sources = len(url_list)

    for i, url in enumerate(url_list, 1):
        # 执行单个下载
        lines, error_msg = _download_single_url(url)

        # [清洗点 1] 标签生成：使用 WORD_SOURCE_DATA ("源数据")
        source_tag = f"{Logger.WORD_SOURCE_DATA} [{i}/{total_sources}]"

        if lines is not None:
            count = len(lines)
            all_lines.extend(lines)

            # [清洗点 2] 成功日志：使用 WORD_SUCCESS ("成功") 和 WORD_ROWS ("行")
            # 格式示例: 成功: 1,024 行
            msg = f"{Logger.WORD_SUCCESS}: {count:,} {Logger.WORD_ROWS}"
            Logger.debug(msg, tag=source_tag)
        else:
            # [清洗点 3] 失败日志：使用 WORD_FAIL ("失败")
            msg = f"{Logger.WORD_FAIL}: {error_msg}"
            Logger.debug(msg, tag=source_tag)

            # 报告错误给 Logger
            Logger.log_generic_message(MSG_ERROR, f"{error_msg}", source=url)

    return all_lines


def _download_single_url(url: str) -> Tuple[List[str] | None, str | None]:
    """
    下载单个 URL。
    这里的错误信息也使用了 Logger 的变量。
    """
    try:
        resp = requests.get(url, headers=DEFAULT_REQUEST_HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return resp.text.splitlines(), None

    except requests.exceptions.HTTPError as e:
        # 使用 HTTP 状态码变量 (虽然这通常是英文，但我们可以加上前缀)
        return None, f"HTTP {e.response.status_code}"
    except requests.exceptions.Timeout:
        return None, "Timeout"  # 这是一个通用技术术语，保留英文或也在 Logger 中定义
    except requests.exceptions.RequestException:
        # [清洗点 4] 网络错误
        return None, f"{Logger.WORD_NET_ERR}"
    except Exception as e:
        return None, f"Error: {e}"
