# core/logger.py

# ======================================================================
# 模块说明：日志系统
#
# 职责：把"发生了什么事"渲染成人能读的样子。它不负责业务逻辑，
#       只负责三件事——收事件、查文案、排格式。
#
# 设计约定（改这个文件之前请先读）：
#   1. 其他模块只调用下面的事件方法，不自己拼输出格式；
#   2. 只有这个文件知道"终端"和"CI"两种呈现方式的区别（自动判断，
#      不靠命令行开关）；
#   3. 所有文案集中在 TEXT 字典里，改文案只改这里；
#   4. TEXT 的键用英文、值用中文模板，将来要做多语言就是再加一份字典，
#      调用方一行都不用改。
# ======================================================================

import os
import unicodedata
from typing import ClassVar

from core.constants import LOG_LEVEL_DEBUG, LOG_LEVEL_INFO

# 三种状态的符号。放在这里统一管理，终端和 CI 都用它。
MARK_OK = "✅"
MARK_WARN = "⚠️"
MARK_FAIL = "❌"

# ======================================================================
# 文案字典
# 占位符用 {xxx}，由 _t() 填充。改文案只改这里。
# ======================================================================
TEXT = {
    # --- 运行 ---
    "RUN_START": "ProxyAssetsHub · 开始 {time} · {total} 个任务",
    "RUN_END": "合计 {ok} {n_ok} · {warn} {n_warn} · {fail} {n_fail} · 结束 {time}",
    # --- 任务块 ---
    "LABEL_PHASE": "阶段",
    "LABEL_COLLECTION": "规则集",
    "LABEL_INPUT": "输入",
    "LABEL_OUT": "输出",
    "LABEL_TIME": "耗时",
    "LABEL_STATE": "状态",
    "LABEL_RESULT": "结果",
    "LABEL_DL": "下载",
    "LABEL_PARSE": "解析",
    "LABEL_CONV": "转换",
    "LABEL_WRITE": "写入",
    "DL_SUMMARY": "{ok}/{total} 成功 · {lines} 行",
    "PARSE_HEAD": "输入 {raw} → 输出 {out}",
    "PARSE_FACT": "{label} {n}",
    "PARSE_FILTERED": "过滤 {n}",
    "PARSE_DUP": "重复 {n}",
    "PARSE_VIP": "追加 {n}",
    "PARSE_SKIP": "跳过 {n}",
    "DROP_UNSUPPORTED": "类型不支持",
    "DROP_UNRECOGNIZED": "格式未识别",
    "DROP_EMPTY": "空值",
    "CONV_ITEM": "{format}: {rules} 条",
    "CONV_DROPPED": "（丢弃 {dropped}）",
    "WRITE_ITEM": "{format}: {files} 文件",
    "NO_OUTPUT": "全部下载失败，本任务没有产出",
    # --- 问题清单 ---
    "PROBLEM_HEAD": "发现 {n} 个问题：",
    "PROBLEM_ITEM": "  {i}. {scope} · {text}",
    "ALL_OK": "全部正常",
    # --- 配置相关（loader 使用） ---
    "CONFIG_EMPTY": "配置为空",
    "CONFIG_NOT_DICT": "配置格式错误：根节点应该是字典",
    "CONFIG_CRASH": "配置处理出错：{detail}",
    "FORMATS_NOT_LIST": "formats 应该是列表",
    "FORMATS_ITEM_NOT_STR": "formats 里的每一项都应该是字符串",
    "CUSTOM_HEADERS_NOT_DICT": "custom_headers 应该是字典",
    "FILTERS_NOT_DICT": "filters 应该是字典",
    "FILTER_ITEM_NOT_LIST": "filters 下的 {key} 应该是列表",
    "IDENT_NOT_STR": "{key} 应该是字符串",
    "YAML_ERR": "YAML 格式错误：{detail}",
    "LOAD_ERR": "读取失败：{detail}",
    "NAME_NOT_SET": "未命名，已按文件名补上",
    "CONFIG_DISABLED": "已禁用，跳过",
    "ENABLED_TYPE_ERR": "enabled 类型错误（{value}）",
    "ENABLED_UNKNOWN": "enabled 取值无法识别",
    "SOURCES_NOT_LIST": "sources 不是列表",
    "SOURCES_EMPTY": "sources 为空",
    "DIR_NOT_FOUND": "配置目录不存在：{path}",
    "NO_OUTPUT_FMT": "没有可输出的格式，已跳过",
    "DEFAULTS_NOT_DICT": "通用配置内容不是键值对",
    "DEFAULTS_KEY_IGNORED": "通用配置里不支持的字段：{key}",
    # --- 运行期问题 ---
    "SOURCE_FAIL": "源 {index}/{total} 下载失败：{error}",
    "NO_FORMATTER": "没有对应翻译器：{format}",
    "WRITE_FAIL": "写入失败：{format}",
    "OUTPUT_CONFLICT": "文件名冲突：{path} 已被 {owner} 使用，本规则集的 {format} 版本未写入",
    "EXCEPTION": "异常：{error}",
    "PROCESS_FAIL": "处理失败",
}


# 下载失败时网址最多显示多少个字符（不含协议）。
# 这个值只保证"错误原因不会被挤到下一行"——原因看漏比网址看不全更麻烦。
# 真要精确定位是哪个源，看前面的 "源 3/8" 序号即可。
URL_WIDTH = 60


def _fit_url(url: str, width: int = URL_WIDTH) -> str:
    """网址去掉协议后压进指定宽度，超出部分从尾部截掉。"""
    if "://" in url:
        url = url.split("://", 1)[1]
    if len(url) <= width:
        return url
    return url[: width - 1] + "…"


def _drop_label(code: str) -> str:
    """把丢弃原因的内部代号翻成中文，文案统一放在 TEXT 里。"""
    return _t("DROP_" + code.upper())


def _t(name: str, **kwargs) -> str:
    """
    取一条文案并填充占位符。

    第一个参数故意叫 name 而不是 key：模板参数里也可能出现名为 key 的值
    （例如"不支持的字段：{key}"），形参同名会直接冲突。

    将来要做多语言，只需要把这里改成"按当前语言从对应字典取"，
    调用方一律不用动。
    """
    return TEXT.get(name, name).format(**kwargs)


# ======================================================================
# 排版小工具
# ======================================================================


def _width(text: str) -> int:
    """
    估算一段文字在终端里占多少列。

    中文、全角符号按 2 列算，其余按 1 列。终端是等宽的，这样能对齐；
    在聊天窗口这类比例字体里仍可能歪，属于显示环境差异，不是数据问题。
    """
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int, right: bool = False) -> str:
    """把文字补到指定显示宽度。right=True 时右对齐（数字列用）。"""
    fill = " " * max(0, width - _width(text))
    return fill + text if right else text + fill


class Logger:
    """
    [核心模块：日志器]

    所有输出都从这里走。外部只调用事件方法，不关心排版。
    """

    # --- 当前状态（由 init 设置） ---
    _level = LOG_LEVEL_INFO
    _ci = False

    # 本次运行中累积的问题，供结尾清单使用。
    # ClassVar 表示"这是类级别的共享变量"——日志器没有实例，所有调用共用这一份，
    # 这正是我们想要的；加上标注工具就不会再提示"可变默认值"了。
    _problems: ClassVar[list] = []

    # ==================================================================
    # 初始化
    # ==================================================================

    @classmethod
    def init(cls, level=LOG_LEVEL_INFO):
        """
        初始化日志器。

        level：详略程度。LOG_LEVEL_INFO（默认）或 LOG_LEVEL_DEBUG。
        呈现方式不在这里选：程序自动判断是否跑在 CI 环境里。
        """
        cls._level = level
        cls._ci = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
        cls._problems = []

    @classmethod
    def is_debug(cls) -> bool:
        """是否开启了 debug 详略。"""
        return cls._level >= LOG_LEVEL_DEBUG

    # ==================================================================
    # 基础输出
    # ==================================================================

    @classmethod
    def _emit(cls, text: str):
        print(text, flush=True)

    @classmethod
    def _debug(cls, text: str, tag: str = ""):
        """只在 --debug 时输出的补充信息。"""
        if not cls.is_debug():
            return
        prefix = f"[{tag}] " if tag else ""
        cls._emit(f"      {prefix}{text}")

    # ==================================================================
    # 运行级事件
    # ==================================================================

    @classmethod
    def run_start(cls, total: int, start_time: str):
        """程序开始。"""
        if cls._ci:
            cls._emit(f"--- ProxyAssetsHub start · {total} tasks · {start_time} ---")
        else:
            cls._emit(_t("RUN_START", time=start_time, total=total))
            cls._emit("")

    @classmethod
    def run_end(cls, records: list, duration: float, end_time: str):
        """
        运行结束：终端模式打印总表 + 问题清单；CI 模式只打一行统计。

        records 是每个任务的运行结果字典，字段固定：
            category / collection / ok_src / n_src / lines_in / out / secs / state
        """
        # 这里跑在收尾阶段：万一以后新增了第四种状态，
        # counts[state] 会直接 KeyError，把整次运行崩在最后一步（产物已写完，
        # CI 只看到红叉，真实原因却藏在这里）。用 get 兜底，未知状态不参与统计。
        counts = {"成功": 0, "警告": 0, "失败": 0}
        for r in records:
            state = r["state"]
            counts[state] = counts.get(state, 0) + 1

        if cls._ci:
            cls._emit(
                f"--- summary: {MARK_OK} ok={counts['成功']} · "
                f"{MARK_WARN} warn={counts['警告']} · "
                f"{MARK_FAIL} fail={counts['失败']} · {end_time} ---"
            )
            # CI 里同样要有问题清单：退出码只说"失败了"，
            # 具体哪一条、为什么，还得靠这里看。
            cls._emit("")
            cls._emit_problems()
            return

        cls._emit("")
        # 每一列：文案键、固定宽度、是否右对齐。
        # 列与列之间统一用两个空格分隔，这样表头和数据行的间距完全一致。
        columns = [
            ("LABEL_PHASE", 6, False),
            ("LABEL_COLLECTION", 20, False),
            ("LABEL_DL", 6, False),
            ("LABEL_INPUT", 10, True),
            ("LABEL_OUT", 10, True),
            ("LABEL_TIME", 7, True),
        ]

        def join_row(cells):
            return "  ".join(_pad(v, w, right) for v, w, right in cells)

        header = [
            (_t(key), width, right) for key, width, right in columns
        ]
        cls._emit(join_row(header) + "  " + _t("LABEL_STATE"))

        for r in records:
            cells = [
                (r["category"], columns[0][1], columns[0][2]),
                (r["collection"], columns[1][1], columns[1][2]),
                (f"{r['ok_src']}/{r['n_src']}", columns[2][1], columns[2][2]),
                (f"{r['lines_in']:,}", columns[3][1], columns[3][2]),
                (f"{r['out']:,}", columns[4][1], columns[4][2]),
                (f"{r['secs']:.1f}s", columns[5][1], columns[5][2]),
            ]
            cls._emit(join_row(cells) + "  " + r["state_mark"])

        cls._emit("-" * 78)
        cls._emit(
            _t(
                "RUN_END",
                ok=MARK_OK,
                n_ok=counts["成功"],
                warn=MARK_WARN,
                n_warn=counts["警告"],
                fail=MARK_FAIL,
                n_fail=counts["失败"],
                time=end_time,
            )
        )

        # 问题清单：不管前面滚了多少，最后一定有一份完整列表
        cls._emit("")
        cls._emit_problems()

    @classmethod
    def _emit_problems(cls):
        """打印本次运行收集到的问题清单。终端和 CI 都走这里，保证两边都能看到。"""
        if cls._problems:
            cls._emit(MARK_FAIL + " " + _t("PROBLEM_HEAD", n=len(cls._problems)))
            for i, (scope, text) in enumerate(cls._problems, 1):
                cls._emit(_t("PROBLEM_ITEM", i=i, scope=scope, text=text))
        else:
            cls._emit(MARK_OK + " " + _t("ALL_OK"))

    # ==================================================================
    # 任务级事件
    # ==================================================================

    @classmethod
    def task_start(cls, index: int, total: int, name: str):
        """一个任务开始。"""
        cls._emit(f"[{index}/{total}] {name}")

    @classmethod
    def download_summary(cls, results: list):
        """
        下载阶段结束：打印汇总行，失败的源各自单独一行并标出来。

        results 每项：{"index", "total", "ok", "lines", "url", "error"}
        """
        ok = sum(1 for r in results if r["ok"])
        total = len(results)
        lines_in = sum(r["lines"] for r in results)

        if cls._ci:
            for r in results:
                if r["ok"]:
                    cls._emit(f"[DL]    {r['index']}/{r['total']} ok lines={r['lines']}")
                else:
                    cls._emit(f"[DL]    {r['index']}/{r['total']} FAIL {r['error']}")
                    text = _t("SOURCE_FAIL", index=r["index"], total=r["total"],
                              error=r["error"])
                    cls._emit(f"::error::{MARK_FAIL} [{r['scope']}] {text}")
                    cls._problems.append((r["scope"], text))
            return

        cls._emit(
            f"  |- {_t('LABEL_DL')}  "
            + _t("DL_SUMMARY", ok=ok, total=total, lines=f"{lines_in:,}")
        )

        # 只有 --debug 才逐个源列出明细，默认级别不刷屏
        if cls.is_debug():
            for r in results:
                mark = MARK_OK if r["ok"] else MARK_FAIL
                cls._emit(
                    f"  |  {mark} 源 {r['index']}/{r['total']} · {r['lines']:,} 行"
                )
        for r in results:
            if r["ok"]:
                continue
            # 完整显示网址，只把超出宽度的尾部省略：
            # 协议、域名、作者都在前面，保住开头比保住结尾有用得多。
            # 带上序号：网址本身可能被省略得只剩开头，序号能直接对到配置里的第几个源
            cls._emit(
                f"  |  {MARK_FAIL} 源 {r['index']}/{r['total']} "
                f"[{_fit_url(r['url'])}] ❗ {r['error']}"
            )
            cls._problems.append(
                (
                    r["scope"],
                    _t("SOURCE_FAIL", index=r["index"], total=r["total"], error=r["error"]),
                )
            )

    @classmethod
    def parse_summary(cls, stats: dict):
        """
        解析阶段结束：打印清洗与去重的数字。

        "跳过"和"丢弃"分开显示。空行、注释行属于跳过，数量再大也是正常的；
        丢弃才是"本来是规则但没能用上"，需要看清丢的是什么。
        """
        source = stats.get("source", 0)
        skip = stats.get("skip", 0)
        drop = stats.get("drop", 0)
        valid = source - skip - drop

        if cls._ci:
            cls._emit(
                f"[PARSE] raw={source} valid={valid} skip={skip} drop={drop} "
                f"dup_src={stats.get('dup_src', 0)} dup_vip={stats.get('dup_vip', 0)} "
                f"filtered={stats.get('filtered', 0)} vip={stats.get('vip', 0)} "
                f"out={stats.get('total', 0)}"
            )
            return

        # 一行把账算清：原始 - 各种损耗 + 追加 = 产出。
        # 只列非零项，否则满屏都是 0，重点会被淹掉。
        head = _t("PARSE_HEAD", raw=f"{source:,}", out=f"{stats.get('total', 0):,}")

        facts = [
            _t("PARSE_FACT", label=_drop_label(code), n=f"{count:,}")
            for code, count in (stats.get("drop_detail") or {}).items()
            if count
        ]
        for key, value in (
            ("PARSE_FILTERED", stats.get("filtered", 0)),
            ("PARSE_DUP", stats.get("dup_src", 0) + stats.get("dup_vip", 0)),
            ("PARSE_VIP", stats.get("vip", 0)),
            ("PARSE_SKIP", skip),
        ):
            if value:
                facts.append(_t(key, n=f"{value:,}"))

        tail = (" ｜ " + " · ".join(facts)) if facts else ""
        cls._emit(f"  |- {_t('LABEL_PARSE')}  {head}{tail}")

        # 调试模式下把原始样例打出来，能直接看到被丢的是什么
        if cls.is_debug():
            for code, samples in (stats.get("drop_samples") or {}).items():
                for sample in samples:
                    cls._emit(f"  |   {_drop_label(code)}：{sample}")

    @classmethod
    def convert_summary(cls, formats: list):
        """转换阶段结束：每种格式产出多少条。formats 每项 {"format","rules"}。"""
        if cls._ci:
            cls._emit(
                "[CONV]  "
                + " ".join(
                    f"{f['format']}={f['rules']}"
                    + (f"(drop {f['dropped']})" if f.get("dropped") else "")
                    for f in formats
                )
            )
            return

        items = " ｜ ".join(
            _t("CONV_ITEM", format=f["format"], rules=f"{f['rules']:,}")
            + (
                _t("CONV_DROPPED", dropped=f"{f['dropped']:,}")
                if f.get("dropped")
                else ""
            )
            for f in formats
        )
        cls._emit(f"  |- {_t('LABEL_CONV')}  {items}")

    @classmethod
    def write_summary(cls, formats: list, seconds: float):
        """
        写入阶段结束：写了几个文件。

        成功时不额外标注（没有消息就是好消息）；失败时另起一行标出来，
        和下载失败的呈现方式保持一致。
        """
        if cls._ci:
            cls._emit(
                "[WRITE] "
                + " ".join(f"{f['format']}={f['files']}file" for f in formats)
                + f" {seconds:.1f}s"
            )
        else:
            items = " ｜ ".join(
                _t("WRITE_ITEM", format=f["format"], files=f["files"]) for f in formats
            )
            cls._emit(f"  \\- {_t('LABEL_WRITE')}  {items}      {seconds:.1f}s")

        for f in formats:
            if f.get("ok", True):
                continue
            detail = f.get("error")
            text = detail or _t("WRITE_FAIL", format=f["format"])
            if cls._ci:
                cls._emit(f"::error::{MARK_FAIL} [{f['scope']}] {text}")
            else:
                cls._emit(f"     {MARK_FAIL} {text}")
            cls._problems.append((f["scope"], text))

    @classmethod
    def task_end(cls):
        """任务块结束：终端模式空一行，把相邻任务分开。"""
        if not cls._ci:
            cls._emit("")

    @classmethod
    def task_no_output(cls, scope: str):
        """任务因为一个源都没成功而没有任何产出。"""
        if cls._ci:
            cls._emit("[TASK]  all sources failed, no output")
        else:
            cls._emit(f"  |- {_t('LABEL_RESULT')}  {_t('NO_OUTPUT')}")

    # ==================================================================
    # 问题与提示（供 loader 等模块使用）
    # ==================================================================

    @classmethod
    def problem(cls, level: str, text: str, scope: str = ""):
        """
        报告一个问题。level 取 "error" 或 "warn"。

        终端：打一行带符号的提示；CI：打成 GitHub 注解（会浮到页面顶部）。
        两个模式都会记进本次的问题清单。
        """
        mark = MARK_FAIL if level == "error" else MARK_WARN
        prefix = f"[{scope}] " if scope else ""

        if cls._ci:
            kind = "error" if level == "error" else "warning"
            cls._emit(f"::{kind}::{mark} {prefix}{text}")
        else:
            cls._emit(f"  {mark} {prefix}{text}")

        cls._problems.append((scope or "-", text))

    @classmethod
    def msg(cls, name: str, **kwargs) -> str:
        """按文案字典取一条中文文案（供其他模块组装复合句子用）。"""
        return _t(name, **kwargs)

    @classmethod
    def no_output_format(cls, scope: str):
        """配置里没有任何可输出的格式。"""
        cls.problem("warn", _t("NO_OUTPUT_FMT"), scope=scope)

    @classmethod
    def task_exception(cls, scope: str, error):
        """任务执行中抛了异常。"""
        cls.problem("error", _t("EXCEPTION", error=error), scope=scope)

    @classmethod
    def process_failed(cls, scope: str):
        """任务处理失败（没有更具体的原因时使用）。"""
        cls.problem("error", _t("PROCESS_FAIL"), scope=scope)

    @classmethod
    def debug(cls, text: str, tag: str = ""):
        """兼容旧接口：只在 --debug 时输出。"""
        cls._debug(text, tag=tag)
