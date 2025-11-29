# core/rewrite/formatter_rewrite_quantumultx.py

# ----------------------------------------------------------------------
# 模块元数据常量
# 定义输出文件相关的基本信息，用于 Quantumult X 的重写（Rewrite）配置文件。
# ----------------------------------------------------------------------

# 必需常量：输出重写规则存放的子目录名称
DIR_NAME = "QuantumultX"
# 必需常量：文件中使用的注释符号
COMMENT_SYMBOL = "#"
# 必需常量：输出文件的默认扩展名，重写规则通常以 .conf 结尾
FILE_EXTENSION = "conf"

def format_rules(rules, policy_tag="Default", header_lines=None):
    """
    占位
    """
    formatted = []

    # 1. 处理用户自定义头部
    if header_lines:
        for header in header_lines:
            formatted.append(f"{COMMENT_SYMBOL} {header}")

    # 2. 添加规则内容
    formatted.extend(rules)
    
    return formatted