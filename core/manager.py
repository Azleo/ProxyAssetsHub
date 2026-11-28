# core/manager.py

import os
import time
import traceback
from datetime import datetime

from core.constants import LOG_LEVEL_INFO
from core.downloader import download_sources
from core.loader import load_all_configs
from core.logger import MARK_FAIL, MARK_OK, MARK_WARN, Logger
from core.reporter import write_client_readmes
from core.rewrite import formatter_rewrite_loon, formatter_rewrite_quantumultx
from core.rewrite.processor_rewrite import process_rewrites
from core.rule import (
    formatter_rule_clash,
    formatter_rule_loon,
    formatter_rule_quantumultx,
)
from core.rule.processor_rule import process_rules
from core.writer import write_output

# 每个阶段有哪些翻译器。加新客户端时，只需要在这里注册一行。
AVAILABLE_FORMATTERS = {
    "rule": {
        "quantumultx": formatter_rule_quantumultx,
        "loon": formatter_rule_loon,
        "clash": formatter_rule_clash,
    },
    "rewrite": {
        "quantumultx": formatter_rewrite_quantumultx,
        "loon": formatter_rewrite_loon,
    },
}

# 每个阶段用哪个处理器。处理器负责"清洗 -> 去重 -> 过滤 -> 排序"。
PIPELINE_HANDLERS = {
    "rule": process_rules,
    "rewrite": process_rewrites,
}

# 执行顺序。目前只有 rule 有配置，rewrite 是留好的位置。
EXECUTION_ORDER = ["rule", "rewrite"]


class Manager:
    """
    [核心模块：任务调度器]

    负责整个程序的流程控制：读配置 -> 逐个任务跑流水线 -> 汇总输出。
    它不关心日志长什么样，只把"发生了什么"告诉 Logger。
    """

    def __init__(self, level=LOG_LEVEL_INFO):
        self.project_root = os.getcwd()
        Logger.init(level)
        # 每个任务跑完后的结果，最后交给 Logger 打印总表
        self.records = []
        # 本次运行已经写过的文件：{(目录, 文件名): 规则集名}
        # 用来发现"两个规则集输出了同名文件"这种会让用户困惑的情况
        self._written = {}

    # ==================================================================
    # 入口
    # ==================================================================

    def run(self):
        """
        程序入口。

        返回本次所有任务的运行记录。入口程序靠它判断有没有失败，
        决定要不要返回非 0 退出码让 CI 标红。
        """
        start_time = time.strftime("%H:%M:%S")
        started_at = time.time()
        self._written = {}

        # 先把所有阶段的配置读进来，这样才能在开头就报出任务总数
        phases = []
        for category in EXECUTION_ORDER:
            configs, problems = load_all_configs(
                subdir=category, project_root=self.project_root
            )
            # 加载阶段的问题由 manager 统一报告（loader 自己不说话）
            self._report_problems(problems)
            phases.append((category, configs))

        total = sum(len(configs) for _, configs in phases)
        Logger.run_start(total=total, start_time=start_time)

        for category, configs in phases:
            self._run_phase(category, configs)

        # 写每个客户端目录下的 README（订阅地址、条数、最后变更时间）
        self._write_reports()

        Logger.run_end(
            records=self.records,
            duration=time.time() - started_at,
            end_time=time.strftime("%H:%M:%S"),
        )
        return self.records

    # ==================================================================
    # 问题报告
    # ==================================================================

    def _report_problems(self, problems):
        """把各模块返回的问题记录交给日志输出。"""
        for item in problems:
            text = Logger.msg(item["code"], **item.get("params", {}))
            scope = item.get("scope", "")

            if item["level"] == "debug":
                Logger.debug(text, tag=scope)
            else:
                Logger.problem(item["level"], text, scope=scope)

    # ==================================================================
    # 阶段与任务
    # ==================================================================

    def _run_phase(self, category, configs):
        """执行单个阶段：逐个任务处理。"""
        processor = PIPELINE_HANDLERS.get(category)
        if not processor:
            return

        total = len(configs)
        for index, cfg in enumerate(configs, 1):
            self.records.append(self._run_task(category, cfg, processor, index, total))

    # ==================================================================
    # 单个任务：编排与记账
    #
    # manager 只负责"按顺序调下去"和"把数字记下来"，
    # 每一步内部怎么做交给对应模块。拆成 _stage_* 是为了：
    # 改某个阶段不牵动其它阶段，_run_task 保持一页能读完。
    # ==================================================================

    def _run_task(self, category, cfg, processor, index, total):
        """
        执行单个任务，返回运行记录（供总表和 README 使用）。

        流程：没有输出格式就跳过；下载拿不到数据就提前收工；
        否则 解析 -> 转换 -> 写入。任何一步不成立都停在这里，
        但该报的信息在收工前都报过了。

        整个流程包在 try 里：单个任务出错不该拖垮整批。
        """
        name = cfg.get("name", "Unknown")
        started = time.time()
        record = self._new_record(category, cfg)
        writes = []  # 每种格式的写入结果，判定状态要用

        Logger.task_start(index, total, name)

        try:
            # 没有输出格式的任务没有意义： formats 为空时，
            # 下载解析都成功也产不出文件，别浪费下载时间。
            # 这不是"失败"（源没问题），而是"这个规则集被配成不输出"，记警告即可。
            if not (cfg.get("formats_data") or {}):
                record["no_format"] = True
                Logger.no_output_format(name)
                return record

            # 返回 None 表示一个源都没成功，后面几步都没有意义
            raw_data = self._stage_download(cfg, record, name)
            if raw_data is None:
                return record

            final_data = self._stage_parse(processor, cfg, raw_data, record)
            self._stage_convert(cfg, final_data, category, record, name, started, writes)

        except Exception as error:  # noqa: BLE001 - 任何任务异常都不该拖垮整批
            Logger.task_exception(name, error)
            if Logger.is_debug():
                traceback.print_exc()

        finally:
            # 不管成功、提前收工还是抛异常，耗时和状态都要算出来，
            # 否则总表里这一行就是错的。
            record["secs"] = time.time() - started
            record["state"], record["state_mark"] = self._judge(record, writes)
            Logger.task_end()

        return record

    @staticmethod
    def _new_record(category, cfg):
        """
        任务记录的初始值。这些键和日志、README 是约定好的。

        初始状态写"失败"是刻意的：只有真正走完流程才会被 _judge 改成成功，
        中途提前收工就保持失败。
        """
        return {
            "category": category,
            "collection": cfg["collection"],
            "ok_src": 0,
            "n_src": len(cfg.get("sources", [])),
            "lines_in": 0,
            "out": 0,
            "secs": 0.0,
            "state": "失败",
            "state_mark": MARK_FAIL,
            # 每个格式的产物信息，运行结束时汇总成 README
            "formats": [],
        }

    def _stage_download(self, cfg, record, name):
        """
        下载阶段：把源抓回来，返回原始行。

        记两件事给总表：成功源数、原始行数。
        返回 None（而不是空列表）表示一个源都没成功，
        和"上游给的就是空文件"区分开。
        """
        raw_data, source_results = download_sources(
            cfg.get("sources", []), scope=name
        )

        # 下载器只负责抓取和整理结果，打印统一由这里做
        record["ok_src"] = sum(1 for r in source_results if r["ok"])
        record["lines_in"] = sum(r["lines"] for r in source_results)
        Logger.download_summary(source_results)

        if not raw_data:
            Logger.task_no_output(name)
            return None
        return raw_data

    @staticmethod
    def _stage_parse(processor, cfg, raw_data, record):
        """
        解析阶段：清洗、去重、过滤、排序，都在 processor 里做完。

        这里只把统计交给日志、把产出条数记进 record。
        processor 按阶段传进来（rule 用 process_rules，
        rewrite 用 process_rewrites），manager 不关心是哪一个。
        """
        final_data, stats = processor(cfg, raw_data)
        Logger.parse_summary(stats)
        record["out"] = len(final_data)
        return final_data

    def _stage_convert(self, cfg, data, category, record, name, started, writes):
        """
        转换 + 写入：每种输出格式各走一遍。

        两个阶段合成一个方法，因为对使用者来说是一件事——
        "这个规则集在两个客户端上分别生成了什么"。

        writes 由调用方传进来、这里往里追加：万一中途抛异常，
        调用方手里已经包含前面写成功的格式，状态判定和 README 才不会漏掉它们。
        """
        convert_rows = []

        # 顺序直接来自配置里 formats 的书写顺序，不另排序
        for fmt, fmt_params in cfg["formats_data"].items():
            row = self._dispatch_write(cfg, data, fmt, fmt_params, category)
            convert_rows.append(
                {
                    "format": fmt,
                    "rules": row["rules"],
                    "files": row["files"],
                    "dropped": row["dropped"],
                    "ok": row["ok"],
                    "error": row["error"],
                    "scope": name,
                }
            )
            writes.append(row)

        # 产物信息是"写成功一个文件才有一条"，所以放在全部写完之后收集
        self._collect_artifacts(record, writes, category)

        Logger.convert_summary(convert_rows)
        Logger.write_summary(convert_rows, time.time() - started)

    @staticmethod
    def _collect_artifacts(record, writes, category):
        """
        把写入成功的文件登记进任务记录。

        按文件记而不是按规则集记：一个 formatter 可能产出多个文件
        （Clash 固定三个），甚至写到不同目录。由 reporter 汇总 README 时
        再按"规则集"合并回去。
        """
        for row in writes:
            for art in row["artifacts"]:
                record["formats"].append(
                    {
                        "category": category,
                        "client_dir": art["client_dir"],
                        "collection": record["collection"],
                        "rules": art["rules"],
                        "updated": art["updated"],
                        "files": [art["path"]],
                    }
                )

    # ==================================================================
    # 写入
    #
    # formatter 决定写哪些文件、文件里放什么；manager 只管写并攒结果。
    # 所以这里没有客户端相关的判断，加新客户端时这两个方法一行都不用改。
    # ==================================================================

    @staticmethod
    def _new_format_row(fmt):
        """
        单个格式的写入结果，初始是"没写成"。

        和 _new_record 一个思路：先按失败写，只有真写成功才改，
        中途退出就不会被误判成成功。
        """
        return {
            "format": fmt,
            "ok": False,
            "error": None,
            "files": 0,
            "rules": 0,
            "dropped": 0,
            "paths": [],
            "artifacts": [],
        }

    def _dispatch_write(self, cfg, data, fmt, fmt_params, category):
        """
        让翻译器产出文件清单，然后逐个交给写盘模块。

        顺序：找翻译器 -> 拿文件清单 -> 算转换丢弃数 -> 逐个写。
        """
        name = cfg.get("name", "Unknown")
        row = self._new_format_row(fmt)

        # 配置里写了这个格式但程序没有对应实现：报出来，这个格式按失败处理
        formatter = AVAILABLE_FORMATTERS.get(category, {}).get(fmt)
        if not formatter:
            Logger.problem("error", Logger.msg("NO_FORMATTER", format=fmt), scope=name)
            return row

        # policy 和 header_lines 是 loader 展开好的，原样传，
        # 具体怎么用是各客户端自己的事
        outputs = formatter.format_rules(
            data,
            cfg["collection"],
            policy=fmt_params.get("policy", "Default"),
            header_lines=fmt_params.get("header_lines", []),
        ) or []

        # 转换丢弃数 = 交进来的条数 - 真正拼进文件的条数。
        # 条数优先用 formatter 给的 rule_count：只有它知道哪些行算一条规则。
        # 旧写法靠"含逗号"去数，遇到没有逗号的写法（例如重写规则）会全部算成丢弃。
        # 没提供 rule_count 时才退回按逗号数。
        produced = 0
        for item in outputs:
            if "rule_count" in item:
                produced += item["rule_count"]
            else:
                produced += sum(1 for line in item.get("content", []) if "," in line)
        row["dropped"] = max(0, len(data) - produced)

        # 不因一个文件失败就中断：其它文件能写还是要写，
        # 最后把"是否全部成功"和"第一条错误"一起交给日志。
        all_ok = True
        first_error = None
        for item in outputs:
            error = self._write_one(item, cfg, category, fmt, name, row)
            if error:
                all_ok = False
                first_error = first_error or error

        row["ok"] = all_ok
        row["error"] = first_error

        # 写失败的原因要进问题清单：否则终端只看到状态不对，
        # CI 里连状态都只有一行统计，谁也不知道为什么没写成。
        if first_error:
            Logger.problem("error", first_error, scope=name)

        return row

    def _write_one(self, item, cfg, category, fmt, name, row):
        """
        写一个文件，把结果累加进 row。

        返回 None 表示写成；返回文案表示没写成（冲突或写盘失败）。
        调用方只关心"有没有错、第一条错是什么"，所以这里不抛异常。
        """
        # 键里带上 category：rule 和 rewrite 是两个不同的输出根目录，
        # 各自都有 QuantumultX/，同名文件并不冲突。
        key = (category, item["dir"], item["filename"])

        # 同一客户端目录下文件名必须唯一，否则用户会拿到两个分不清的规则集，
        # 所以第二个直接拒绝写入（不是覆盖）
        owner = self._written.get(key)
        if owner is not None:
            return Logger.msg(
                "OUTPUT_CONFLICT",
                path=f"{item['dir']}/{item['filename']}",
                owner=owner,
                format=fmt,
            )

        # writer 自己会判断内容有没有变：没变就不动文件，UPDATED 也不推进
        ok, error, path, updated = write_output(
            project_root=self.project_root,
            category=category,
            sub_path=cfg.get("__sub_path__", ""),
            cfg=cfg,
            item=item,
        )
        if not ok:
            return f"{Logger.msg('WRITE_FAIL', format=fmt)}（{error}）"

        # 写成功才登记，写失败的不该白占名字，后面的规则集还要用
        self._written[key] = name

        # 条数优先用翻译器给的 rule_count，没给才退回按逗号数
        rules = item.get("rule_count")
        if rules is None:
            rules = sum(1 for line in item.get("content", []) if "," in line)
        row["files"] += 1
        row["rules"] += rules
        row["paths"].append(path)
        row["artifacts"].append(
            {
                "client_dir": item["dir"],
                "rules": rules,
                "updated": updated,
                "path": os.path.relpath(path, self.project_root),
            }
        )
        return None

    # ==================================================================
    # 状态报告
    # ==================================================================

    def _write_reports(self):
        """写每个客户端目录下的 README：订阅地址、条数、最后变更时间。"""
        artifacts = [f for r in self.records for f in r.get("formats", [])]
        if not artifacts:
            return

        ok = sum(1 for r in self.records if r["state"] == "成功")
        try:
            write_client_readmes(
                project_root=self.project_root,
                artifacts=artifacts,
                run_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ok=ok,
                total=len(self.records),
            )
        except OSError as error:  # 报告写不出来不该中断整个运行
            Logger.problem("error", f"状态文件写入失败：{error}")

    # ==================================================================
    # 状态判定
    # ==================================================================

    @staticmethod
    def _judge(record, writes):
        """
        判定任务状态。

        成功：所有源都成功、所有格式都写成功，而且确实产出了规则
        失败：一个源都没成功
        警告：介于两者之间，或者下载成功但一条规则都没剩下
        """
        write_ok = sum(1 for w in writes if w["ok"])
        write_all_ok = writes and write_ok == len(writes)

        # 配置里没写输出格式：不是源的问题，是"这个规则集不输出"，记警告
        if record.get("no_format"):
            return "警告", MARK_WARN

        if record["ok_src"] == 0:
            return "失败", MARK_FAIL

        # 产出了 0 条不能算成功：源可能空了、格式变了、或者被过滤光了，
        # 这些都该有人看一眼，不能因为"下载成功"就报绿。
        if record["out"] == 0:
            return "警告", MARK_WARN

        if record["ok_src"] == record["n_src"] and write_all_ok:
            return "成功", MARK_OK
        return "警告", MARK_WARN
