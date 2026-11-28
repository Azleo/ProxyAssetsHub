# core/reporter.py

# ======================================================================
# 模块说明：状态报告
#
# 职责：每次运行结束后，在每个客户端目录下写一份 README.md，
#       列出该客户端所有规则文件的订阅地址、条数和最后变更时间。
#
# 为什么按客户端分目录写：用户是"先选软件、再找规则"，
# 所以从 rule/QuantumultX/ 点进去就应该看到这一份说明。
#
# 内容每天都会变（因为写了"最近一次运行"），所以每天至少会有一条提交，
# 这就充当了"心跳"——即使规则没有任何变化，也能看出程序跑过。
# ======================================================================

import os

from core.constants import PROJECT_BRANCH, PROJECT_REPO

# 客户端目录名 → 展示用标题
CLIENT_TITLES = {
    "quantumultx": "Quantumult X",
    "clash": "Clash",
    "loon": "Loon",
}


def _raw_url(path: str) -> str:
    """把仓库内的相对路径转成可以直接订阅的 raw 地址。"""
    repo = PROJECT_REPO.replace(
        "https://github.com/", "https://raw.githubusercontent.com/"
    )
    clean = _to_posix(path).lstrip("./")
    return f"{repo}/{PROJECT_BRANCH}/{clean}"


def _title(client_dir: str) -> str:
    return CLIENT_TITLES.get(client_dir.lower(), client_dir)


def _to_posix(path: str) -> str:
    """
    把路径统一成正斜杠。

    这里的活儿是按字符串切路径，所以分隔符必须统一。
    Windows 下 relpath 给的是反斜杠，直接去找 "/客户端/" 会找不到，
    于是分组和排序全部跑偏。文件名里本来也不会出现反斜杠，替换是安全的。
    """
    return path.replace("\\", "/")


def _sub_dir(path: str, client_dir: str) -> str:
    """
    从产物路径里取出"所在子文件夹"。

    例如 rule/QuantumultX/AI/OpenAI.list → "AI"
         rule/QuantumultX/Direct.list     → ""（根目录）
    """
    path = _to_posix(path)
    marker = f"/{client_dir}/"
    index = path.find(marker)
    rel = path[index + len(marker):] if index >= 0 else path
    return os.path.dirname(rel)


def _file_label(path: str) -> str:
    """从文件名里取出分册名，例如 Direct_Domain.yaml → Domain。"""
    stem = os.path.splitext(os.path.basename(path))[0]
    if "_" in stem:
        return stem.rsplit("_", 1)[1]
    return stem


def build_readme(client_dir: str, artifacts: list, run_time: str, ok: int, total: int) -> str:
    """
    生成一份 README 的内容（纯字符串，方便测试）。

    artifacts 每项：{collection, rules, updated, files}

    排版原则：规则集信息和订阅地址分行写。订阅地址是要复制的东西，
    和条数挤在同一行不好复制、也不好读。
    """
    title = _title(client_dir)

    lines = [
        f"# {title} 规则",
        "",
        "本文件由程序自动生成，每次运行会更新。",
        "",
        f"- 最近一次运行：{run_time}（{ok}/{total} 个规则集成功）",
        f"- 仓库地址：{PROJECT_REPO}",
        "",
        "## 规则清单",
        "",
    ]

    # 按"所在子文件夹"分组，让读者一眼看出哪些规则属于同一类；
    # 分组顺序沿用传入顺序（调用方已经按 GitHub 文件列表排好）
    groups = []
    for item in artifacts:
        sub_dir = _sub_dir(item["files"][0], client_dir) if item["files"] else ""
        if not groups or groups[-1][0] != sub_dir:
            groups.append((sub_dir, []))
        groups[-1][1].append(item)

    for index, (sub_dir, items) in enumerate(groups):
        # 分类标题统一用文件夹图标。
        # "根目录"指的是客户端目录本身（例如 rule/QuantumultX/），它也是一个文件夹，
        # 所以不用换成文档类图标，只用名字区分即可。
        # 图标的作用是让"分类"和下面的"规则集"在视觉上拉开层级。
        lines.append(f"### 📁 {sub_dir or '根目录'}")
        lines.append("")

        for item in items:
            updated = item["updated"] or "未知"
            files = item["files"]

            lines.append(f"#### {item['collection']}")
            lines.append("")
            lines.append(f"条数：{item['rules']:,} ｜ 最后变更：{updated}")
            lines.append("")

            if len(files) == 1:
                # 单文件（例如 Quantumult X）：地址直接一行，方便整行复制
                lines.append(f"订阅地址：{_raw_url(files[0])}")
            else:
                # 多文件（例如 Clash 分 Domain/IP/Classical）：逐条列出
                lines.append("订阅地址：")
                for f in files:
                    lines.append(f"- {_file_label(f)}：{_raw_url(f)}")

            lines.append("")

        # 分类之间加一条分隔线，视觉上更清楚
        if index != len(groups) - 1:
            lines.append("---")
            lines.append("")

    lines += [
        "## 说明",
        "",
        "「最后变更」是这个规则集最后一次真正发生变化的时间。",
        "内容没变时程序不会重写文件，所以这个时间不会每天前进。",
        "",
    ]
    return "\n".join(lines)


def write_client_readmes(project_root, artifacts, run_time, ok, total) -> list:
    """
    按客户端目录写出 README.md，返回写出的文件路径列表。

    artifacts 每项：{client_dir, collection, rules, updated, files}
    """
    # 先把同一个规则集的多个文件合并成一条记录
    # （Clash 一个规则集会输出 Domain/IP/Classical 三个文件）
    merged = {}
    for item in artifacts:
        key = (item["category"], item["client_dir"], item["collection"])
        slot = merged.get(key)
        if slot is None:
            merged[key] = {
                "collection": item["collection"],
                "rules": item["rules"],
                "updated": item["updated"],
                "files": list(item["files"]),
                "category": item["category"],
                "client_dir": item["client_dir"],
            }
        else:
            slot["rules"] += item["rules"]
            slot["files"].extend(item["files"])
            if item["updated"] and (
                not slot["updated"] or item["updated"] > slot["updated"]
            ):
                slot["updated"] = item["updated"]

    # 再按 (阶段, 客户端目录) 分组，例如 rule/QuantumultX、rule/Clash
    grouped = {}
    for slot in merged.values():
        key = (slot["category"], slot["client_dir"])
        grouped.setdefault(key, []).append(slot)

    # 组内排序：与 GitHub 网页上的文件列表保持一致——
    # 先按子文件夹（AI、Block…），最后是根目录下的规则集；
    # 同一层内按名称字母序。这样 README 和文件列表看到的顺序一样。
    for (category, client_dir), items in grouped.items():
        prefix = f"{category}/{client_dir}/"

        def sort_key(item, prefix=prefix):
            first_file = _to_posix(item["files"][0]) if item["files"] else ""
            rel = (
                first_file.removeprefix(prefix)
            )
            sub_dir = os.path.dirname(rel)
            # 根目录的排最后，其余按子目录名、再按规则集标识
            return (1 if sub_dir == "" else 0, sub_dir.lower(), item["collection"].lower())

        items.sort(key=sort_key)

    written = []
    for (category, client_dir), items in grouped.items():
        content = build_readme(client_dir, items, run_time, ok, total)

        directory = os.path.join(project_root, category, client_dir)
        os.makedirs(directory, exist_ok=True)

        path = os.path.join(directory, "README.md")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

        written.append(path)

    return written
