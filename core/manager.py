# core/manager.py

import os
import time
import traceback

from core.loader import load_all_configs
from core.downloader import download_sources
from core.writer import write_output
from core.logger import Logger
from core.constants import (
    MSG_ERROR,
    MSG_WARN,
    LOG_LEVEL_DEFAULT,
    LOG_LEVEL_INFO,
    LOG_LEVEL_DEBUG,
    LOG_STYLE_HUMAN,
)

from core.rule.processor_rule import process_rules
from core.rewrite.processor_rewrite import process_rewrites
from core.rule import formatter_rule_quantumultx, formatter_rule_loon
from core.rewrite import formatter_rewrite_quantumultx, formatter_rewrite_loon

AVAILABLE_FORMATTERS = {
    "rule": {
        "quantumultx": formatter_rule_quantumultx,
        "loon": formatter_rule_loon,
    },
    "rewrite": {
        "quantumultx": formatter_rewrite_quantumultx,
        "loon": formatter_rewrite_loon,
    },
}

PIPELINE_HANDLERS = {
    "rule": process_rules,
    "rewrite": process_rewrites,
}

EXECUTION_ORDER = ["rule", "rewrite"]


class Manager:
    """
    [核心模块：任务调度器]

    负责整个程序的流程控制。
    所有的日志输出都委托给 Logger，确保文案统一。
    """

    def __init__(self, level=LOG_LEVEL_DEFAULT, style=LOG_STYLE_HUMAN):
        self.project_root = os.getcwd()
        Logger.init(level, style)

        self.debug_mode = level >= LOG_LEVEL_DEBUG
        self.summary_errors = []
        self.stats = {}

    def run(self):
        """程序入口"""
        start_time = time.time()
        Logger.log_app_start()

        for category in EXECUTION_ORDER:
            self._run_phase(category)

        duration = time.time() - start_time
        Logger.log_final_summary(duration, self.stats, self.summary_errors)

    def _run_phase(self, category):
        """执行单个阶段"""
        processor_func = PIPELINE_HANDLERS.get(category)
        if not processor_func:
            return

        # 1. 加载配置
        configs = load_all_configs(subdir=category)

        total = len(configs)
        Logger.log_phase_start(category.upper(), total)

        if total == 0:
            return

        success_count = 0
        fail_count = 0

        # 2. 遍历任务
        for i, cfg in enumerate(configs, 1):
            name = cfg.get("name", "Unknown")
            Logger.log_task_start(i, total, name)

            task_start = time.time()
            try:
                if self._process_single_task(cfg, category, processor_func):
                    success_count += 1
                else:
                    fail_count += 1
                    # [清洗点] 记录处理失败
                    err_msg = f"{name}: {Logger.WORD_PROCESS_FAIL}"
                    if not self.summary_errors or name not in self.summary_errors[-1]:
                        self.summary_errors.append(err_msg)
            except Exception as e:
                fail_count += 1
                # [清洗点] 异常崩溃
                msg = f"{Logger.WORD_EXCEPTION}: {e}"
                Logger.log_generic_message(MSG_ERROR, msg, source="SYSTEM")

                # 记录到汇总
                self.summary_errors.append(f"{name} ({Logger.WORD_CRASH}: {e})")

                if self.debug_mode:
                    traceback.print_exc()
            finally:
                Logger.log_task_done(time.time() - task_start)

        self.stats[category] = {
            "total": total,
            "success": success_count,
            "fail": fail_count,
        }

    def _process_single_task(self, cfg, category, processor_func):
        """处理单个任务"""
        name = cfg.get("name", "Unknown")
        formats_data = cfg.get("formats_data", {})

        if not formats_data:
            # [清洗点] 无输出格式
            Logger.log_generic_message(MSG_WARN, Logger.WORD_NO_OUTPUT_FMT, source=name)
            return False

        # --- 下载 ---
        sources = cfg.get("sources", [])
        Logger.log_download_start(len(sources))

        raw_data = download_sources(sources)
        if not raw_data:
            return False

        # --- 处理 ---
        final_data, stats = processor_func(cfg, raw_data)
        Logger.log_stats_data(stats)

        # --- 写入 ---
        all_ok = True
        for fmt, fmt_params in formats_data.items():
            Logger.log_write_job(fmt)
            if not self._dispatch_write(cfg, final_data, fmt, fmt_params, category):
                all_ok = False

        return all_ok

    def _dispatch_write(self, cfg, data, fmt, fmt_params, category):
        """分发写入"""
        formatters = AVAILABLE_FORMATTERS.get(category, {})
        formatter = formatters.get(fmt)

        if not formatter:
            return False

        dir_name = getattr(formatter, "DIR_NAME", fmt.capitalize())
        file_ext = getattr(formatter, "FILE_EXTENSION", "list")
        comment_sym = getattr(formatter, "COMMENT_SYMBOL", "#")

        policy = fmt_params.get("policy_tag", "Default")
        headers = fmt_params.get("header_lines", [])

        content = formatter.format_rules(data, policy_tag=policy, header_lines=headers)
        if not content:
            return False

        sub_path = cfg.get("__sub_path__", "")

        success = write_output(
            project_root=self.project_root,
            category=category,
            subdir_name=dir_name,
            cfg=cfg,
            rules=content,
            comment_symbol=comment_sym,
            file_extension=file_ext,
            sub_path=sub_path,
        )

        return success
