# core/rule/formatter_rule_loon.py

# ----------------------------------------------------------------------
# 模块元数据常量
# 定义输出文件相关的基本信息，供 Writer 模块使用。
# ----------------------------------------------------------------------

# 必需常量：输出规则存放的子目录名称
DIR_NAME = "Loon"
# 必需常量：文件中使用的注释符号
COMMENT_SYMBOL = "#"
# 必需常量：输出文件的默认扩展名
FILE_EXTENSION = "list"


def format_rules(
    rules: List[str], policy_tag: str = "Default", header_lines: List[str] = None
) -> List[str]:
    """
    将标准格式的规则列表转换为 Loon 格式的规则列表。

    Loon 软件的规则列表（List）格式与项目内部的“通用标准格式”高度兼容，
    因此主要操作是添加头部注释。Loon 在导入时会根据规则内容自动分配策略。

    参数:
        rules (List[str]): 经过处理和排序后的标准规则列表（格式: TYPE,value）。
        policy_tag (str): 规则将被导向的策略组名称（在这个格式中主要用于文件名，不直接写入规则行）。
        header_lines (List[str] | None): 用户在配置中定义的额外头部注释行。

    返回:
        List[str]: 格式化后的规则列表。
    """
    formatted = []

    # 1. 处理用户自定义头部
    if header_lines:
        # 遍历用户定义的头部注释行
        for header in header_lines:
            # 在每行前加上注释符号和空格，然后添加到结果中
            formatted.append(f"{COMMENT_SYMBOL} {header}")

    # 2. 添加规则内容
    # Loon 的规则格式与项目内部的清洗/排序后的标准格式兼容（如 DOMAIN-SUFFIX,google.com），
    # 因此可以直接将规则列表添加到结果中。
    formatted.extend(rules)

    # 返回包含头部和规则的最终列表
    return formatted
