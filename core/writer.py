# core/writer.py

import os
from collections import defaultdict
from datetime import datetime

from core.constants import (
    DEFAULT_PRIORITY,
    PROJECT_AUTHOR,
    PROJECT_REPO,
    RULE_TYPE_PRIORITY,
)


def _read_updated(text: str, prefix: str):
    """从文件内容里取出 UPDATED 记录的时间（去掉 UTC+8 前缀）。"""
    for line in text.splitlines():
        if line.startswith(prefix):
            value = line[len(prefix):].strip()
            return value.replace("UTC+8", "").strip()
    return None


def write_output(project_root, category, sub_path, cfg, item) -> tuple[bool, str | None, str | None, str | None]:
    """
    [写入阶段] 写出一个文件。

    要写什么由调用方完全决定，writer 不再猜文件名或目录：

        item = {
            "dir": 输出目录（例如 "Clash"）,
            "filename": 文件名（例如 "Direct_Domain.yaml"）,
            "content": 内容行列表,
            "header": 是否写标准头部,
            "comment": 头部用的注释符号,
        }

    返回 (是否成功, 失败原因, 文件路径, 该文件当前记录的更新时间)。

    关于更新时间：UPDATED 记录的是"这份规则最后一次实质性变化的时间"。
    算出来的内容和磁盘上的旧文件一致（忽略 UPDATED 那一行）时，
    直接返回、不碰文件，这样重复运行不会产生无意义的改动。
    """
    output_dir = os.path.join(project_root, category, item["dir"], sub_path)

    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            return False, f"{output_dir} ({e})", None, None

    path = os.path.join(output_dir, item["filename"])
    content_lines = item.get("content", [])
    want_header = item.get("header", True)
    comment_symbol = item.get("comment", "#")

    # ------------------------------------------------------------------
    # 先算出"不带时间戳"的完整内容，用来和磁盘上的旧文件比对。
    # ------------------------------------------------------------------
    body_lines = []

    if want_header:
        # 统计每类规则各有多少条，写在文件头部，方便人工检查
        count = defaultdict(int)
        valid_rule_count = 0

        for r in content_lines:
            r_stripped = r.strip()
            if not r_stripped or r_stripped.startswith(comment_symbol):
                continue

            # 类型分布只对"类型,值"这种形态有意义，
            # 其它形态（例如重写规则、Clash 的 payload: 结构行）没有类型可统计。
            if "," in r:
                raw_type_str = r.split(",", 1)[0].strip().upper()
                rule_type = raw_type_str.lstrip("-").strip()

                # 只有已知的规则类型才计入分布。重写规则那种自然语言行里
                # 也可能有逗号，但不是"类型,值"结构，不能当类型统计。
                if rule_type in RULE_TYPE_PRIORITY:
                    count[rule_type] += 1

        # 总条数优先用调用方给的：只有生成内容的人才真正知道哪些行算一条规则。
        # 靠内容特征去猜是猜不准的——Clash 的 YAML 里就有 payload: 这种结构行，
        # 既不是注释也不含逗号；rewrite 的行则根本没有逗号。
        # 没提供时退回"能识别出类型的行数"，兼容旧调用。
        rule_total = item.get("rule_count")
        if rule_total is None:
            rule_total = sum(count.values())
        valid_rule_count = rule_total

        body_lines = [
            f"{comment_symbol} NAME: {cfg.get('name', 'Unknown')}",
            f"{comment_symbol} AUTHOR: {PROJECT_AUTHOR}",
            f"{comment_symbol} REPO: {PROJECT_REPO}",
        ]

        for k in sorted(
            count.keys(), key=lambda x: RULE_TYPE_PRIORITY.get(x, DEFAULT_PRIORITY)
        ):
            if count[k] > 0:
                body_lines.append(f"{comment_symbol} {k}: {count[k]}")

        body_lines.append(f"{comment_symbol} TOTAL: {valid_rule_count}")

    body_lines.extend(content_lines)

    new_body = "\n".join(body_lines) + "\n"
    updated_prefix = f"{comment_symbol} UPDATED:"

    # 旧文件存在时，先去掉它自己的 UPDATED 行再比对
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                old_text = f.read()
        except OSError:
            old_text = None

        if old_text is not None and updated_prefix in old_text:
            old_body = (
                "\n".join(
                    line
                    for line in old_text.splitlines()
                    if not line.startswith(updated_prefix)
                )
                + "\n"
            )
            if old_body == new_body:
                # 内容完全没有变化：文件保持原样
                return True, None, path, _read_updated(old_text, updated_prefix)

    # 内容有变化（或文件不存在）：写入
    if want_header:
        updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        content = (
            "\n".join(body_lines[:3])
            + "\n"
            + f"{comment_symbol} UPDATED: UTC+8 {updated}\n"
            + "\n".join(body_lines[3:])
            + "\n"
        )
    else:
        updated = None
        content = new_body

    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        return True, None, path, updated

    except OSError as e:
        return False, f"{path} ({e})", None, None
