# core/loader.py

import os
import yaml
from typing import List, Dict, Tuple
from core.constants import MSG_ERROR, MSG_WARN, MSG_INFO, MSG_DEBUG
from core.logger import Logger


def _load_single_config(path: str) -> Dict | None:
    """
    读取并解析单个 YAML 文件。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
            if not cfg:
                # [清洗点] 配置文件为空
                Logger.log_generic_message(
                    MSG_ERROR, Logger.WORD_CONFIG_EMPTY, source=os.path.basename(path)
                )
                return None
            return cfg

    except FileNotFoundError:
        # [清洗点] 文件未找到
        Logger.log_generic_message(MSG_ERROR, Logger.WORD_FILE_NOT_FOUND, source=path)
        return None
    except yaml.YAMLError as e:
        # [清洗点] YAML 格式错误
        Logger.log_generic_message(
            MSG_ERROR, f"{Logger.WORD_YAML_ERR}: {e}", source=os.path.basename(path)
        )
        return None
    except Exception as e:
        Logger.log_generic_message(
            MSG_ERROR, f"Load Error: {e}", source=os.path.basename(path)
        )
        return None


def _preprocess_config(cfg: Dict) -> Dict | None:
    """
    预处理配置，检查必填项。
    """
    filename = cfg.get("__filename__", "UnknownFile")

    # 1. 检查 name
    if not cfg.get("name"):
        # [清洗点] 未设置名称
        Logger.log_generic_message(MSG_WARN, Logger.WORD_NAME_NOT_SET, source=filename)
        cfg["name"] = filename.replace(".yaml", "").replace(".yml", "")

    # 2. 检查 enabled
    raw_enabled = cfg.get("enabled")
    if raw_enabled is True:
        pass
    elif raw_enabled is False or raw_enabled is None:
        # [清洗点] 配置禁用
        Logger.log_generic_message(
            MSG_INFO, Logger.WORD_CONFIG_DISABLED, source=filename
        )
        return None
    elif isinstance(raw_enabled, str):
        # [清洗点] 类型错误
        msg = f"{Logger.WORD_ENABLED_TYPE_ERR} ({raw_enabled})"
        Logger.log_generic_message(MSG_ERROR, msg, source=filename)
        return None
    else:
        # [清洗点] 格式未知
        Logger.log_generic_message(
            MSG_ERROR, Logger.WORD_ENABLED_UNKNOWN, source=filename
        )
        return None

    # 3. 补充默认值
    cfg["final_policy_tag"] = cfg.get("output_filename", "Default")
    cfg["formats"] = [fmt.lower() for fmt in cfg.get("formats", [])]

    # 4. 标准化 Headers
    standardized_headers = {}
    for fmt, headers in cfg.get("custom_headers", {}).items():
        standardized_headers[fmt.lower()] = headers
    cfg["custom_headers"] = standardized_headers

    # 5. 校验 Sources
    raw_sources = cfg.get("sources", [])
    if raw_sources is None or not isinstance(raw_sources, list):
        # [清洗点] sources 不是列表
        Logger.log_generic_message(
            MSG_ERROR, Logger.WORD_SOURCES_NOT_LIST, source=filename
        )
        return None

    valid_sources = []
    for item in raw_sources:
        if isinstance(item, str) and item.strip():
            valid_sources.append(item.strip())

    if not valid_sources:
        # [清洗点] sources 为空
        Logger.log_generic_message(
            MSG_ERROR, Logger.WORD_SOURCES_EMPTY, source=filename
        )
        return None

    cfg["sources"] = valid_sources
    return cfg


def _build_formats_data(cfg: Dict) -> Dict:
    """打包格式化参数"""
    formats_data = {}
    for fmt in cfg.get("formats", []):
        header_data = cfg.get("custom_headers", {}).get(fmt, {})
        header_lines = header_data.get("header_lines", [])
        formats_data[fmt] = {
            "policy_tag": cfg["final_policy_tag"],
            "header_lines": header_lines,
        }
    cfg["formats_data"] = formats_data
    return cfg


def load_all_configs(subdir: str = "rule") -> List[Dict]:
    """主加载函数"""
    configs_dir = os.path.join(os.getcwd(), "configs", subdir)
    prepared_configs = []

    if not os.path.exists(configs_dir):
        # Debug 信息可以保留
        Logger.debug(f"Dir not found: {configs_dir}", tag="LOADER")
        return prepared_configs

    for file in os.listdir(configs_dir):
        if file.endswith((".yaml", ".yml")):
            path = os.path.join(configs_dir, file)

            cfg = _load_single_config(path)
            if not cfg:
                continue

            cfg["__filename__"] = file
            cfg = _preprocess_config(cfg)
            if cfg:
                cfg = _build_formats_data(cfg)
                prepared_configs.append(cfg)

    return prepared_configs
