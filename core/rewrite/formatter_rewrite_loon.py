# core/rewrite/formatter_rewrite_loon.py

# ----------------------------------------------------------------------
# 模块元数据常量
# 定义输出文件相关的基本信息，用于 Loon 的重写（Rewrite）配置文件。
# ----------------------------------------------------------------------

# 必需常量：输出重写规则存放的子目录名称
DIR_NAME = "Loon"
# 必需常量：文件中使用的注释符号
COMMENT_SYMBOL = "#"
# 必需常量：输出文件的默认扩展名，Loon 的重写规则常以 .plugin 格式存在
FILE_EXTENSION = "plugin"


def format_rules(
    rules: list[str], policy_tag: str = "Default", header_lines: list[str] = None
) -> list[str]:
    """
    重写规则格式化函数：将标准格式的重写规则列表转换为 Loon 格式。

    与 Quantumult X 类似，Loon 的重写规则格式兼容性高，不需要复杂的规则转换。
    本函数主要任务是添加用户自定义的头部注释。

    参数:
        rules (List[str]): 经过清洗后的重写规则列表。
        policy_tag (str): 策略标签（在此格式中作用有限）。
        header_lines (List[str] | None): 用户在配置中定义的额外头部注释行。

    返回:
        List[str]: 格式化后的重写规则列表。
    """
    formatted = []

    # 1. 处理用户自定义头部
    if header_lines:
        # 遍历用户定义的头部注释行
        for header in header_lines:
            # 在每行前加上注释符号和空格，然后添加到结果中
            formatted.append(f"{COMMENT_SYMBOL} {header}")

    # 2. 添加规则内容
    # 由于 Loon 的重写规则格式是通用的，可以直接将清洗后的规则内容（rules）添加到结果列表
    formatted.extend(rules)

    # 返回包含头部和规则的最终列表
    return formatted
