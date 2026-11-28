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
    rules: list[tuple[str, str]],
    collection: str,
    policy: str = "Default",
    header_lines: list[str] | None = None,
) -> list[dict]:
    """
    将标准格式的规则列表转换为 Loon 格式的规则列表。

    Loon 的规则行写法是「规则类型,规则值」，一个规则集产出一个文件。

    注意：这里**不做任何类型转换，也不追加任何参数**（例如 no-resolve），
    内部的标准类型名和值直接写进产物。它看起来刚好能用，是因为 Loon 的类型名
    恰好和项目内部的标准名一致——这不是适配，只是巧合。
    真正做适配时，在这里加一张映射表即可，其它模块都不用动。

    参数:
        rules (List[tuple]): 经过处理和排序的规则，每项是 (类型, 值) 两栏。
        collection (str): 规则集标识，用于拼文件名。
        policy (str): 策略名。Loon 的规则行里不写策略，这里保留参数只为和其它翻译器接口一致。
        header_lines (List[str] | None): 用户在配置中定义的额外头部注释行。

    返回:
        文件清单（列表），每项描述一个要写出的文件：
        {"dir": 目录, "filename": 文件名, "content": 内容行, "header": 是否写标准头部, "comment": 注释符}
    """
    formatted = []

    # 1. 处理用户自定义头部
    if header_lines:
        for header in header_lines:
            formatted.append(f"{COMMENT_SYMBOL} {header}")

    # 2. 处理规则内容：类型和值原样拼起来
    for rule in rules:
        formatted.append(f"{rule.type},{rule.value}")

    # 返回文件清单：Loon 一个规则集只产出一个文件
    return [
        {
            "dir": DIR_NAME,
            "filename": f"{collection}.{FILE_EXTENSION}",
            "content": formatted,
            "rule_count": len(rules),
            "header": True,
            "comment": COMMENT_SYMBOL,
        }
    ]
