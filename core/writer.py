# core/writer.py

import os
from datetime import datetime
from collections import defaultdict

from core.constants import (
    PROJECT_AUTHOR,
    PROJECT_REPO,
    RULE_TYPE_PRIORITY,
    DEFAULT_PRIORITY,
    MSG_ERROR,
    MSG_INFO,
)
from core.logger import Logger


def write_output(
    project_root,
    category,
    subdir_name,
    cfg,
    rules,
    comment_symbol="#",
    file_extension="list",
    sub_path="",
    filename_suffix="",
) -> bool:
    """
    [文件写入器]

    负责创建目录并写入文件。
    所有的日志输出（成功/失败）均使用 Logger 的变量。
    """
    output_dir = os.path.join(project_root, category, subdir_name, sub_path)

    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            # [清洗点] 创建目录失败
            msg = f"{Logger.WORD_DIR_FAIL}: {output_dir} ({e})"
            Logger.log_generic_message(MSG_ERROR, msg)
            return False

    clean_ext = file_extension.lstrip(".")
    base_name = cfg.get("output_filename", "Output")
    filename = f"{base_name}{filename_suffix}.{clean_ext}"
    path = os.path.join(output_dir, filename)

    count = defaultdict(int)
    valid_rule_count = 0

    for r in rules:
        r_stripped = r.strip()
        if not r_stripped or r_stripped.startswith(comment_symbol):
            continue
        if "," in r:
            rule_type = r.split(",", 1)[0].strip().upper()
            if rule_type:
                count[rule_type] += 1
                valid_rule_count += 1

    updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"{comment_symbol} NAME: {cfg.get('name', 'Unknown')}\n")
            f.write(f"{comment_symbol} AUTHOR: {PROJECT_AUTHOR}\n")
            f.write(f"{comment_symbol} REPO: {PROJECT_REPO}\n")
            f.write(f"{comment_symbol} UPDATED: UTC+8 {updated}\n")

            sorted_types = sorted(
                count.keys(), key=lambda k: RULE_TYPE_PRIORITY.get(k, DEFAULT_PRIORITY)
            )

            for k in sorted_types:
                if count[k] > 0:
                    f.write(f"{comment_symbol} {k}: {count[k]}\n")

            f.write(f"{comment_symbol} TOTAL: {valid_rule_count}\n")

            for line in rules:
                f.write(line + "\n")

        # [清洗点] 写入成功
        try:
            display_path = os.path.relpath(path)
        except ValueError:
            display_path = path

        msg = f"{Logger.WORD_WRITE_OK}: {display_path}"
        Logger.log_generic_message(MSG_INFO, msg)
        return True

    except IOError as e:
        # [清洗点] 写入失败
        msg = f"{Logger.WORD_WRITE_FAIL}: {path} ({e})"
        Logger.log_generic_message(MSG_ERROR, msg)
        return False
