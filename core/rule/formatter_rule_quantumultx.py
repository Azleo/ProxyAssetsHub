# core/rule/formatter_rule_quantumultx.py

# ----------------------------------------------------------------------
# 模块元数据常量
# 定义输出文件相关的基本信息，供 Writer 模块使用。
# ----------------------------------------------------------------------

# 必需常量：输出规则存放的子目录名称
DIR_NAME = "QuantumultX"
# 必需常量：文件中使用的注释符号
COMMENT_SYMBOL = "#"
# 必需常量：输出文件的默认扩展名
FILE_EXTENSION = "list"

# ----------------------------------------------------------------------
# 规则类型映射表
# 将项目中使用的“通用标准规则类型”（Key）转换回 Quantumult X 软件特有的规则类型（Value）。
# ----------------------------------------------------------------------
QX_MAPPING = {
    # 域名类规则的转换
    "DOMAIN": "HOST",
    "DOMAIN-SUFFIX": "HOST-SUFFIX",
    "DOMAIN-WILDCARD": "HOST-WILDCARD",
    "DOMAIN-KEYWORD": "HOST-KEYWORD",
    # 其他类型规则的转换
    "USER-AGENT": "USER-AGENT",
    "IP-CIDR": "IP-CIDR",
    # 注意：IPv6 规则在 QX 中通常使用 IP6-CIDR 而非 IP-CIDR6
    "IP-CIDR6": "IP6-CIDR",
    "GEOIP": "GEOIP",
    "IP-ASN": "IP-ASN",
}


def format_rules(
    rules: list[str], policy_tag: str = "Default", header_lines: list[str] = None
) -> list[str]:
    """
    将标准格式的规则列表转换为 Quantumult X 格式的规则列表。

    Quantumult X 格式要求：规则类型（特殊名称）, 规则值, 策略标签

    参数:
        rules (List[str]): 经过处理和排序后的标准规则列表（格式: TYPE,value）。
        policy_tag (str): 规则将被导向的策略组名称（例如 "Proxy" 或 "Reject"）。
        header_lines (List[str] | None): 用户在配置中定义的额外头部注释行。

    返回:
        List[str]: 格式化为 QX 标准语法的规则列表。
    """
    formatted = []

    # 1. 处理用户自定义头部
    if header_lines:
        # 遍历用户定义的头部注释行
        for header in header_lines:
            # 在每行前加上注释符号和空格，然后添加到结果中
            formatted.append(f"{COMMENT_SYMBOL} {header}")

    # 2. 处理规则内容
    # 遍历输入的标准规则列表
    for line in rules:
        # 如果规则行中没有逗号，说明格式不符合 "TYPE,value" 标准，跳过
        if "," not in line:
            continue

        # 将标准规则行分割成类型和值两部分
        parts = line.split(",", 1)
        std_type = parts[0]  # 标准规则类型
        value = parts[1]  # 规则值

        # 检查标准规则类型是否在 QX 映射表中
        if std_type not in QX_MAPPING:
            # 如果是未知类型，则跳过此条规则
            continue

        # 根据映射表获取 Quantumult X 软件特有的规则类型
        qx_type = QX_MAPPING[std_type]

        # 按照 QX 格式重新拼装规则：TYPE,VALUE,POLICY
        final_line = f"{qx_type},{value},{policy_tag}"
        # 将最终格式化的规则添加到结果列表
        formatted.append(final_line)

    # 返回所有格式化后的规则列表
    return formatted
