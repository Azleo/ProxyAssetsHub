# core/downloader.py

import time

import requests

from core.constants import DEFAULT_REQUEST_HEADERS

# 失败后最多再试几次（不含第一次）
RETRY_TIMES = 2
# 每次重试之间等多久（秒）
RETRY_WAIT = 1.5


def download_sources(url_list: list[str], scope: str = "") -> tuple[list[str], list[dict]]:
    """
    [下载阶段]

    逐个下载规则源，返回两样东西：

      1. 所有源拼起来的原始行（交给解析阶段）
      2. 每个源的结果（交给日志）：成功与否、多少行、失败原因

    这里只负责"下载"和"整理结果"，不负责打印。
    打印由 Manager 统一调用 Logger 完成，这样下载器不用知道日志长什么样。
    """
    all_lines = []
    results = []
    total = len(url_list)

    for index, url in enumerate(url_list, 1):
        lines, error = _download_single_url(url)

        results.append(
            {
                "index": index,
                "total": total,
                "url": url,
                "ok": lines is not None,
                "lines": len(lines) if lines else 0,
                "error": error,
                "scope": scope,
            }
        )

        if lines:
            all_lines.extend(lines)

    return all_lines, results


def _decode(resp) -> str:
    """
    把响应体解成文本。

    依次尝试：响应头声明的编码 -> utf-8 -> gb18030。
    不再强行指定 utf-8——源若是 GBK，中文会整片变成乱码。
    gb18030 是 GBK 的超集，几乎能解任何字节，所以基本不会走到最后一步。
    """
    body = resp.content
    candidates = []
    if resp.encoding:
        candidates.append(resp.encoding)
    candidates.extend(["utf-8", "gb18030"])

    for encoding in candidates:
        try:
            return body.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue

    # 兜底：宽松解码。宁可出现几个替换字符，也不要整个源作废
    return body.decode("utf-8", errors="replace")


def _try_once(url: str) -> tuple[list[str] | None, str | None, bool]:
    """
    下载一次，返回 (行列表, 错误信息, 是否值得重试)。

    区分"值得重试"和"不值得"是重试有意义的前提：
    超时、连不上、服务端 5xx、被限流都可能是暂时的；
    而 404/403 说明资源本身不在了，再试多少次都一样。
    """
    try:
        resp = requests.get(url, headers=DEFAULT_REQUEST_HEADERS, timeout=15)
        resp.raise_for_status()
        return _decode(resp).splitlines(), None, False

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        retryable = status >= 500 or status == 429
        return None, f"HTTP {status}", retryable
    except requests.exceptions.Timeout:
        return None, "Timeout", True
    except requests.exceptions.ConnectionError:
        return None, "网络错误", True
    except requests.exceptions.RequestException:
        return None, "网络错误", False
    except Exception as e:  # noqa: BLE001 - 单源异常不该拖垮整批
        return None, f"Error: {e}", False


def _download_single_url(url: str) -> tuple[list[str] | None, str | None]:
    """
    下载单个 URL，返回 (行列表, 错误信息)。

    失败时行列表为 None，错误信息是中文短语（例如"网络错误"、"HTTP 404"）。
    可能自愈的失败会自动重试几次，最多一共尝试 RETRY_TIMES + 1 次。
    """
    last_error = "网络错误"

    for attempt in range(RETRY_TIMES + 1):
        lines, error, retryable = _try_once(url)
        if lines is not None:
            return lines, None

        last_error = error
        if not retryable or attempt == RETRY_TIMES:
            break

        time.sleep(RETRY_WAIT)

    return None, last_error
