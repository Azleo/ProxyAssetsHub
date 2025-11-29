# core/logger.py

import sys
import time

from core.constants import (
    LOG_LEVEL_DEFAULT,
    LOG_LEVEL_INFO,
    LOG_LEVEL_DEBUG,
    LOG_STYLE_CI,
    MSG_ERROR,
    MSG_WARN,
    MSG_INFO,
    MSG_DEBUG,
)


class Logger:
    """
    [核心模块：业务型日志器 V5]

    这是系统的“语言中心”。

    【核心特性】
    1. 字典化 (Dictionary-based): 所有的中文提示语都提取到了 TEXT 字典中。
    2. 变量映射 (Mapping): 通过类变量 (WORD_*) 公开给其他模块使用，消除硬编码。
    3. 统一门卫 (_print): 集中控制日志的显示与否。
    """

    # --- 核心开关 ---
    show_detail = False
    show_debug = False
    is_ci_mode = False

    # =================================================================
    # 📖 [配置中心] 文案大字典
    # 所有的汉字都必须住在这里，不能流浪在外面。
    # =================================================================
    TEXT = {
        # --- 核心名词 ---
        "RULE": "规则",
        "REWRITE": "重写",
        "TASK": "任务",
        "QUEUE": "队列",
        "SOURCE_DATA": "源数据",
        "ROWS": "行",
        # --- 动作与状态 ---
        "FOUND": "发现",
        "START": "准备开始",
        "PROCESS": "处理",
        "DOWNLOAD": "下载",
        "WRITING": "正在写入",
        "WRITE_OK": "已写入",
        "DONE": "耗时",
        "SUCCESS": "成功",
        "FAIL": "失败",
        "FINISH": "全部完成",
        # --- 汇总与统计 ---
        "SUMMARY": "执行结果汇总",
        "STATS": "统计面板",
        "TOTAL": "总数",
        "Problem": "问题",
        "DATA_DETAIL": "数据详情",
        # --- 错误与警告 (Loader/Manager/Downloader 专用) ---
        "FILE_NOT_FOUND": "文件未找到",
        "YAML_ERR": "YAML格式错误",
        "CONFIG_EMPTY": "配置文件为空",
        "NAME_NOT_SET": "未设置 'name' 字段，已使用文件名代替",
        "CONFIG_DISABLED": "配置未启用 (enabled: false)",
        "ENABLED_TYPE_ERR": "enabled 类型错误",
        "ENABLED_UNKNOWN": "enabled 字段格式未知",
        "SOURCES_NOT_LIST": "'sources' 必须是列表格式",
        "SOURCES_EMPTY": "有效 source 列表为空",
        "NO_OUTPUT_FMT": "无输出格式",
        "DIR_FAIL": "创建目录失败",
        "WRITE_FAIL": "写入文件失败",
        "NET_ERR": "网络错误",
        "PROCESS_FAIL": "处理失败",
        "CRASH": "崩溃",
        "EXCEPTION": "异常崩溃",
        # --- 标签 ---
        "DEBUG": "调试",
        "INFO": "信息",
        "WARN": "警告",
        "ERROR": "失败",
    }

    # [数据键名翻译字典]
    # 把 processor 返回的英文 key 翻译成中文
    KEYS = {
        "source": "原始数据",
        "vip": "VIP添加",
        "invalid": "无效行数",
        "dup_vip": "VIP重复",
        "dup_src": "源内重复",
        "filtered": "过滤移除",
        "total": "有效产出",
        "valid": "有效规则",
    }

    # =================================================================
    # 🔗 [变量映射层]
    # 供其他模块调用，例如 Logger.WORD_SUCCESS
    # =================================================================
    WORD_RULE = TEXT["RULE"]
    WORD_REWRITE = TEXT["REWRITE"]
    WORD_TASK = TEXT["TASK"]
    WORD_QUEUE = TEXT["QUEUE"]
    WORD_SOURCE_DATA = TEXT["SOURCE_DATA"]
    WORD_ROWS = TEXT["ROWS"]

    WORD_FOUND = TEXT["FOUND"]
    WORD_START = TEXT["START"]
    WORD_PROCESS = TEXT["PROCESS"]
    WORD_DOWNLOAD = TEXT["DOWNLOAD"]
    WORD_WRITING = TEXT["WRITING"]
    WORD_WRITE_OK = TEXT["WRITE_OK"]
    WORD_DONE = TEXT["DONE"]
    WORD_SUCCESS = TEXT["SUCCESS"]
    WORD_FAIL = TEXT["FAIL"]
    WORD_FINISH = TEXT["FINISH"]

    WORD_SUMMARY = TEXT["SUMMARY"]
    WORD_STATS = TEXT["STATS"]
    WORD_TOTAL = TEXT["TOTAL"]
    WORD_PROBLEM = TEXT["Problem"]
    WORD_DATA_DETAIL = TEXT["DATA_DETAIL"]

    # 错误映射
    WORD_FILE_NOT_FOUND = TEXT["FILE_NOT_FOUND"]
    WORD_YAML_ERR = TEXT["YAML_ERR"]
    WORD_CONFIG_EMPTY = TEXT["CONFIG_EMPTY"]
    WORD_NAME_NOT_SET = TEXT["NAME_NOT_SET"]
    WORD_CONFIG_DISABLED = TEXT["CONFIG_DISABLED"]
    WORD_ENABLED_TYPE_ERR = TEXT["ENABLED_TYPE_ERR"]
    WORD_ENABLED_UNKNOWN = TEXT["ENABLED_UNKNOWN"]
    WORD_SOURCES_NOT_LIST = TEXT["SOURCES_NOT_LIST"]
    WORD_SOURCES_EMPTY = TEXT["SOURCES_EMPTY"]
    WORD_NO_OUTPUT_FMT = TEXT["NO_OUTPUT_FMT"]
    WORD_DIR_FAIL = TEXT["DIR_FAIL"]
    WORD_WRITE_FAIL = TEXT["WRITE_FAIL"]
    WORD_NET_ERR = TEXT["NET_ERR"]
    WORD_PROCESS_FAIL = TEXT["PROCESS_FAIL"]
    WORD_CRASH = TEXT["CRASH"]
    WORD_EXCEPTION = TEXT["EXCEPTION"]

    WORD_DEBUG = TEXT["DEBUG"]
    WORD_INFO = TEXT["INFO"]
    WORD_WARN = TEXT["WARN"]
    WORD_ERROR = TEXT["ERROR"]

    @classmethod
    def init(cls, level=LOG_LEVEL_DEFAULT, style="human"):
        """初始化开关"""
        if style == LOG_STYLE_CI:
            cls.is_ci_mode = True

        if level >= LOG_LEVEL_DEBUG:
            cls.show_detail = True
            cls.show_debug = True
        elif level >= LOG_LEVEL_INFO:
            cls.show_detail = True

    @classmethod
    def _print(cls, text, level=LOG_LEVEL_DEFAULT, use_flush=True):
        """核心打印门卫"""
        if level == LOG_LEVEL_DEBUG and not cls.show_debug:
            return
        if level == LOG_LEVEL_INFO and not cls.show_detail:
            return
        print(text, flush=use_flush)

    # =================================================================
    # 📢 [业务层] 喊话方法
    # =================================================================

    @classmethod
    def log_app_start(cls):
        """程序启动"""
        if cls.is_ci_mode:
            cls._print("--- ProxyAssetsHub Start ---")
        else:
            cls._print(f"\n{'='*20} ProxyAssetsHub 启动 {'='*20}")

    @classmethod
    def log_phase_start(cls, phase_name, task_count):
        """阶段开始"""
        if task_count == 0:
            return

        if phase_name == "RULE":
            display_name = cls.WORD_RULE
        elif phase_name == "REWRITE":
            display_name = cls.WORD_REWRITE
        else:
            display_name = phase_name

        if cls.is_ci_mode:
            cls._print(f"--- Phase: {phase_name} ({task_count}) ---")
        else:
            cls._print(
                f"\n[{display_name:<4}] {cls.WORD_FOUND} {task_count} 个{cls.WORD_TASK}，{cls.WORD_START}..."
            )

    @classmethod
    def log_task_start(cls, index, total, name):
        """任务开始"""
        if cls.is_ci_mode:
            cls._print(f"[TASK] {name}")
        else:
            cls._print(
                f"  -> [{index}/{total}] {cls.WORD_PROCESS}: {name}",
                level=LOG_LEVEL_INFO,
            )

    @classmethod
    def log_task_done(cls, duration):
        """任务耗时"""
        cls._print(f"     ({cls.WORD_DONE}: {duration:.2f}s)", level=LOG_LEVEL_INFO)

    @classmethod
    def log_download_start(cls, count):
        """下载开始"""
        cls._print(f"     {cls.WORD_DOWNLOAD}: {count} 个{cls.WORD_SOURCE_DATA}...", level=LOG_LEVEL_INFO)

    @classmethod
    def log_write_job(cls, fmt):
        """写入开始"""
        cls._print(f"     {cls.WORD_WRITING}: {fmt}...", level=LOG_LEVEL_DEBUG)

    @classmethod
    def log_final_summary(cls, total_time, stats, errors):
        """汇总报告"""
        if not cls.is_ci_mode:
            cls._print(f"\n{'-'*20} {cls.WORD_SUMMARY} {'-'*20}")

        if errors:
            cls._print(f"{cls.WORD_FOUND} {len(errors)} 个{cls.WORD_PROBLEM}:")
            for i, err in enumerate(errors, 1):
                cls._print(f"  {i}. {err}")

        if stats:
            cls._print(f"\n[{cls.WORD_STATS}]:")
            for cat, s in stats.items():
                if cat.upper() == "RULE":
                    w_cat = cls.WORD_RULE
                elif cat.upper() == "REWRITE":
                    w_cat = cls.WORD_REWRITE
                else:
                    w_cat = cat.upper()

                line = (
                    f"  {w_cat:<10} | "
                    f"{cls.WORD_TOTAL}: {s['total']:<4} | "
                    f"{cls.WORD_SUCCESS}: {s['success']:<4} | "
                    f"{cls.WORD_FAIL}: {s['fail']:<4}"
                )
                cls._print(line)

        cls._print(f"\n{cls.WORD_FINISH} ({cls.WORD_DONE}: {total_time:.2f}s)")

    @classmethod
    def log_generic_message(cls, msg_type, text, source=""):
        """通用消息"""
        prefix = f"[{source}] " if source else ""

        if msg_type == MSG_ERROR:
            tag = cls.WORD_ERROR
            if cls.is_ci_mode:
                cls._print(f"::error::{prefix}{text}")
            else:
                cls._print(f"XX {tag}: {prefix}{text}")

        elif msg_type == MSG_WARN:
            tag = cls.WORD_WARN
            if cls.is_ci_mode:
                cls._print(f"::warning::{prefix}{text}")
            else:
                cls._print(f"!! {tag}: {prefix}{text}")

        elif msg_type == MSG_DEBUG:
            tag = cls.WORD_DEBUG
            cls._print(f"  [{tag}] {prefix}{text}", level=LOG_LEVEL_DEBUG)

        elif msg_type == MSG_INFO:
            tag = cls.WORD_INFO
            cls._print(f"  [{tag}] {prefix}{text}", level=LOG_LEVEL_INFO)

    @classmethod
    def log_stats_data(cls, stats):
        """数据详情"""
        if not stats:
            return

        cls._print(f"     [{cls.WORD_DATA_DETAIL}]:", level=LOG_LEVEL_DEBUG)

        for key, val in stats.items():
            label = cls.KEYS.get(key, key)
            cls._print(f"       {label:<10}: {val}", level=LOG_LEVEL_DEBUG)

    @classmethod
    def debug(cls, message, tag=""):
        """兼容接口"""
        cls._print(f"  [DEBUG] [{tag}] {message}", level=LOG_LEVEL_DEBUG)
