# core/rewrite/formatter_rewrite_loon.py

# ----------------------------------------------------------------------
# 模块元数据常量
# 定义输出文件相关的基本信息，供 Writer 模块使用。
# ----------------------------------------------------------------------

# 必需常量：输出重写规则存放的子目录名称
DIR_NAME = "Loon"
# 必需常量：文件中使用的注释符号
COMMENT_SYMBOL = "#"
# 必需常量：输出文件的默认扩展名，Loon 的重写规则以 .plugin 结尾
FILE_EXTENSION = "plugin"


def format_rules(
    rules: list[str],
    collection: str,
    policy: str = "Default",
    header_lines: list[str] | None = None,
) -> list[dict]:
    """
    将重写规则写入 Loon 的 .plugin 文件。

    注意：这里**不做任何语法解析，也不做任何转换**，拿到的行原样放进产物。
    当前是占位实现——真正做适配时，要在这里按 Loon 的插件语法把规则分节
    （[Script] / [MITM] / [URL Rewrite] 等），并按各节的要求校验写法。

    参数:
        rules (List[str]): 经过处理器清洗后的重写规则行。
        collection (str): 规则集标识，用于拼文件名。
        policy (str): 策略名。重写规则不使用策略，这里保留参数只为和其它翻译器接口一致。
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

    # 2. 添加规则内容
    formatted.extend(rules)

    # 返回文件清单：一个规则集只产出一个 .plugin 文件
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
