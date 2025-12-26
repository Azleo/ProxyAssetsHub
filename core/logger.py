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
    [核心模块：业务型日志器 V5 - Modern Emoji Edition]

    这是系统的“语言中心”。
    """

    # --- 核心开关 ---
    show_detail = False
    show_debug = False
    is_ci_mode = False

    # --- 视觉素材 (新) ---
    ICONS = {
        "APP": "🚀",
        "PHASE": "📌",
        "TASK": "📦",
        "DOWN": "📥",
        "PROC": "⚙️",
        "WRITE": "💾",
        "DONE": "✨",
        "SUCCESS": "✅",
        "FAIL": "❌",
        "WARN": "⚠️",
        "INFO": "ℹ️",
        "DEBUG": "🐛",
        "TREE_BRANCH": "  ├──",
        "TREE_END": "  └──",
        "TREE_SUB": "  │   ",
        "ARROW": "➔",
    }

    # --- ANSI 颜色代码 (新) ---
    COLORS = {
        "RESET": "\033[0m",
        "RED": "\033[31m",
        "GREEN": "\033[32m",
        "YELLOW": "\033[33m",
        "BLUE": "\033[34m",
        "CYAN": "\033[36m",
        "GRAY": "\033[90m",
    }

    # =================================================================
    # 📖 [配置中心] 文案大字典
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
        "START": "启动",
        "PROCESS": "处理",
        "DOWNLOAD": "下载",
        "WRITING": "写入",
        "WRITE_OK": "保存成功",
        "DONE": "完成",
        "SUCCESS": "成功",
        "FAIL": "失败",
        "FINISH": "全部完成",
        # --- 汇总与统计 ---
        "SUMMARY": "执行结果汇总",
        "STATS": "统计面板",
        "TOTAL": "总计",
        "Problem": "个问题",
        "DATA_DETAIL": "数据详情",
        # --- 错误与警告 ---
        "FILE_NOT_FOUND": "文件未找到",
        "YAML_ERR": "YAML格式错误",
        "CONFIG_EMPTY": "配置为空",
        "NAME_NOT_SET": "未命名",
        "CONFIG_DISABLED": "已禁用",
        "ENABLED_TYPE_ERR": "enabled类型错误",
        "ENABLED_UNKNOWN": "enabled未知",
        "SOURCES_NOT_LIST": "source非列表",
        "SOURCES_EMPTY": "source为空",
        "NO_OUTPUT_FMT": "无输出格式",
        "DIR_FAIL": "创建目录失败",
        "WRITE_FAIL": "写入失败",
        "NET_ERR": "网络错误",
        "PROCESS_FAIL": "处理失败",
        "CRASH": "崩溃",
        "EXCEPTION": "异常",
        # --- 标签 ---
        "DEBUG": "调试",
        "INFO": "信息",
        "WARN": "警告",
        "ERROR": "错误",
    }

    # [数据键名翻译字典]
    KEYS = {
        "source": "原始",
        "vip": "VIP",
        "invalid": "无效",
        "dup_vip": "VIP重复",
        "dup_src": "源重复",
        "filtered": "过滤",
        "total": "产出",
        "valid": "有效",
    }

    # =================================================================
    # 🔗 [变量映射层]
    # 这一部分必须完整保留，否则外部模块调用时会报错 AttributeError
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

    # --- 错误映射 (Loader等模块依赖这些变量) ---
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

    @classmethod
    def _c(cls, text, color_key):
        """(内部工具) 给文本上色"""
        if cls.is_ci_mode or color_key not in cls.COLORS:
            return text
        return f"{cls.COLORS[color_key]}{text}{cls.COLORS['RESET']}"

    # =================================================================
    # 📢 [业务层] 喊话方法 (UI重构版)
    # =================================================================

    @classmethod
    def log_app_start(cls):
        """程序启动"""
        if cls.is_ci_mode:
            cls._print("--- ProxyAssetsHub Start ---")
        else:
            title = cls._c("ProxyAssetsHub 启动", "CYAN")
            cls._print(f"\n{cls.ICONS['APP']} {title}\n")

    @classmethod
    def log_phase_start(cls, phase_name, task_count):
        """阶段开始"""
        if task_count == 0:
            return

        display_name = phase_name
        if phase_name == "RULE":
            display_name = cls.TEXT["RULE"]
        elif phase_name == "REWRITE":
            display_name = cls.TEXT["REWRITE"]

        if cls.is_ci_mode:
            cls._print(f"--- Phase: {phase_name} ({task_count}) ---")
        else:
            msg = f"{cls.ICONS['PHASE']} {display_name}{cls.TEXT['TASK']} (共 {task_count} 个)"
            cls._print(cls._c(msg, "BLUE"))

    @classmethod
    def log_task_start(cls, index, total, name):
        """任务开始 (树根)"""
        if cls.is_ci_mode:
            cls._print(f"[TASK] {name}")
        else:
            idx_str = f"[{index}/{total}]"
            cls._print(f"\n{cls.ICONS['TASK']} {cls._c(idx_str, 'YELLOW')} {cls._c(name, 'GREEN')}")

    @classmethod
    def log_download_start(cls, count):
        """下载开始 (树枝)"""
        msg = f"{cls.ICONS['TREE_BRANCH']} {cls.ICONS['DOWN']} {cls.WORD_DOWNLOAD}: {count} 个{cls.TEXT['SOURCE_DATA']}..."
        cls._print(msg, level=LOG_LEVEL_INFO)

    @classmethod
    def log_stats_data(cls, stats):
        """数据详情 (树枝 - 扁平化显示)"""
        if not stats:
            return
        
        parts = []
        priority_keys = ["source", "filtered", "dup_src", "total"]
        
        for k in priority_keys:
            if k in stats:
                label = cls.KEYS.get(k, k)
                val = stats[k]
                if val > 0 or k in ["source", "total"]:
                    parts.append(f"[{label}: {val}]")
        
        if parts:
            flow_str = f" {cls.ICONS['ARROW']} ".join(parts)
            msg = f"{cls.ICONS['TREE_BRANCH']} {cls.ICONS['PROC']} {cls.TEXT['PROCESS']}: {cls._c(flow_str, 'GRAY')}"
            cls._print(msg, level=LOG_LEVEL_DEBUG)

    @classmethod
    def log_write_job(cls, fmt):
        """写入开始 (树枝)"""
        msg = f"{cls.ICONS['TREE_BRANCH']} {cls.ICONS['WRITE']} {cls.WORD_WRITING}: {fmt}..."
        cls._print(msg, level=LOG_LEVEL_DEBUG)

    @classmethod
    def log_generic_message(cls, msg_type, text, source=""):
        """通用消息 (自动适配树状结构)"""
        prefix_tree = cls.ICONS['TREE_SUB'] + " " 
        prefix_source = f"[{source}] " if source else ""
        
        if msg_type == MSG_ERROR:
            tag = cls.ICONS['FAIL']
            content = cls._c(f"{prefix_source}{text}", "RED")
            if cls.is_ci_mode:
                cls._print(f"::error::{prefix_source}{text}")
            else:
                cls._print(f"{prefix_tree}{tag} {content}")

        elif msg_type == MSG_WARN:
            tag = cls.ICONS['WARN']
            content = cls._c(f"{prefix_source}{text}", "YELLOW")
            if cls.is_ci_mode:
                cls._print(f"::warning::{prefix_source}{text}")
            else:
                cls._print(f"{prefix_tree}{tag} {content}")

        elif msg_type == MSG_INFO:
            tag = cls.ICONS['SUCCESS'] 
            # 只有明确包含“保存成功”字样的信息才标绿，其他为灰
            color = "GREEN" if cls.TEXT['WRITE_OK'] in text else "GRAY"
            content = cls._c(f"{prefix_source}{text}", color)
            cls._print(f"{prefix_tree}{tag} {content}", level=LOG_LEVEL_INFO)

        elif msg_type == MSG_DEBUG:
            tag = cls.ICONS['DEBUG']
            content = cls._c(f"{prefix_source}{text}", "GRAY")
            cls._print(f"{prefix_tree}{tag} {content}", level=LOG_LEVEL_DEBUG)

    @classmethod
    def log_task_done(cls, duration):
        """任务耗时 (树底)"""
        time_str = f"{duration:.2f}s"
        msg = f"{cls.ICONS['TREE_END']} {cls.ICONS['DONE']} {cls.WORD_DONE} ({cls.WORD_DONE}: {cls._c(time_str, 'CYAN')})"
        cls._print(msg, level=LOG_LEVEL_INFO)

    @classmethod
    def log_final_summary(cls, total_time, stats, errors):
        """汇总报告 (卡片式)"""
        if cls.is_ci_mode:
            cls._print(f"\n[SUMMARY] Done in {total_time:.2f}s")
            return

        print("")
        line = cls._c("-" * 40, "GRAY")
        cls._print(line)
        title = f"{cls.ICONS['APP']} {cls.WORD_SUMMARY}"
        cls._print(f"{title}")
        cls._print(line)

        if errors:
            cls._print(f"{cls.ICONS['FAIL']} {cls.WORD_FOUND} {len(errors)} {cls.TEXT['Problem']}:")
            for i, err in enumerate(errors, 1):
                cls._print(cls._c(f"  {i}. {err}", "RED"))
            cls._print(line)

        if stats:
            for cat, s in stats.items():
                cat_name = cat.upper()
                if cat_name == "RULE": cat_name = cls.TEXT['RULE']
                if cat_name == "REWRITE": cat_name = cls.TEXT['REWRITE']
                
                part1 = f"{cat_name:<6}"
                part2 = f"{cls.WORD_TOTAL}: {s['total']}"
                part3 = f"{cls.WORD_SUCCESS}: {cls._c(str(s['success']), 'GREEN')}"
                
                fail_color = "RED" if s['fail'] > 0 else "GRAY"
                part4 = f"{cls.WORD_FAIL}: {cls._c(str(s['fail']), fail_color)}"
                
                cls._print(f"  {part1} | {part2} | {part3} | {part4}")

        cls._print(line)
        end_msg = f"{cls.ICONS['DONE']} {cls.WORD_FINISH} : {cls._c(f'{total_time:.2f}s', 'CYAN')}"
        cls._print(end_msg)
        cls._print("")

    @classmethod
    def debug(cls, message, tag=""):
        """兼容接口"""
        prefix = cls.ICONS['TREE_SUB'] + " "
        tag_str = f"[{tag}] " if tag else ""
        content = cls._c(f"{tag_str}{message}", "GRAY")
        cls._print(f"{prefix}{cls.ICONS['DEBUG']} {content}", level=LOG_LEVEL_DEBUG)