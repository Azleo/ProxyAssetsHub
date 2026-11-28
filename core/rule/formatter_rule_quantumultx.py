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
    rules: list[tuple[str, str]],
    collection: str,
    policy: str = "Default",
    header_lines: list[str] | None = None,
) -> list[dict]:
    """
    将标准格式的规则列表转换为 Quantumult X 格式的规则列表。

    Quantumult X 格式要求：规则类型（特殊名称）, 规则值, 策略标签

    参数:
        rules (List[tuple]): 经过处理和排序的规则，每项是 (类型, 值) 两栏。
        policy (str): 规则将被导向的策略组名称（例如 "Proxy" 或 "Reject"）。
        header_lines (List[str] | None): 用户在配置中定义的额外头部注释行。

    返回:
        文件清单（列表），每项描述一个要写出的文件：
        {"dir": 目录, "filename": 文件名, "content": 内容行, "header": 是否写标准头部, "comment": 注释符}
    """
    formatted = []

    # 1. 处理用户自定义头部
    if header_lines:
        # 遍历用户定义的头部注释行
        for header in header_lines:
            # 在每行前加上注释符号和空格，然后添加到结果中
            formatted.append(f"{COMMENT_SYMBOL} {header}")

    # 2. 处理规则内容
    # 收到的是两栏结构（类型 / 值），这里负责拼成 QX 的写法
    rule_count = 0
    for rule in rules:
        # 检查标准规则类型是否在 QX 映射表中
        if rule.type not in QX_MAPPING:
            # 如果是未知类型，则跳过此条规则
            continue

        # 按照 QX 格式重新拼装规则：TYPE,VALUE,POLICY
        final_line = f"{QX_MAPPING[rule.type]},{rule.value},{policy}"

        # 将最终格式化的规则添加到结果列表
        formatted.append(final_line)
        rule_count += 1

    # 返回文件清单：QX 一个规则集只产出一个文件，文件名就是规则集标识
    return [
        {
            "dir": DIR_NAME,
            "filename": f"{collection}.{FILE_EXTENSION}",
            "content": formatted,
            "rule_count": rule_count,
            "header": True,
            "comment": COMMENT_SYMBOL,
        }
    ]
